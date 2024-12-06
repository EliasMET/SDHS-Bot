# automod.py

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
            timestamp=datetime.utcnow()
        )
        for warn in self.warnings[start:end]:
            warn_id, reason, moderator_id, timestamp = warn  # Unpack the tuple
            embed.add_field(
                name=f"Warning ID: {warn_id}",
                value=(
                    f"**Reason:** {reason}\n"
                    f"**Moderator:** <@{moderator_id}>\n"
                    f"**Date:** <t:{int(timestamp)}:F>"
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
    """
    AutoMod Cog
    Provides automated moderation features such as warning users,
    monitoring messages for prohibited content, and handling timeouts.
    
    Version: 1.4.0
    """

    # Define constants for the monitored user and exempt roles
    MONITORED_USER_ID = 1178294054170153010  # The user to monitor mentions for
    EXEMPT_ROLE_IDS = {1311777421049204846, 1289875864749867058}  # Roles that exempt from timeout

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

        # Initialize cache for server settings
        self.server_settings_cache = {}

        # Initialize cache for the monitored user
        self.monitored_user = None

    async def cog_load(self):
        """
        Initialize the cog by setting up the database and caching owner_id.
        """
        self.db = self.bot.database  # Access DatabaseManager from the bot instance
        if not self.db:
            self.bot.logger.error("DatabaseManager is not initialized in the bot.")
            raise ValueError("DatabaseManager is not initialized in the bot.")

        # Cache owner_id
        if not hasattr(self.bot, 'owner_id'):
            app_info = await self.bot.application_info()
            self.bot.owner_id = app_info.owner.id

        # Fetch and cache the monitored user
        try:
            self.monitored_user = await self.bot.fetch_user(self.MONITORED_USER_ID)
            self.bot.logger.info(f"Monitored user '{self.monitored_user}' fetched and cached.")
        except Exception as e:
            self.bot.logger.error(f"Failed to fetch monitored user with ID {self.MONITORED_USER_ID}: {e}")

    def cog_unload(self):
        self.expire_warnings_task.cancel()
        self.load_profanity_list_task.cancel()

    async def handle_message_violation(self, message: discord.Message, reason: str):
        """
        Handles violations detected by AutoMod by deleting the message,
        issuing a warning, notifying the user, and logging the action.
        """
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

            # Send a warning message to the user in the channel
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
                duration_str = f"{int(duration.total_seconds() / 60)} minutes" if warning_count == 3 else "24 hours"
                timeout_notice = (
                    f"🚫 {message.author.mention} has been timed out for {duration_str} due to accumulating {warning_count} warnings."
                )
                await message.channel.send(timeout_notice)

            # Delete the moderation message after 10 seconds to reduce clutter
            await asyncio.sleep(10)
            await moderation_message.delete()

            # Log the automod action if logging is enabled
            server_settings = await self.get_server_settings(message.guild.id)
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
                        log_embed.add_field(name="Reason", value=f"{reason}\n||{message.content}||", inline=False)  # Offending message in spoilers
                        log_embed.set_footer(text=f"User ID: {message.author.id} | Warn ID: {warn_id}")
                        await log_channel.send(embed=log_embed)
        except Exception as e:
            self.bot.logger.error(f"Failed to handle message violation: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Listens to all messages and applies AutoMod checks.
        """
        if message.author.bot:
            return

        # Check if AutoMod is enabled for this server
        server_settings = await self.get_server_settings(message.guild.id)
        if not server_settings.get('automod_enabled', True):
            return

        content = message.content

        # Monitor mentions of the specific user
        if self.MONITORED_USER_ID in [user.id for user in message.mentions]:
            # Only the bot owner can bypass the protected user mention check
            if not await self.is_owner(message.author):
                # Check if the message author has any of the exempt roles
                has_exempt_role = any(role.id in self.EXEMPT_ROLE_IDS for role in message.author.roles)

                if not has_exempt_role:
                    try:
                        # Apply a timeout of one hour
                        duration = timedelta(hours=1)
                        await message.author.timeout(duration, reason=f"Mentioned user {self.monitored_user} without required roles.")

                        # Inform the channel about the timeout without pinging the protected user
                        timeout_message = await message.channel.send(
                            f"🚫 {message.author.mention} has been timed out for 1 hour for mentioning {self.monitored_user.name} without the necessary roles."
                        )

                        # Log the timeout action if logging is enabled
                        if server_settings.get('automod_logging_enabled'):
                            log_channel_id = server_settings.get('automod_log_channel_id')
                            if log_channel_id:
                                log_channel = message.guild.get_channel(int(log_channel_id))
                                if log_channel:
                                    log_embed = discord.Embed(
                                        title="🚨 User Timeout",
                                        color=0xFFA500,
                                        timestamp=datetime.utcnow()
                                    )
                                    log_embed.add_field(name="User", value=message.author.mention, inline=True)
                                    log_embed.add_field(name="Action", value="Mentioned Protected User Without Required Roles", inline=True)
                                    log_embed.add_field(name="Duration", value="1 Hour", inline=True)
                                    log_embed.add_field(name="Reason", value=f"||{message.content}||", inline=False)
                                    log_embed.set_footer(text=f"User ID: {message.author.id}")
                                    await log_channel.send(embed=log_embed)

                        # Optionally, delete the timeout message after some time to reduce clutter
                        await asyncio.sleep(10)
                        await timeout_message.delete()
                    except discord.Forbidden:
                        self.bot.logger.error(f"Missing permissions to timeout user {message.author.id}.")
                    except Exception as e:
                        self.bot.logger.error(f"Failed to timeout user {message.author.id}: {e}")

        # Determine if the user can bypass general AutoMod checks
        can_bypass_general = await self.can_bypass_general_automod(message.author)

        # Existing AutoMod checks (profanity, links, etc.)
        if not can_bypass_general:
            try:
                if self.roblox_group_regex.search(content):
                    await self.handle_message_violation(message, "Posting Roblox group links.")
                elif self.discord_invite_regex.search(content):
                    await self.handle_message_violation(message, "Posting Discord invite links.")
                elif self.profanity_pattern and self.profanity_pattern.search(content):
                    await self.handle_message_violation(message, "Using prohibited language.")
            except Exception as e:
                self.bot.logger.error(f"Error during AutoMod checks: {e}")

    async def get_server_settings(self, guild_id: int):
        """
        Retrieves server settings from the database and caches them.
        """
        # Check if settings are cached
        if guild_id in self.server_settings_cache:
            return self.server_settings_cache[guild_id]

        # Fetch from database and cache it
        try:
            settings = await self.db.get_server_settings(guild_id)
            self.server_settings_cache[guild_id] = settings
            return settings
        except Exception as e:
            self.bot.logger.error(f"Failed to retrieve server settings for guild {guild_id}: {e}")
            return {}

    async def is_owner(self, member: discord.Member) -> bool:
        """
        Checks if the member is the bot owner.

        :param member: The Discord member to check.
        :return: True if the member is the bot owner, False otherwise.
        """
        if not hasattr(self.bot, 'owner_id'):
            try:
                app_info = await self.bot.application_info()
                self.bot.owner_id = app_info.owner.id
            except Exception as e:
                self.bot.logger.error(f"Failed to fetch application info: {e}")
                return False

        return member.id == self.bot.owner_id

    async def can_bypass_general_automod(self, member: discord.Member) -> bool:
        """
        Determines if a member can bypass general AutoMod checks (profanity, links, etc.).
        Only admins and the bot owner can bypass.

        :param member: The Discord member to check.
        :return: True if the member can bypass general AutoMod checks, False otherwise.
        """
        if await self.is_owner(member):
            return True
        if member.guild_permissions.administrator:
            return True
        return False

    @tasks.loop(minutes=10)
    async def expire_warnings_task(self):
        """
        Task to expire warnings older than 2 days.
        """
        try:
            expiration_timestamp = int((datetime.utcnow() - timedelta(days=2)).timestamp())
            await self.db.remove_expired_warnings(expiration_timestamp)
            self.bot.logger.info("Expired warnings older than 2 days.")
        except Exception as e:
            self.bot.logger.error(f"Error in warning expiration task: {e}")

    @tasks.loop(count=1)
    async def load_profanity_list_task(self):
        """
        Load the profanity list and compile the regex pattern.
        """
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

    @app_commands.command(name="warn", description="Issue a warning to a user.")
    @app_commands.describe(user="The user to warn.", reason="The reason for the warning.")
    @app_commands.check(is_admin_or_owner)
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        """
        Issues a warning to a specified user with a provided reason.

        :param interaction: The command interaction.
        :param user: The user to warn.
        :param reason: The reason for the warning.
        """
        await interaction.response.defer(ephemeral=True)  # Use the thinking function

        # Prevent warning the bot itself
        if user.id == self.bot.user.id:
            embed = discord.Embed(
                title="⚠️ Warning Issuance Failed",
                description="I cannot warn myself.",
                color=0x8B0000  # Dark red
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Prevent warning the guild owner
        if user.id == interaction.guild.owner_id:
            embed = discord.Embed(
                title="⚠️ Warning Issuance Failed",
                description="You cannot warn the server owner.",
                color=0x8B0000  # Dark red
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Prevent warning members with higher or equal roles
        if user.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            embed = discord.Embed(
                title="⚠️ Warning Issuance Failed",
                description="You cannot warn a member with equal or higher roles.",
                color=0x8B0000  # Dark red
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        try:
            # Add the warning to the database
            warn_id = await self.db.add_warn(
                user_id=user.id,
                server_id=interaction.guild.id,
                moderator_id=interaction.user.id,
                reason=reason,
            )

            # Send a confirmation message to the moderator
            embed = discord.Embed(
                title="✅ Warning Issued",
                color=0x00FF00,  # Green
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="User", value=user.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Warning ID", value=str(warn_id), inline=True)
            embed.set_footer(text=f"Moderator: {interaction.user} (ID: {interaction.user.id})")
            await interaction.followup.send(embed=embed, ephemeral=True)

            # Send a DM to the warned user
            try:
                dm_embed = discord.Embed(
                    title="⚠️ You Have Been Warned",
                    color=0xFFA500,  # Orange
                    timestamp=datetime.utcnow()
                )
                dm_embed.add_field(name="Server", value=interaction.guild.name, inline=False)
                dm_embed.add_field(name="Reason", value=reason, inline=False)
                dm_embed.add_field(name="Warning ID", value=str(warn_id), inline=True)
                dm_embed.set_footer(text="Please adhere to the server rules to avoid further actions.")
                await user.send(embed=dm_embed)
            except discord.Forbidden:
                self.bot.logger.warning(f"Could not send DM to {user}.")

            # Check if the warning count triggers any automatic actions
            warning_count = await self.db.count_warnings(user_id=user.id, server_id=interaction.guild.id)
            timeout_actions = {
                3: timedelta(minutes=10),
                6: timedelta(hours=24)
            }

            if warning_count in timeout_actions:
                duration = timeout_actions[warning_count]
                await user.timeout(duration, reason=f"Reached {warning_count} warnings via /warn command")
                duration_str = f"{int(duration.total_seconds() / 60)} minutes" if warning_count == 3 else "24 hours"
                timeout_notice = (
                    f"🚫 {user.mention} has been timed out for {duration_str} due to accumulating {warning_count} warnings."
                )
                system_channel = interaction.guild.system_channel
                if system_channel:
                    await system_channel.send(timeout_notice)

                # Log the timeout action if logging is enabled
                server_settings = await self.get_server_settings(interaction.guild.id)
                if server_settings.get('automod_logging_enabled'):
                    log_channel_id = server_settings.get('automod_log_channel_id')
                    if log_channel_id:
                        log_channel = interaction.guild.get_channel(int(log_channel_id))
                        if log_channel:
                            log_embed = discord.Embed(
                                title="🚨 User Timeout",
                                color=0xFFA500,  # Orange
                                timestamp=datetime.utcnow()
                            )
                            log_embed.add_field(name="User", value=user.mention, inline=True)
                            log_embed.add_field(name="Action", value="Accumulated Warnings via /warn command", inline=True)
                            log_embed.add_field(name="Duration", value=duration_str, inline=True)
                            log_embed.add_field(name="Reason", value=f"Reached {warning_count} warnings.\n||No specific reason provided.||", inline=False)
                            log_embed.set_footer(text=f"User ID: {user.id}")
                            await log_channel.send(embed=log_embed)

        except Exception as e:
            self.bot.logger.error(f"Failed to issue warning to {user}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while issuing the warning.",
                color=0x8B0000,  # Dark red
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="warns", description="View all warnings for a user.")
    @app_commands.describe(user="The user to view warnings for.")
    @app_commands.check(is_admin_or_owner)
    async def warns(self, interaction: discord.Interaction, user: discord.Member):
        """
        Retrieves and displays all warnings for a specified user.

        :param interaction: The command interaction.
        :param user: The user to view warnings for.
        """
        await interaction.response.defer(ephemeral=True)

        try:
            warnings = await self.db.get_warnings(user_id=user.id, server_id=interaction.guild.id)
        except Exception as e:
            self.bot.logger.error(f"Failed to retrieve warnings for {user}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while fetching warnings.",
                color=0x8B0000,  # Dark red
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if warnings:
            if len(warnings) > 7:
                view = WarningsView(warnings, user)
                embed = view.create_embed()
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                embed = discord.Embed(
                    title=f"Warnings for {user}",
                    color=0xFF0000,  # Red
                    timestamp=datetime.utcnow()
                )
                for warn in warnings:
                    warn_id, reason, moderator_id, timestamp = warn  # Unpack the tuple
                    embed.add_field(
                        name=f"Warning ID: {warn_id}",
                        value=(
                            f"**Reason:** {reason}\n"
                            f"**Moderator:** <@{moderator_id}>\n"
                            f"**Date:** <t:{int(timestamp)}:F>"
                        ),
                        inline=False,
                    )
                await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="No Warnings Found",
                description=f"{user.mention} has no recorded warnings.",
                color=0x00FF00,  # Green
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Clear all warnings for a user.")
    @app_commands.describe(user="The user to clear warnings for.")
    @app_commands.check(is_admin_or_owner)
    async def clearwarnings(self, interaction: discord.Interaction, user: discord.Member):
        """
        Clears all warnings for a specified user.

        :param interaction: The command interaction.
        :param user: The user to clear warnings for.
        """
        await interaction.response.defer(ephemeral=True)

        try:
            await self.db.clear_all_warnings(user_id=user.id, server_id=interaction.guild.id)
            embed = discord.Embed(
                title="✅ Warnings Cleared",
                description=f"All warnings for {user.mention} have been cleared.",
                color=0x00FF00,  # Green
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            self.bot.logger.error(f"Failed to clear warnings for {user}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while clearing warnings.",
                color=0x8B0000,  # Dark red
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarn", description="Clear a specific warning for a user.")
    @app_commands.describe(user="The user to clear warning for.", warn_id="The ID of the warning to clear.")
    @app_commands.check(is_admin_or_owner)
    async def clearwarn(self, interaction: discord.Interaction, user: discord.Member, warn_id: int):
        """
        Clears a specific warning for a specified user.

        :param interaction: The command interaction.
        :param user: The user to clear warning for.
        :param warn_id: The ID of the warning to clear.
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # Attempt to remove the warning
            result = await self.db.remove_warn(warn_id=warn_id, user_id=user.id, server_id=interaction.guild.id)
            if result:
                embed = discord.Embed(
                    title="✅ Warning Removed",
                    description=f"Warning ID {warn_id} for {user.mention} has been removed.",
                    color=0x00FF00,  # Green
                    timestamp=datetime.utcnow()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="❌ Warning Not Found",
                    description=f"No warning with ID {warn_id} found for {user.mention}.",
                    color=0x8B0000,  # Dark red
                    timestamp=datetime.utcnow()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            self.bot.logger.error(f"Failed to remove warning ID {warn_id} for {user}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while removing the warning.",
                color=0x8B0000,  # Dark red
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """
        Handles errors for all application commands in this cog.
        """
        # Ignore already handled errors
        if hasattr(error, "handled") and error.handled:
            return

        embed = discord.Embed(
            title="❌ Error",
            description="An unexpected error occurred while processing the command.",
            color=0x8B0000,  # Dark red color
            timestamp=datetime.utcnow()
        )

        if isinstance(error, app_commands.MissingPermissions):
            embed.description = "You do not have the required permissions to use this command."
        elif isinstance(error, app_commands.MissingRequiredArgument):
            embed.description = "Missing arguments. Please check the command usage."
        elif isinstance(error, app_commands.CommandOnCooldown):
            embed.description = f"This command is on cooldown. Please try again after {error.retry_after:.2f} seconds."
        elif isinstance(error, app_commands.CheckFailure):
            embed.description = "You do not meet the requirements to use this command."
        else:
            # For unhandled errors, log the exception details for debugging
            self.bot.logger.error(f"Unhandled error in command {interaction.command}: {error}")
            embed.description = f"An unexpected error occurred: {error}"

        # Send the embed as an ephemeral message
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

# Setup function to add the cog to the bot
async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
