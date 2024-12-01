import discord
from discord.ext import commands, tasks
from discord import app_commands

import re
from datetime import datetime, timedelta
import math
import aiohttp
import asyncio

# Define the check function outside the class for command permissions
async def is_admin_or_owner(interaction: discord.Interaction) -> bool:
    bot = interaction.client
    if not hasattr(bot, 'owner_id'):
        app_info = await bot.application_info()
        bot.owner_id = app_info.owner.id
    if interaction.user.id == bot.owner_id or interaction.user.guild_permissions.administrator:
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

        self.previous_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.blurple, disabled=True)
        self.next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.blurple, disabled=(self.total_pages <= 1))
        self.previous_button.callback = self.previous_page
        self.next_button.callback = self.next_page

        self.add_item(self.previous_button)
        self.add_item(self.next_button)

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

    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1

class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = None  # Placeholder for the database manager instance

        # Compile regex patterns for performance
        self.roblox_group_regex = re.compile(
            r"https?://www\.roblox\.com/communities/\d+/[a-zA-Z0-9\-]+",
            re.IGNORECASE
        )
        self.discord_invite_regex = re.compile(
            r"(https?://)?(www\.)?(discord\.(gg|io|me|li)|discordapp\.com/invite)/[a-zA-Z0-9]+",
            re.IGNORECASE
        )
        self.profanity_list = []
        self.profanity_pattern = None

        # Start background tasks
        self.expire_warnings_task.start()
        self.load_profanity_list_task.start()

    async def cog_load(self):
        self.db = self.bot.database  # Access DatabaseManager from the bot instance
        if not self.db:
            raise ValueError("DatabaseManager is not initialized in the bot.")

        # Cache owner_id
        if not hasattr(self.bot, 'owner_id'):
            app_info = await self.bot.application_info()
            self.bot.owner_id = app_info.owner.id

    def cog_unload(self):
        self.expire_warnings_task.cancel()
        self.load_profanity_list_task.cancel()

    async def handle_message_violation(self, message: discord.Message, reason: str):
        try:
            # Delete the violating message
            await message.delete()

            # Log the violation to the database
            warn_id = await self.db.add_warn(
                user_id=message.author.id,
                server_id=message.guild.id,
                moderator_id=self.bot.user.id,
                reason=reason,
            )

            # Send a warning message to the user
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
            timeout_actions = {
                3: timedelta(minutes=10),
                6: timedelta(hours=24)
            }

            if warning_count in timeout_actions:
                duration = timeout_actions[warning_count]
                await message.author.timeout(duration, reason=f"Reached {warning_count} warnings")
                duration_str = f"{duration.total_seconds() / 60} minutes" if warning_count == 3 else "24 hours"
                await message.channel.send(
                    f"🚫 {message.author.mention} has been timed out for {duration_str} due to accumulating {warning_count} warnings."
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
                        log_embed.add_field(name="Message", value=f"||{message.content}||", inline=False)
                        log_embed.set_footer(text=f"User ID: {message.author.id} | Warn ID: {warn_id}")
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
        if not hasattr(self.bot, 'owner_id'):
            try:
                app_info = await self.bot.application_info()
                self.bot.owner_id = app_info.owner.id
            except Exception as e:
                self.bot.logger.error(f"Failed to fetch application info: {e}")
                return False  # Default to not bypass

        return message.author.id == self.bot.owner_id or message.author.guild_permissions.administrator

    @tasks.loop(minutes=5)
    async def expire_warnings_task(self):
        """Task to expire warnings older than 1 hour."""
        try:
            expiration_timestamp = int((datetime.utcnow() - timedelta(hours=1)).timestamp())
            await self.db.remove_expired_warnings(expiration_timestamp)
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

    # Consolidated error handler
    async def send_missing_permissions_error(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Missing Permissions",
            description="You need the `Administrator` permission to use this command.",
            color=0xFF0000,
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @warns.error
    @clearwarnings.error
    @clearwarn.error
    async def commands_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await self.send_missing_permissions_error(interaction)
        else:
            self.bot.logger.error(f"Error in command {interaction.command}: {error}")
            raise error

# Setup function
async def setup(bot):
    await bot.add_cog(AutoMod(bot))
