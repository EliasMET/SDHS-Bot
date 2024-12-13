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
    """
    A simple paginated view for displaying warnings.
    """
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
            # warn: (user_id, server_id, moderator_id, reason, created_at, id)
            warn_id = warn[5]
            reason = warn[3]
            moderator_id = warn[2]
            timestamp_val = int(warn[4])
            embed.add_field(
                name=f"Warning ID: {warn_id}",
                value=(
                    f"**Reason:** {reason}\n"
                    f"**Moderator:** <@{moderator_id}>\n"
                    f"**Date:** <t:{timestamp_val}:F>"
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


def is_warning_expired(timestamp_val: int, days: int = 2) -> bool:
    """
    Checks if a warning (given its unix timestamp) is expired.
    Warnings older than 'days' are considered expired.
    """
    warning_time = datetime.utcfromtimestamp(timestamp_val)
    return (datetime.utcnow() - warning_time) > timedelta(days=days)


class AutoMod(commands.Cog):
    """
    AutoMod Cog
    Provides automated moderation features such as warning users,
    monitoring messages for prohibited content, and handling timeouts.

    Version: 1.6.1
    Changes:
    - Enhanced error messages for permission issues in /warn command.
    - When a user mentions a protected user:
        - Counts as a warning.
        - Logs the timeout action but does NOT log the warning to the log channel.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = None

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

        self.server_settings_cache = {}

    async def cog_load(self):
        """
        Initialize the cog by setting up the database and caching the owner_id.
        """
        self.db = self.bot.database
        if not self.db:
            self.bot.logger.error("DatabaseManager is not initialized in the bot.")
            raise ValueError("DatabaseManager is not initialized in the bot.")

        if not hasattr(self.bot, 'owner_id'):
            app_info = await self.bot.application_info()
            self.bot.owner_id = app_info.owner.id

    def cog_unload(self):
        self.expire_warnings_task.cancel()
        self.load_profanity_list_task.cancel()

    async def handle_message_violation(self, message: discord.Message, reason: str, log_warn: bool = True):
        """
        Handles violating messages by deleting them, warning the user,
        and optionally timing them out if they hit warning thresholds.
        Logs the violation to the log channel if configured and log_warn is True.
        """
        try:
            await message.delete()

            # Add a warning to the DB
            warn_id = await self.db.add_warn(
                user_id=message.author.id,
                server_id=message.guild.id,
                moderator_id=self.bot.user.id,
                reason=reason
            )

            # Notify the user in the channel
            warning_msg = (
                f"{message.author.mention}, your message violated the server rules.\n"
                f"**Reason:** {reason}"
            )
            moderation_message = await message.channel.send(warning_msg)

            # Fetch all warnings and filter out expired
            all_warnings = await self.db.get_warnings(
                user_id=message.author.id, server_id=message.guild.id
            )
            non_expired_warnings = [
                w for w in all_warnings
                if not is_warning_expired(int(w[4]))
            ]
            warning_count = len(non_expired_warnings)

            server_settings = await self.get_server_settings(message.guild.id)
            automod_mute_duration = server_settings.get('automod_mute_duration', 3600)
            if warning_count % 3 == 0 and warning_count > 0:
                duration = timedelta(seconds=automod_mute_duration)
                await message.author.timeout(duration, reason=f"Reached {warning_count} warnings")
                duration_str = str(duration)
                timeout_notice = (
                    f"🚫 {message.author.mention} has been timed out for {duration_str} due to accumulating {warning_count} warnings."
                )
                await message.channel.send(timeout_notice)

            # Delete the moderation message after some time for clutter reduction
            await asyncio.sleep(10)
            await moderation_message.delete()

            # Log the violation if automod logging is enabled and log_warn is True
            if log_warn and server_settings.get('automod_logging_enabled'):
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
                        log_embed.add_field(name="Offending Message", value=f"||{message.content}||", inline=False)
                        log_embed.set_footer(text=f"User ID: {message.author.id} | Warn ID: {warn_id}")
                        await log_channel.send(embed=log_embed)
                else:
                    self.bot.logger.warning(f"'automod_log_channel_id' not set for guild {message.guild.id}.")

            self.bot.logger.info(
                f"Handled violating message from {message.author} (ID:{message.author.id}) with reason: {reason}. "
                f"Warnings (non-expired): {warning_count}, Message: '{message.content}'"
            )
        except Exception as e:
            self.bot.logger.error(f"Failed to handle message violation: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Main entry point for message checks. Only acts on user messages,
        checks automod status, protected users, exempt roles, and other conditions.
        Logs violations but does not log every allowed message.
        """
        if message.author.bot:
            return

        server_settings = await self.get_server_settings(message.guild.id)
        # If automod disabled, do nothing
        if not server_settings.get('automod_enabled', True):
            return

        content = message.content
        exempt_roles = await self.db.get_automod_exempt_roles(message.guild.id)
        protected_users = await self.db.get_protected_users(message.guild.id)
        mentioned_protected = [u for u in protected_users if u in [m.id for m in message.mentions]]

        # Check if user can bypass automod (owner/admin)
        can_bypass_general = await self.can_bypass_general_automod(message.author)

        # Protected user mention handling
        if mentioned_protected and not await self.is_owner(message.author):
            has_exempt_role = any(role.id in exempt_roles for role in message.author.roles)
            if not has_exempt_role:
                # User mentions protected without exemption
                # Timeout the user and issue a warn without logging the warn
                automod_mute_duration = server_settings.get('automod_mute_duration', 3600)
                duration = timedelta(seconds=automod_mute_duration)
                try:
                    # Handle the violation without logging the warn
                    await self.handle_message_violation(
                        message,
                        reason="Mentioned a protected user without required roles.",
                        log_warn=False  # Do not log the warn to the log channel
                    )

                    # Log the timeout action separately
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
                                log_embed.add_field(name="Duration", value=str(duration), inline=True)
                                log_embed.add_field(name="Message Content", value=f"||{message.content}||", inline=False)
                                log_embed.set_footer(text=f"User ID: {message.author.id}")
                                await log_channel.send(embed=log_embed)
                            else:
                                self.bot.logger.error(f"Log channel with ID {log_channel_id} not found in guild {message.guild.id}.")
                        else:
                            self.bot.logger.warning(f"'automod_log_channel_id' not set for guild {message.guild.id}.")
                    await asyncio.sleep(10)
                    # The moderation message was already deleted in handle_message_violation
                    # So no need to delete it here
                    self.bot.logger.info(
                        f"User {message.author} (ID:{message.author.id}) timed out for mentioning protected user(s) "
                        f"without exemption. Duration: {duration}, Message: '{message.content}'"
                    )
                except discord.Forbidden:
                    self.bot.logger.error(f"Missing permissions to timeout user {message.author.id}.")
                except Exception as e:
                    self.bot.logger.error(f"Failed to timeout user {message.author.id}: {e}")
                return
            # If user is owner or has exempt role, just ignore

        # If can bypass general automod (owner/admin), do nothing further
        if can_bypass_general:
            return

        # Check against prohibited content if not bypassed
        try:
            if self.roblox_group_regex.search(content):
                await self.handle_message_violation(message, "Posting Roblox group links.")
            elif self.discord_invite_regex.search(content):
                await self.handle_message_violation(message, "Posting Discord invite links.")
            elif self.profanity_pattern and self.profanity_pattern.search(content):
                await self.handle_message_violation(message, "Using prohibited language.")
            # If none matched, no action is taken (and no logging of every message)
        except Exception as e:
            self.bot.logger.error(f"Error during AutoMod checks for message from {message.author}: {e}")

    async def get_server_settings(self, guild_id: int):
        """
        Retrieves and caches server settings to reduce DB calls.
        """
        if guild_id in self.server_settings_cache:
            return self.server_settings_cache[guild_id]

        try:
            settings = await self.db.get_server_settings(guild_id)
            self.server_settings_cache[guild_id] = settings
            return settings
        except Exception as e:
            self.bot.logger.error(f"Failed to retrieve server settings for guild {guild_id}: {e}")
            return {}

    async def is_owner(self, member: discord.Member) -> bool:
        """
        Checks if a member is the bot owner.
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
        Determines if a member can bypass general automod checks.
        This applies to the bot owner and server administrators.
        """
        if await self.is_owner(member):
            return True
        return member.guild_permissions.administrator

    @tasks.loop(minutes=10)
    async def expire_warnings_task(self):
        """
        Periodically checks for expired warnings.
        Warnings are no longer removed from the DB; they remain stored but are ignored if expired.
        """
        # Do not remove warnings anymore, just log that we are checking
        self.bot.logger.debug("Checked expired warnings, but not removing them anymore.")

    @tasks.loop(count=1)
    async def load_profanity_list_task(self):
        """
        Loads a list of profane words from a remote source and compiles a regex pattern.
        """
        url = "https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/en"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        text = await response.text()
                        self.profanity_list = [word.strip() for word in text.splitlines() if word.strip()]
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
        Allows administrators or the bot owner to manually warn a user.
        Automatically times out the user if they hit certain warning thresholds.
        """
        await interaction.response.defer(ephemeral=True)

        # Prevent self-warning and warning the owner or higher/equal role members
        if user.id == self.bot.user.id:
            embed = discord.Embed(
                title="⚠️ Warning Issuance Failed",
                description="I cannot warn myself.",
                color=0x8B0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if user.id == interaction.guild.owner_id:
            embed = discord.Embed(
                title="⚠️ Warning Issuance Failed",
                description="You cannot warn the server owner.",
                color=0x8B0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if user.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            embed = discord.Embed(
                title="⚠️ Warning Issuance Failed",
                description="You cannot warn a member with equal or higher roles.",
                color=0x8B0000
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

            # Acknowledge the moderator
            embed = discord.Embed(
                title="✅ Warning Issued",
                color=0x00FF00,
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="User", value=user.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Warning ID", value=str(warn_id), inline=True)
            embed.set_footer(text=f"Moderator: {interaction.user} (ID: {interaction.user.id})")
            await interaction.followup.send(embed=embed, ephemeral=True)

            # Notify the warned user via DM
            try:
                dm_embed = discord.Embed(
                    title="⚠️ You Have Been Warned",
                    color=0xFFA500,
                    timestamp=datetime.utcnow()
                )
                dm_embed.add_field(name="Server", value=interaction.guild.name, inline=False)
                dm_embed.add_field(name="Reason", value=reason, inline=False)
                dm_embed.add_field(name="Warning ID", value=str(warn_id), inline=True)
                dm_embed.set_footer(text="Please adhere to the server rules to avoid further actions.")
                await user.send(embed=dm_embed)
            except discord.Forbidden:
                self.bot.logger.warning(f"Could not DM {user} about their warning.")

            # Fetch all warnings and filter out expired
            all_warnings = await self.db.get_warnings(user_id=user.id, server_id=interaction.guild.id)
            non_expired_warnings = [
                w for w in all_warnings
                if not is_warning_expired(int(w[4]))
            ]
            warning_count = len(non_expired_warnings)

            server_settings = await self.get_server_settings(interaction.guild.id)
            automod_mute_duration = server_settings.get('automod_mute_duration', 3600)

            if warning_count % 3 == 0 and warning_count > 0:
                duration = timedelta(seconds=automod_mute_duration)
                await user.timeout(duration, reason=f"Reached {warning_count} warnings via /warn command")
                duration_str = str(duration)
                timeout_notice = (
                    f"🚫 {user.mention} has been timed out for {duration_str} due to accumulating {warning_count} warnings."
                )
                system_channel = interaction.guild.system_channel
                if system_channel:
                    await system_channel.send(timeout_notice)

                # Log timeout if enabled
                if server_settings.get('automod_logging_enabled'):
                    log_channel_id = server_settings.get('automod_log_channel_id')
                    if log_channel_id:
                        log_channel = interaction.guild.get_channel(int(log_channel_id))
                        if log_channel:
                            log_embed = discord.Embed(
                                title="🚨 User Timeout",
                                color=0xFFA500,
                                timestamp=datetime.utcnow()
                            )
                            log_embed.add_field(name="User", value=user.mention, inline=True)
                            log_embed.add_field(name="Action", value="Accumulated Warnings via /warn command", inline=True)
                            log_embed.add_field(name="Duration", value=duration_str, inline=True)
                            log_embed.add_field(name="Reason", value=f"Reached {warning_count} warnings.", inline=False)
                            log_embed.set_footer(text=f"User ID: {user.id}")
                            await log_channel.send(embed=log_embed)
                        else:
                            self.bot.logger.error(f"Log channel with ID {log_channel_id} not found in guild {interaction.guild.id}.")
                    else:
                        self.bot.logger.warning(f"'automod_log_channel_id' not set for guild {interaction.guild.id}.")

        except Exception as e:
            self.bot.logger.error(f"Failed to issue warning to {user}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while issuing the warning.",
                color=0x8B0000,
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="warns", description="View all warnings for a user.")
    @app_commands.describe(user="The user to view warnings for.")
    @app_commands.check(is_admin_or_owner)
    async def warns(self, interaction: discord.Interaction, user: discord.Member):
        """
        Shows all warnings for a specified user.
        Paginated if there are more than 7 warnings.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            all_warnings = await self.db.get_warnings(user_id=user.id, server_id=interaction.guild.id)
        except Exception as e:
            self.bot.logger.error(f"Failed to retrieve warnings for {user}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while fetching warnings.",
                color=0x8B0000,
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Filter out expired warnings before showing
        warnings = [
            w for w in all_warnings
            if not is_warning_expired(int(w[4]))
        ]

        if warnings:
            if len(warnings) > 7:
                view = WarningsView(warnings, user)
                embed = view.create_embed()
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                embed = discord.Embed(
                    title=f"Warnings for {user}",
                    color=0xFF0000,
                    timestamp=datetime.utcnow()
                )
                for w in warnings:
                    warn_id = w[5]
                    reason = w[3]
                    moderator_id = w[2]
                    timestamp_val = int(w[4])
                    embed.add_field(
                        name=f"Warning ID: {warn_id}",
                        value=(
                            f"**Reason:** {reason}\n"
                            f"**Moderator:** <@{moderator_id}>\n"
                            f"**Date:** <t:{timestamp_val}:F>"
                        ),
                        inline=False,
                    )
                await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="No Warnings Found",
                description=f"{user.mention} has no recorded non-expired warnings.",
                color=0x00FF00,
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Clear all warnings for a user.")
    @app_commands.describe(user="The user to clear warnings for.")
    @app_commands.check(is_admin_or_owner)
    async def clearwarnings(self, interaction: discord.Interaction, user: discord.Member):
        """
        Clears all warnings for a specified user.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            removed_count = await self.db.clear_all_warnings(user_id=user.id, server_id=interaction.guild.id)
            embed = discord.Embed(
                title="✅ Warnings Cleared",
                description=f"All warnings for {user.mention} have been cleared. ({removed_count} removed)",
                color=0x00FF00,
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            self.bot.logger.error(f"Failed to clear warnings for {user}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while clearing warnings.",
                color=0x8B0000,
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarn", description="Clear a specific warning for a user.")
    @app_commands.describe(user="The user to clear warning for.", warn_id="The ID of the warning to clear.")
    @app_commands.check(is_admin_or_owner)
    async def clearwarn(self, interaction: discord.Interaction, user: discord.Member, warn_id: int):
        """
        Clears a specific warning by its ID for a specified user.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.db.remove_warn(warn_id=warn_id, user_id=user.id, server_id=interaction.guild.id)
            if result:
                embed = discord.Embed(
                    title="✅ Warning Removed",
                    description=f"Warning ID {warn_id} for {user.mention} has been removed.",
                    color=0x00FF00,
                    timestamp=datetime.utcnow()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="❌ Warning Not Found",
                    description=f"No warning with ID {warn_id} found for {user.mention}.",
                    color=0x8B0000,
                    timestamp=datetime.utcnow()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            self.bot.logger.error(f"Failed to remove warning ID {warn_id} for {user}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while removing the warning.",
                color=0x8B0000,
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """
        Handles errors for all application commands in this cog.
        """
        if hasattr(error, "handled") and error.handled:
            return

        embed = discord.Embed(
            title="❌ Error",
            description="An unexpected error occurred while processing the command.",
            color=0x8B0000,
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
            self.bot.logger.error(f"Unhandled error in command {interaction.command}: {error}")
            embed.description = f"An unexpected error occurred: {error}"

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


# Setup function to add the cog to the bot
async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
