# automod.py

import discord
from discord.ext import commands, tasks
from discord import app_commands

import re
from datetime import datetime, timedelta
import math
import aiohttp
import asyncio
from collections import deque

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
    warning_time = datetime.utcfromtimestamp(timestamp_val)
    return (datetime.utcnow() - warning_time) > timedelta(days=days)

class AutoMod(commands.Cog):
    """
    AutoMod Cog
    Provides automated moderation features.

    Version: Adjusted to use db settings for spam detection.
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

        # Recent messages for spam detection
        self.recent_messages = {}

        # Start background tasks
        self.expire_warnings_task.start()
        self.load_profanity_list_task.start()

        self.server_settings_cache = {}

    async def cog_load(self):
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

    async def handle_message_violation(self, message: discord.Message, reason: str, log_warn: bool = True, delete_message: bool = True):
        try:
            if delete_message:
                await message.delete()

            warn_id = await self.db.add_warn(
                user_id=message.author.id,
                server_id=message.guild.id,
                moderator_id=self.bot.user.id,
                reason=reason
            )

            warning_msg = (
                f"{message.author.mention}, your message violated the server rules.\n"
                f"**Reason:** {reason}"
            )
            moderation_message = await message.channel.send(warning_msg)

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

            await asyncio.sleep(10)
            await moderation_message.delete()

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
                        if delete_message:
                            log_embed.add_field(name="Offending Message", value=f"||{message.content}||", inline=False)
                        else:
                            log_embed.add_field(name="Offending Message", value="(Not Deleted)", inline=False)
                        log_embed.set_footer(text=f"User ID: {message.author.id} | Warn ID: {warn_id}")
                        await log_channel.send(embed=log_embed)

            self.bot.logger.info(
                f"Handled violating message from {message.author} (ID:{message.author.id}) with reason: {reason}. "
                f"Warnings (non-expired): {warning_count}, Message: '{message.content}'"
            )
        except Exception as e:
            self.bot.logger.error(f"Failed to handle message violation: {e}")

    def record_message_for_spam(self, user_id: int, spam_time_window: int):
        now = datetime.utcnow().timestamp()
        if user_id not in self.recent_messages:
            self.recent_messages[user_id] = deque()

        user_deque = self.recent_messages[user_id]
        user_deque.append(now)

        while user_deque and (now - user_deque[0]) > spam_time_window:
            user_deque.popleft()

        return len(user_deque)

    async def spam_check(self, message: discord.Message) -> bool:
        server_settings = await self.get_server_settings(message.guild.id)
        spam_limit = server_settings.get('automod_spam_limit', 5)
        spam_window = server_settings.get('automod_spam_window', 5)

        count = self.record_message_for_spam(message.author.id, spam_window)
        return count > spam_limit

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        server_settings = await self.get_server_settings(message.guild.id)
        if not server_settings.get('automod_enabled', True):
            return

        content = message.content
        exempt_roles = await self.db.get_automod_exempt_roles(message.guild.id)
        protected_users = await self.db.get_protected_users(message.guild.id)
        mentioned_protected = [u for u in protected_users if u in [m.id for m in message.mentions]]

        if mentioned_protected and not await self.is_owner(message.author):
            has_exempt_role = any(role.id in exempt_roles for role in message.author.roles)
            if not has_exempt_role:
                automod_mute_duration = server_settings.get('automod_mute_duration', 3600)
                duration = timedelta(seconds=automod_mute_duration)
                try:
                    await self.handle_message_violation(
                        message,
                        reason="Mentioned a protected user without required roles.",
                        log_warn=False,
                        delete_message=False
                    )
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

                    self.bot.logger.info(
                        f"User {message.author} (ID:{message.author.id}) timed out for mentioning protected user(s) without exemption. "
                        f"Duration: {duration}, Message: '{message.content}'"
                    )
                except discord.Forbidden:
                    self.bot.logger.error(f"Missing permissions to timeout user {message.author.id}.")
                except Exception as e:
                    self.bot.logger.error(f"Failed to timeout user {message.author.id}: {e}")
                return

        if await self.can_bypass_general_automod(message.author):
            return

        try:
            if await self.spam_check(message):
                await self.handle_message_violation(message, "Spamming.")
                return
        except Exception as e:
            self.bot.logger.error(f"Error during spam check for message from {message.author}: {e}")

        try:
            if self.roblox_group_regex.search(content):
                await self.handle_message_violation(message, "Posting Roblox group links.")
            elif self.discord_invite_regex.search(content):
                await self.handle_message_violation(message, "Posting Discord invite links.")
            elif self.profanity_pattern and self.profanity_pattern.search(content):
                await self.handle_message_violation(message, "Using prohibited language.")
        except Exception as e:
            self.bot.logger.error(f"Error during AutoMod checks for message from {message.author}: {e}")

    async def get_server_settings(self, guild_id: int):
        cached = self.server_settings_cache.get(guild_id)
        if cached is not None:
            return cached

        try:
            settings = await self.db.get_server_settings(guild_id)
            self.server_settings_cache[guild_id] = settings
            return settings
        except Exception as e:
            self.bot.logger.error(f"Failed to retrieve server settings for guild {guild_id}: {e}")
            return {}

    async def is_owner(self, member: discord.Member) -> bool:
        if not hasattr(self.bot, 'owner_id'):
            try:
                app_info = await self.bot.application_info()
                self.bot.owner_id = app_info.owner.id
            except Exception as e:
                self.bot.logger.error(f"Failed to fetch application info: {e}")
                return False
        return member.id == self.bot.owner_id

    async def can_bypass_general_automod(self, member: discord.Member) -> bool:
        if await self.is_owner(member):
            return True
        return member.guild_permissions.administrator

    @tasks.loop(minutes=10)
    async def expire_warnings_task(self):
        self.bot.logger.debug("Checked expired warnings (no removal).")

    @tasks.loop(count=1)
    async def load_profanity_list_task(self):
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
        await interaction.response.defer(ephemeral=True)

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
            warn_id = await self.db.add_warn(
                user_id=user.id,
                server_id=interaction.guild.id,
                moderator_id=interaction.user.id,
                reason=reason,
            )

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
        if getattr(error, "handled", False):
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

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))