# ai_moderation.py

import discord
from discord.ext import commands, tasks
from discord import app_commands

import openai
import aiohttp
import asyncio
import os
import json
from typing import Optional

# Constants
TARGET_GUILD_ID = 1087452557426819203  # Replace with your server ID
LOG_CHANNEL_ID = 123456789012345678  # Replace with your log channel ID if any

# Initialize OpenAI API
openai.api_key = os.getenv("OPENAI_API_KEY")  # Ensure your OpenAI API key is set as an environment variable

# Define a check for administrator permissions
async def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator

class AIModeration(commands.Cog):
    """
    A Cog for AI-based moderation using OpenAI's Moderation API.
    Includes commands to enable and disable moderation.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.mod_enabled = False  # Default state; can be loaded from a database if available

        # Start a background task to periodically save settings if needed
        # self.save_settings_task.start()

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())
        # self.save_settings_task.cancel()

    # Optional: Background task to save settings periodically
    # @tasks.loop(minutes=10)
    # async def save_settings_task(self):
    #     # Implement saving settings to the database or a file
    #     pass

    @commands.command(name="aimod")
    @commands.has_permissions(administrator=True)
    async def aimod_command(self, ctx: commands.Context, action: str):
        """
        Command to enable or disable AI moderation.
        Usage: /aimod on | /aimod off
        """
        if ctx.guild.id != TARGET_GUILD_ID:
            await ctx.send("This command cannot be used in this server.", ephemeral=True)
            return

        action = action.lower()
        if action == "on":
            self.mod_enabled = True
            # Save the state to the database if applicable
            await ctx.send("AI Moderation has been **enabled**.")
        elif action == "off":
            self.mod_enabled = False
            # Save the state to the database if applicable
            await ctx.send("AI Moderation has been **disabled**.")
        else:
            await ctx.send("Invalid action. Use `on` or `off`.", ephemeral=True)

    @app_commands.command(name="aimod", description="Enable or disable AI moderation.")
    @app_commands.describe(action="The action to perform: on or off.")
    @app_commands.check(is_admin)
    async def app_aimod_command(self, interaction: discord.Interaction, action: str):
        """
        Slash command to enable or disable AI moderation.
        Usage: /aimod on | /aimod off
        """
        if interaction.guild_id != TARGET_GUILD_ID:
            await interaction.response.send_message("This command cannot be used in this server.", ephemeral=True)
            return

        action = action.lower()
        if action == "on":
            self.mod_enabled = True
            # Save the state to the database if applicable
            await interaction.response.send_message("AI Moderation has been **enabled**.", ephemeral=True)
        elif action == "off":
            self.mod_enabled = False
            # Save the state to the database if applicable
            await interaction.response.send_message("AI Moderation has been **disabled**.", ephemeral=True)
        else:
            await interaction.response.send_message("Invalid action. Use `on` or `off`.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Listener that triggers on every message.
        Checks the message using OpenAI's Moderation API and deletes it if flagged.
        """

        # Ignore messages from bots or in DMs
        if message.author.bot or not message.guild:
            return

        # Ensure the message is in the target server
        if message.guild.id != TARGET_GUILD_ID:
            return

        # Check if AI moderation is enabled
        # Here, it's using an in-memory flag. Replace with a database check if persistent storage is needed.
        if not self.mod_enabled:
            return

        # Prepare the input for the Moderation API
        content = message.content

        if not content:
            # Optionally handle messages without text (e.g., images)
            return

        try:
            # Call OpenAI's Moderation API
            response = await self.call_moderation_api(content)
            # Log the API response
            await self.log_moderation_response(message, response)

            # Check if the content is flagged
            if response.get("flagged"):
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention}, your message was removed for violating the server rules.",
                    delete_after=5  # Message will auto-delete after 5 seconds
                )
        except Exception as e:
            self.bot.logger.error(f"Error during AI moderation: {e}")

    async def call_moderation_api(self, text: str) -> dict:
        """
        Calls OpenAI's Moderation API with the given text.
        Returns the JSON response.
        """
        try:
            response = await openai.Moderation.create(
                model="text-moderation-latest",
                input=text
            )
            return response["results"][0]
        except Exception as e:
            self.bot.logger.error(f"Failed to call OpenAI Moderation API: {e}")
            return {}

    async def log_moderation_response(self, message: discord.Message, response: dict):
        """
        Logs the moderation API response.
        Sends the log to a specified channel or prints to console.
        """
        log_data = {
            "message_id": message.id,
            "channel_id": message.channel.id,
            "user_id": message.author.id,
            "content": message.content,
            "flagged": response.get("flagged", False),
            "categories": response.get("categories", {}),
            "category_scores": response.get("category_scores", {})
        }

        log_message = json.dumps(log_data, indent=4)

        if LOG_CHANNEL_ID:
            log_channel = message.guild.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(f"**AI Moderation Log:**\n```\n{log_message}\n```")
            else:
                self.bot.logger.warning(f"Log channel with ID {LOG_CHANNEL_ID} not found.")
        else:
            # Fallback to console logging
            self.bot.logger.info(f"AI Moderation Log: {log_message}")

    # Optional: Handle errors for app commands
    @app_commands.error
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        else:
            self.bot.logger.error(f"Unhandled error in app command: {error}")
            await interaction.response.send_message("An error occurred while processing the command.", ephemeral=True)

    # Optional: Handle errors for text commands
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("You do not have permission to use this command.", delete_after=5)
        else:
            self.bot.logger.error(f"Unhandled error in command: {error}")
            await ctx.send("An error occurred while processing the command.", delete_after=5)

# Setup function to add the cog to the bot
async def setup(bot: commands.Bot):
    await bot.add_cog(AIModeration(bot))
