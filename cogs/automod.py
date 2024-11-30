import discord
from discord.ext import commands, tasks
from discord import app_commands

import re
import logging
from datetime import datetime, timedelta
import math
import aiohttp
import asyncio

# Define the check function outside the class for command permissions
async def is_admin_or_owner(interaction: discord.Interaction) -> bool:
    # Access bot via interaction.client
    bot = interaction.client
    # Check if owner_id is cached
    if not hasattr(bot, 'owner_id'):
        app_info = await bot.application_info()
        bot.owner_id = app_info.owner.id
    bot_owner_id = bot.owner_id
    if interaction.user.id == bot_owner_id:
        return True
    if interaction.user.guild_permissions.administrator:
        return True
    raise app_commands.MissingPermissions(['administrator'])

class WarningsView(discord.ui.View):
    def __init__(self, warnings, user, per_page=7):
        super().__init__(timeout=180)
        self.warnings = warnings
        self.user = user
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = math.ceil(len(warnings) / per_page)

        self.previous_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.blurple)
        self.next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.blurple)
        self.previous_button.callback = self.previous_page
        self.next_button.callback = self.next_page

        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.update_buttons()

    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1

    def create_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        embed = discord.Embed(
            title=f"Warnings for {self.user}",
            color=0xFF0000,
            description=f"Page {self.current_page + 1}/{self.total_pages}",
        )
        for warn in self.warnings[start:end]:
            embed.add_field(
                name=f"Warning ID: {warn[5]}",
                value=(
                    f"**Reason:** {warn[3]}\n"
                    f"**Moderator:** <@{warn[2]}>\n"
                    f"**Date:** <t:{int(warn[4])}:F>"
                ),
                inline=False,
            )
        return embed

    async def previous_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)

class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = None  # Placeholder for the database manager instance

        # Patterns for auto-moderation
        self.roblox_group_regex = re.compile(
            r"https?://www\.roblox\.com/communities/\d+/[a-zA-Z0-9\-]+",
            re.IGNORECASE
        )
        self.discord_invite_regex = re.compile(
            r"(https?://)?(www\.)?(discord\.(gg|io|me|li)|discordapp\.com/invite)/[a-zA-Z0-9]+",
            re.IGNORECASE
        )
        self.profanity_list = []  # Will be loaded asynchronously
        self.profanity_pattern = None  # Will be set after loading

        # Start the tasks
        self.expire_warnings_task.start()
        self.load_profanity_list_task.start()

    async def cog_load(self):
        self.db = self.bot.database  # Access DatabaseManager from the bot instance
        if not self.db:
            raise ValueError("DatabaseManager is not initialized in the bot.")

        # Ensure owner_id is cached
        if not hasattr(self.bot, 'owner_id'):
            app_info = await self.bot.application_info()
            self.bot.owner_id = app_info.owner.id

    def cog_unload(self):
        self.expire_warnings_task.cancel()
        self.load_profanity_list_task.cancel()

    async def handle_message_violation(self, message: discord.Message, reason: str):
        try:
            # Delete the violating message instantly
            await message.delete()

            # Log the violation to the database
            warn_id = await self.db.add_warn(
                user_id=message.author.id,
                server_id=message.guild.id,
                moderator_id=self.bot.user.id,
                reason=reason,
            )

            # Send a plain warning message
            warning_msg = (
                f"{message.author.mention}, your message violated the server rules.\n"
                f"**Reason:** {reason}"
            )
            moderation_message = await message.channel.send(warning_msg)

            # Check the number of warnings
            warning_count = await self.db.count_warnings(
                user_id=message.author.id, server_id=message.guild.id
            )

            # Apply timeouts based on warning count
            if warning_count == 3:
                timeout_duration = timedelta(minutes=10)
                await message.author.timeout(timeout_duration, reason="Reached 3 warnings")
                await message.channel.send(
                    f"🚫 {message.author.mention} has been timed out for 10 minutes due to accumulating 3 warnings."
                )
            elif warning_count == 6:
                timeout_duration = timedelta(hours=24)
                await message.author.timeout(timeout_duration, reason="Reached 6 warnings")
                await message.channel.send(
                    f"🚫 {message.author.mention} has been timed out for 24 hours due to accumulating 6 warnings."
                )

            # Delete the moderation message after 10 seconds
            await asyncio.sleep(10)
            await moderation_message.delete()

            # Log the automod action if logging is enabled
            server_settings = await self.db.get_server_settings(message.guild.id)
            if server_settings.get('automod_logging_enabled'):
                log_channel_id = server_settings.get('automod_log_channel_id')
                if log_channel_id:
                    log_channel = message.guild.get_channel(int(log_channel_id))
                    if log_channel:
                        log_embed = discord.Embed(
                            title="🚨 Automod Violation",
                            color=0xFF0000,
                            timestamp=datetime.utcnow()
                        )
                        log_embed.add_field(name="User", value=message.author.mention, inline=True)
                        log_embed.add_field(name="Action", value=reason, inline=True)
                        log_embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                        log_embed.set_footer(text=f"User ID: {message.author.id}")
                        await log_channel.send(embed=log_embed)
        except Exception as e:
            self.bot.logger.error(f"Failed to handle message violation: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # Bypass AutoMod if the user is an admin or the bot owner
        if await self.is_bypass(message):
            return

        # Check if automod is enabled for this server
        server_settings = await self.db.get_server_settings(message.guild.id)
        if not server_settings.get('automod_enabled', True):
            return

        content = message.content

        if self.roblox_group_regex.search(content):
            await self.handle_message_violation(message, "Posting Roblox group links.")
        elif self.discord_invite_regex.search(content):
            await self.handle_message_violation(message, "Posting Discord invite links.")
        elif self.profanity_pattern and self.profanity_pattern.search(content):
            await self.handle_message_violation(message, "Using prohibited language.")

    async def is_bypass(self, message: discord.Message) -> bool:
        """
        Checks if the user is the bot owner or has administrator permissions.

        :param message: The message to check.
        :return: True if the user should bypass automod, False otherwise.
        """
        # Ensure owner_id is cached
        if not hasattr(self.bot, 'owner_id'):
            try:
                app_info = await self.bot.application_info()
                self.bot.owner_id = app_info.owner.id
            except Exception as e:
                self.bot.logger.error(f"Failed to fetch application info: {e}")
                return False  # Default to not bypass

        if message.author.id == self.bot.owner_id:
            return True
        if message.author.guild_permissions.administrator:
            return True
        return False

    @tasks.loop(minutes=5)
    async def expire_warnings_task(self):
        """Task to expire warnings older than 1 hour."""
        try:
            expiration_timestamp = int((datetime.now() - timedelta(hours=1)).timestamp())
            # Remove expired warnings directly
            await self.db.remove_expired_warnings(expiration_timestamp)
            # Removed the log line that was printing to the console
            # self.bot.logger.info(f"Expired warnings older than {expiration_timestamp}.")
        except Exception as e:
            self.bot.logger.error(f"Error in warning expiration task: {e}")

    @tasks.loop(count=1)
    async def load_profanity_list_task(self):
        """Load the profanity list and compile the regex pattern."""
        url = "https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/en"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        text = await response.text()
                        self.profanity_list = [word.strip() for word in text.splitlines() if word.strip()]
                        # Compile the profanity regex pattern
                        escaped_words = [re.escape(word) for word in self.profanity_list]
                        pattern = r'\b(' + '|'.join(escaped_words) + r')\b'
                        self.profanity_pattern = re.compile(pattern, re.IGNORECASE)
                        self.bot.logger.info("Profanity list loaded and regex compiled successfully.")
                    else:
                        self.bot.logger.error(f"Failed to load profanity list: HTTP {response.status}")
        except Exception as e:
            self.bot.logger.error(f"Error loading profanity list: {e}")

    @app_commands.command(name="warns", description="View all warnings for a user.")
    @app_commands.describe(user="The user to view warnings for.")
    @app_commands.check(is_admin_or_owner)
    async def warns(self, interaction: discord.Interaction, user: discord.Member):
        # Use the thinking function
        await interaction.response.defer(ephemeral=True)

        warnings = await self.db.get_warnings(user_id=user.id, server_id=interaction.guild.id)
        if warnings:
            if len(warnings) > 7:
                view = WarningsView(warnings, user)
                embed = view.create_embed()
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                embed = discord.Embed(
                    title=f"Warnings for {user}",
                    color=0xFF0000,
                )
                for warn in warnings:
                    embed.add_field(
                        name=f"Warning ID: {warn[5]}",
                        value=(
                            f"**Reason:** {warn[3]}\n"
                            f"**Moderator:** <@{warn[2]}>\n"
                            f"**Date:** <t:{int(warn[4])}:F>"
                        ),
                        inline=False,
                    )
                await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="No Warnings Found",
                description=f"{user.mention} has no recorded warnings.",
                color=0x00FF00,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Clear all warnings for a user.")
    @app_commands.describe(user="The user to clear warnings for.")
    @app_commands.check(is_admin_or_owner)
    async def clearwarnings(self, interaction: discord.Interaction, user: discord.Member):
        # Use the thinking function
        await interaction.response.defer(ephemeral=True)

        await self.db.clear_all_warnings(user_id=user.id, server_id=interaction.guild.id)
        embed = discord.Embed(
            title="Warnings Cleared",
            description=f"All warnings for {user.mention} have been cleared.",
            color=0x00FF00,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarn", description="Clear a specific warning for a user.")
    @app_commands.describe(user="The user to clear warning for.", warn_id="The ID of the warning to clear.")
    @app_commands.check(is_admin_or_owner)
    async def clearwarn(self, interaction: discord.Interaction, user: discord.Member, warn_id: int):
        # Use the thinking function
        await interaction.response.defer(ephemeral=True)

        # Attempt to remove the warning
        result = await self.db.remove_warn(warn_id=warn_id, user_id=user.id, server_id=interaction.guild.id)
        if result:
            embed = discord.Embed(
                title="Warning Removed",
                description=f"Warning ID {warn_id} for {user.mention} has been removed.",
                color=0x00FF00,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="Warning Not Found",
                description=f"No warning with ID {warn_id} found for {user.mention}.",
                color=0xFF0000,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    # Error handlers for commands
    @warns.error
    async def warns_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="Missing Permissions",
                description="You need the `Administrator` permission to use this command.",
                color=0xFF0000,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            self.bot.logger.error(f"Error in /warns command: {error}")
            raise error

    @clearwarnings.error
    async def clearwarnings_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="Missing Permissions",
                description="You need the `Administrator` permission to use this command.",
                color=0xFF0000,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            self.bot.logger.error(f"Error in /clearwarnings command: {error}")
            raise error

    @clearwarn.error
    async def clearwarn_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="Missing Permissions",
                description="You need the `Administrator` permission to use this command.",
                color=0xFF0000,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            self.bot.logger.error(f"Error in /clearwarn command: {error}")
            raise error

# Setup function
async def setup(bot):
    await bot.add_cog(AutoMod(bot))
