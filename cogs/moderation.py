import os
import re
import math
import aiohttp
import asyncio
import discord
from datetime import datetime, timedelta
from discord.ext import commands
from discord import app_commands

#
# Helper permission checks
#
async def is_admin_or_owner(interaction: discord.Interaction) -> bool:
    """
    Check if the user is the guild owner or has Administrator permissions.
    """
    return (
        interaction.user.guild_permissions.administrator
        or interaction.user.id == interaction.guild.owner_id
    )

async def is_moderator(interaction: discord.Interaction) -> bool:
    """
    Check if the user is the bot owner, has Administrator permissions,
    or has one of the allowed moderator roles (from DB).
    """
    bot = interaction.client
    if not hasattr(bot, 'owner_id'):
        app_info = await bot.application_info()
        bot.owner_id = app_info.owner.id

    if interaction.user.id == bot.owner_id:
        return True
    if interaction.user.guild_permissions.administrator:
        return True

    allowed_roles = await bot.database.get_moderation_allowed_roles(interaction.guild.id)
    user_roles = [role.id for role in interaction.user.roles]
    if any(role_id in allowed_roles for role_id in user_roles):
        return True

    raise app_commands.MissingPermissions(['administrator'])

#
# Helper function to check if a warning is expired
#
def is_warning_expired(timestamp_val: int, days: int = 2) -> bool:
    """
    Check if a warning is older than `days` days.
    """
    warning_time = datetime.utcfromtimestamp(timestamp_val)
    return (datetime.utcnow() - warning_time) > timedelta(days=days)

#
# Simple pagination for warnings
#
class WarningsView(discord.ui.View):
    """
    A Discord UI View to paginate through a user's warnings.
    """
    def __init__(self, warnings, user, per_page=7):
        super().__init__(timeout=180)
        self.warnings = warnings
        self.user = user
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = math.ceil(len(warnings) / per_page)

        self.previous_button = discord.ui.Button(
            label="Previous", style=discord.ButtonStyle.blurple, disabled=True
        )
        self.next_button = discord.ui.Button(
            label="Next", style=discord.ButtonStyle.blurple, disabled=(self.total_pages <= 1)
        )
        self.previous_button.callback = self.previous_page
        self.next_button.callback = self.next_page

        self.add_item(self.previous_button)
        self.add_item(self.next_button)

    def create_embed(self) -> discord.Embed:
        """
        Build an embed showing a subset of warnings for the current page.
        """
        start = self.current_page * self.per_page
        end = start + self.per_page

        embed = discord.Embed(
            title=f"Warnings for {self.user}",
            color=0xFF0000,
            description=f"Page {self.current_page + 1}/{self.total_pages}",
            timestamp=datetime.utcnow(),
        )

        for warn in self.warnings[start:end]:
            moderator_id = warn[2]
            reason = warn[3]
            timestamp_val = int(warn[4])
            warn_id = warn[5]

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
        self.previous_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)


class Moderation(commands.Cog, name="moderation"):
    """
    A Cog for general moderation commands:
    - Ban
    - Kick
    - Timeout
    - Lock/Unlock channels (single & mass)
    - Warnings management
    - Global bans
    - Case lookup
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Create an in-memory lock to synchronize global_ban calls
        self.global_ban_lock = asyncio.Lock()

    async def cog_load(self):
        self.db = self.bot.database
        if not self.db:
            self.bot.logger.error("DatabaseManager is not initialized in the bot.")
            raise ValueError("DatabaseManager is not initialized in the bot.")

        if not hasattr(self.bot, 'owner_id'):
            app_info = await self.bot.application_info()
            self.bot.owner_id = app_info.owner.id

        self.bot.logger.info("Moderation Cog loaded successfully.")

    #
    # --------------- Ban Commands ---------------
    #

    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(member="The member to ban.", reason="Reason for banning the member.")
    @app_commands.check(is_moderator)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
        """
        Ban a member from the guild.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            await member.ban(reason=reason, delete_message_days=0)

            # Create a case for this ban
            case_id = await self.db.add_case(
                server_id=interaction.guild.id,
                user_id=member.id,
                moderator_id=interaction.user.id,
                action_type="ban",
                reason=reason
            )

            embed = discord.Embed(
                description=(
                    f"✅ Successfully banned {member.mention}.\n"
                    f"**Reason:** {reason}\n"
                    f"**Case ID:** {case_id}"
                ),
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

            self.bot.logger.info(f"{interaction.user} banned {member} for: {reason}")
            await self.log_action(interaction.guild, "Ban", interaction.user, member, reason)

        except discord.Forbidden:
            embed = discord.Embed(
                description="❌ I do not have permission to ban this member.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.warning(f"Failed to ban {member}: Missing Permissions.")
        except discord.HTTPException as e:
            embed = discord.Embed(
                description=f"❌ Failed to ban member: {e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.error(f"HTTPException while banning {member}: {e}")

    #
    # --------------- Global Ban Commands ---------------
    #

    @app_commands.command(name="global_ban", description="Globally ban a user.")
    @app_commands.describe(user="The user to globally ban.", reason="Reason for the ban.")
    @app_commands.check(is_admin_or_owner)
    async def global_ban(self, interaction: discord.Interaction, user: discord.User, reason: str = "No reason provided."):
        """
        Globally ban a user across all relevant servers (via Bloxlink).
        """
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        bloxlink_api_key = os.getenv("BLOXLINK_TOKEN")

        if not bloxlink_api_key:
            embed = discord.Embed(
                description="❌ BLOXLINK_TOKEN not set in environment variables.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.error("BLOXLINK_TOKEN is missing.")
            return

        try:
            async with self.global_ban_lock:
                bloxlink_url = f"https://api.blox.link/v4/public/guilds/{guild_id}/discord-to-roblox/{user.id}"
                headers = {"Authorization": bloxlink_api_key}
                async with aiohttp.ClientSession() as session:
                    async with session.get(bloxlink_url, headers=headers) as bloxlink_response:
                        bloxlink_data = await bloxlink_response.json()
                        if bloxlink_response.status != 200 or "robloxID" not in bloxlink_data:
                            raise RuntimeError(
                                f"Bloxlink API Error: Status {bloxlink_response.status}, Data: {bloxlink_data}"
                            )
                        roblox_user_id = bloxlink_data["robloxID"]
                        self.bot.logger.info(
                            f"Fetched Roblox User ID {roblox_user_id} for {user} via Bloxlink."
                        )

                        # Optional: fetch Roblox username
                        roblox_user_url = f"https://users.roblox.com/v1/users/{roblox_user_id}"
                        async with session.get(roblox_user_url) as roblox_user_response:
                            roblox_user_data = await roblox_user_response.json()
                            roblox_username = roblox_user_data.get("name", "Unknown")

                # Actually record the global ban in DB
                await self.db.add_global_ban(user.id, roblox_user_id, reason, interaction.user.id)

            embed = discord.Embed(
                description=(
                    f"✅ Successfully globally banned {user.mention}.\n"
                    f"**Reason:** {reason}\n"
                    f"**Roblox Username:** {roblox_username}\n"
                    f"**Roblox ID:** {roblox_user_id}"
                ),
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

            self.bot.logger.info(
                f"{interaction.user} globally banned {user} (Roblox ID: {roblox_user_id}), reason: {reason}"
            )

        except Exception as e:
            embed = discord.Embed(
                description=f"❌ Failed to globally ban user: {e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.error(f"Exception while globally banning {user}: {e}")

    @app_commands.command(name="global_unban", description="Remove a global ban from a user.")
    @app_commands.describe(user="The user to remove the global ban from.")
    @app_commands.check(is_admin_or_owner)
    async def global_unban(self, interaction: discord.Interaction, user: discord.User):
        """
        Lift a global ban from the specified user.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            removed = await self.db.remove_global_ban(user.id)
            if removed:
                embed = discord.Embed(
                    description=f"✅ Successfully removed global ban for {user.mention}.",
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                self.bot.logger.info(f"{interaction.user} removed global ban for {user}.")
            else:
                embed = discord.Embed(
                    description="❌ No existing global ban found for this user.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                description=f"❌ Failed to remove global ban: {e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.error(f"Exception while removing global ban for {user}: {e}")

    #
    # --------------- Warnings Commands ---------------
    #

    @app_commands.command(name="warns", description="View warnings for a user.")
    @app_commands.describe(
        user="The user to view warnings for.",
        show_expired="Whether to include expired warnings."
    )
    @app_commands.check(is_moderator)
    async def warns(self, interaction: discord.Interaction, user: discord.Member, show_expired: bool = False):
        """
        Display warnings for a given user, optionally excluding expired ones.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            all_warnings = await self.db.get_warnings(user_id=user.id, server_id=interaction.guild.id)
            if not show_expired:
                all_warnings = [w for w in all_warnings if not is_warning_expired(int(w[4]))]

            if not all_warnings:
                embed = discord.Embed(
                    description=f"No warnings found for {user.mention}.",
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            view = WarningsView(all_warnings, user)
            embed = view.create_embed()
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            self.bot.logger.info(
                f"{interaction.user} viewed warnings for {user} (show_expired={show_expired})."
            )
        except Exception as e:
            self.bot.logger.error(f"Failed to retrieve warnings for {user}: {e}")
            embed = discord.Embed(
                description="An error occurred while retrieving warnings.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    #
    # --------------- Kick Command ---------------
    #

    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="The member to kick.", reason="Reason for kicking the member.")
    @app_commands.check(is_moderator)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
        """
        Kick a member from the guild.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            await member.kick(reason=reason)

            # Create a case for this kick
            case_id = await self.db.add_case(
                server_id=interaction.guild.id,
                user_id=member.id,
                moderator_id=interaction.user.id,
                action_type="kick",
                reason=reason
            )

            embed = discord.Embed(
                description=(
                    f"✅ Successfully kicked {member.mention}.\n"
                    f"**Reason:** {reason}\n"
                    f"**Case ID:** {case_id}"
                ),
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

            self.bot.logger.info(f"{interaction.user} kicked {member} for {reason}")
            await self.log_action(interaction.guild, "Kick", interaction.user, member, reason)

        except discord.Forbidden:
            embed = discord.Embed(
                description="❌ I do not have permission to kick this member.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.warning(f"Failed to kick {member}: Missing Permissions.")
        except discord.HTTPException as e:
            embed = discord.Embed(
                description=f"❌ Failed to kick member: {e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.error(f"HTTPException while kicking {member}: {e}")

    #
    # --------------- Timeout Command ---------------
    #

    @app_commands.command(name="timeout", description="Timeout a member for a specified duration.")
    @app_commands.describe(
        member="The member to timeout.",
        duration="Duration (e.g. 10m, 2h, 1d).",
        reason="Reason for the timeout."
    )
    @app_commands.check(is_moderator)
    async def timeout_member(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided."):
        """
        Put a member in timeout for a given duration.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            seconds = self.parse_duration(duration)
            if not seconds:
                raise ValueError("Invalid duration format. Please use 10m, 2h, or 1d.")

            until = discord.utils.utcnow() + timedelta(seconds=seconds)
            await member.timeout(until, reason=reason)

            # Create a case for this timeout
            case_id = await self.db.add_case(
                server_id=interaction.guild.id,
                user_id=member.id,
                moderator_id=interaction.user.id,
                action_type="timeout",
                reason=reason,
                extra={"duration": duration}
            )

            embed = discord.Embed(
                description=(
                    f"✅ {member.mention} has been timed out for {duration}.\n"
                    f"**Reason:** {reason}\n"
                    f"**Case ID:** {case_id}"
                ),
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

            self.bot.logger.info(f"{interaction.user} timed out {member} for {duration}. Reason: {reason}")
            await self.log_action(interaction.guild, "Timeout", interaction.user, member, reason, duration)

        except ValueError as ve:
            embed = discord.Embed(
                description=f"❌ {ve}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.warning(f"Timeout error: {ve}")
        except discord.Forbidden:
            embed = discord.Embed(
                description="❌ I do not have permission to timeout this member.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.warning(f"Failed to timeout {member}: Missing permissions.")
        except discord.HTTPException as e:
            embed = discord.Embed(
                description=f"❌ Failed to timeout member: {e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.error(f"HTTPException while timing out {member}: {e}")

    def parse_duration(self, duration_str: str) -> int:
        """
        Parse a human-readable duration like '10m', '2h', '1d' into seconds.
        """
        pattern = re.compile(r'^(?P<value>\d+)(?P<unit>[mhd])$')
        match = pattern.match(duration_str.lower())
        if not match:
            return None

        value = int(match.group('value'))
        unit = match.group('unit')

        if unit == 'm':
            return value * 60
        elif unit == 'h':
            return value * 3600
        elif unit == 'd':
            return value * 86400
        return None

    #
    # --------------- Lock/Unlock Channel Commands ---------------
    #

    @app_commands.command(name="lock", description="Lock a specific text channel.")
    @app_commands.describe(channel="The channel to lock.", reason="Reason for locking.")
    @app_commands.check(is_moderator)
    async def lock_channel(self, interaction: discord.Interaction, channel: discord.TextChannel = None, reason: str = "No reason provided."):
        """
        Lock a channel (deny @everyone Send Messages) if not already locked.
        """
        await interaction.response.defer(ephemeral=True)
        channel = channel or interaction.channel

        try:
            overwrite = channel.overwrites_for(interaction.guild.default_role)
            if overwrite.send_messages is False:
                # Already locked
                embed = discord.Embed(
                    description=f"❌ {channel.mention} is already locked.",
                    color=discord.Color.red()
                )
                return await interaction.followup.send(embed=embed, ephemeral=True)

            overwrite.send_messages = False
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)

            # Create a case for channel lock
            case_id = await self.db.add_case(
                server_id=interaction.guild.id,
                user_id=interaction.user.id,  # The user performing the lock
                moderator_id=interaction.user.id,
                action_type="channel_lock",
                reason=reason,
                extra={"channel_id": channel.id, "channel_name": channel.name}
            )

            # Send an embed in the channel to let users know
            lock_embed = discord.Embed(title="🔒 Channel Locked", color=discord.Color.red())
            lock_embed.add_field(name="Locked By", value=interaction.user.mention, inline=True)
            lock_embed.add_field(name="Case ID", value=case_id, inline=True)
            lock_embed.add_field(name="Reason", value=reason, inline=False)
            await channel.send(embed=lock_embed)

            # Send ephemeral confirmation
            embed = discord.Embed(
                description=(
                    f"✅ {channel.mention} locked.\n"
                    f"**Reason:** {reason}\n"
                    f"**Case ID:** {case_id}"
                ),
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

            self.bot.logger.info(f"{interaction.user} locked {channel} for {reason}")
            await self.log_channel_action(interaction.guild, "Channel Lock", interaction.user, channel, reason)

        except discord.Forbidden:
            embed = discord.Embed(
                description="❌ I do not have permission to lock this channel.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.warning(f"Failed to lock {channel}: Missing permissions.")
        except discord.HTTPException as e:
            embed = discord.Embed(
                description=f"❌ Failed to lock channel: {e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.error(f"HTTPException while locking {channel}: {e}")

    @app_commands.command(name="unlock", description="Unlock a specific text channel.")
    @app_commands.describe(channel="The channel to unlock.", reason="Reason for unlocking.")
    @app_commands.check(is_moderator)
    async def unlock_channel(self, interaction: discord.Interaction, channel: discord.TextChannel = None, reason: str = "No reason provided."):
        """
        Unlock a channel (allow @everyone Send Messages) if not already unlocked.
        """
        await interaction.response.defer(ephemeral=True)
        channel = channel or interaction.channel

        try:
            overwrite = channel.overwrites_for(interaction.guild.default_role)
            if overwrite.send_messages is True or overwrite.send_messages is None:
                # Already unlocked
                embed = discord.Embed(
                    description=f"❌ {channel.mention} is already unlocked.",
                    color=discord.Color.red()
                )
                return await interaction.followup.send(embed=embed, ephemeral=True)

            overwrite.send_messages = True
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)

            # Create a case for channel unlock
            case_id = await self.db.add_case(
                server_id=interaction.guild.id,
                user_id=interaction.user.id,
                moderator_id=interaction.user.id,
                action_type="channel_unlock",
                reason=reason,
                extra={"channel_id": channel.id, "channel_name": channel.name}
            )

            # Send an embed in the channel to let users know
            unlock_embed = discord.Embed(title="🔓 Channel Unlocked", color=discord.Color.green())
            unlock_embed.add_field(name="Unlocked By", value=interaction.user.mention, inline=True)
            unlock_embed.add_field(name="Case ID", value=case_id, inline=True)
            unlock_embed.add_field(name="Reason", value=reason, inline=False)
            await channel.send(embed=unlock_embed)

            # Send ephemeral confirmation
            embed = discord.Embed(
                description=(
                    f"✅ {channel.mention} unlocked.\n"
                    f"**Reason:** {reason}\n"
                    f"**Case ID:** {case_id}"
                ),
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

            self.bot.logger.info(f"{interaction.user} unlocked {channel}. Reason: {reason}")
            await self.log_channel_action(interaction.guild, "Channel Unlock", interaction.user, channel, reason)

        except discord.Forbidden:
            embed = discord.Embed(
                description="❌ I do not have permission to unlock this channel.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.warning(f"Failed to unlock {channel}: Missing permissions.")
        except discord.HTTPException as e:
            embed = discord.Embed(
                description=f"❌ Failed to unlock channel: {e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.error(f"HTTPException while unlocking {channel}: {e}")

    @app_commands.command(name="lockall", description="Lock all text channels in the server.")
    @app_commands.describe(reason="Reason for locking all channels.")
    @app_commands.check(is_moderator)
    async def lock_all_channels(self, interaction: discord.Interaction, reason: str = "No reason provided."):
        """
        Lock all text channels in the guild (deny @everyone Send Messages),
        skipping channels already locked, and creating a single case for the operation.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            # Create one "mass lock" case for the entire operation
            case_id = await self.db.add_case(
                server_id=interaction.guild.id,
                user_id=interaction.user.id,
                moderator_id=interaction.user.id,
                action_type="mass_channel_lock",
                reason=reason,
                extra={}
            )

            newly_locked = []
            for channel in interaction.guild.text_channels:
                overwrite = channel.overwrites_for(interaction.guild.default_role)

                # Skip if already locked
                if overwrite.send_messages is False:
                    continue

                overwrite.send_messages = False
                await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
                newly_locked.append(channel)

                # Send a lock embed in each newly locked channel
                lock_embed = discord.Embed(title="🔒 Channel Locked", color=discord.Color.red())
                lock_embed.add_field(name="Locked By", value=interaction.user.mention, inline=True)
                lock_embed.add_field(name="Case ID", value=case_id, inline=True)
                lock_embed.add_field(name="Reason", value=reason, inline=False)
                await channel.send(embed=lock_embed)

            embed = discord.Embed(
                title="Mass Lock Complete",
                color=discord.Color.green(),
                description=(
                    f"Locked {len(newly_locked)} channels.\n"
                    f"**Reason:** {reason}\n"
                    f"**Case ID:** {case_id}"
                ),
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

            self.bot.logger.info(f"{interaction.user} locked {len(newly_locked)} channels. Reason: {reason}")

        except Exception as e:
            embed = discord.Embed(
                description=f"❌ Failed to lock all channels: {e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.error(f"Exception while locking all channels: {e}")

    @app_commands.command(name="unlockall", description="Unlock all text channels in the server.")
    @app_commands.describe(reason="Reason for unlocking all channels.")
    @app_commands.check(is_moderator)
    async def unlock_all_channels(self, interaction: discord.Interaction, reason: str = "No reason provided."):
        """
        Unlock all text channels in the guild (allow @everyone Send Messages),
        skipping channels already unlocked, and creating a single case for the operation.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            # Create one "mass unlock" case for the entire operation
            case_id = await self.db.add_case(
                server_id=interaction.guild.id,
                user_id=interaction.user.id,
                moderator_id=interaction.user.id,
                action_type="mass_channel_unlock",
                reason=reason,
                extra={}
            )

            newly_unlocked = []
            for channel in interaction.guild.text_channels:
                overwrite = channel.overwrites_for(interaction.guild.default_role)

                # If it's None or True, consider it "unlocked" already
                if overwrite.send_messages is True or overwrite.send_messages is None:
                    continue

                overwrite.send_messages = True
                await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
                newly_unlocked.append(channel)

                # Send an unlock embed in each newly unlocked channel
                unlock_embed = discord.Embed(title="🔓 Channel Unlocked", color=discord.Color.green())
                unlock_embed.add_field(name="Unlocked By", value=interaction.user.mention, inline=True)
                unlock_embed.add_field(name="Case ID", value=case_id, inline=True)
                unlock_embed.add_field(name="Reason", value=reason, inline=False)
                await channel.send(embed=unlock_embed)

            embed = discord.Embed(
                title="Mass Unlock Complete",
                color=discord.Color.green(),
                description=(
                    f"Unlocked {len(newly_unlocked)} channels.\n"
                    f"**Reason:** {reason}\n"
                    f"**Case ID:** {case_id}"
                ),
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

            self.bot.logger.info(f"{interaction.user} unlocked {len(newly_unlocked)} channels. Reason: {reason}")

        except Exception as e:
            embed = discord.Embed(
                description=f"❌ Failed to unlock all channels: {e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.error(f"Exception while unlocking all channels: {e}")

    #
    # --------------- Logging & Case Lookup ---------------
    #

    async def log_action(
        self,
        guild: discord.Guild,
        action: str,
        executor: discord.User,
        target: discord.Member,
        reason: str,
        duration: str = None
    ):
        """
        Send an embedded log message to the mod log channel (if set) for user-based actions.
        """
        try:
            log_channel_id = await self.db.get_mod_log_channel(guild.id)
            if not log_channel_id:
                return
            log_channel = guild.get_channel(log_channel_id)
            if not log_channel:
                return

            embed = discord.Embed(
                title=f"📜 {action}",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Executor", value=f"{executor} (ID: {executor.id})", inline=True)
            embed.add_field(name="Target", value=f"{target} (ID: {target.id})" if target else "N/A", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            if duration:
                embed.add_field(name="Duration", value=duration, inline=True)
            embed.set_footer(text=f"Guild: {guild.name} (ID: {guild.id})")

            await log_channel.send(embed=embed)
        except Exception as e:
            self.bot.logger.error(f"Failed to log moderation action: {e}")

    async def log_channel_action(
        self,
        guild: discord.Guild,
        action: str,
        executor: discord.User,
        channel: discord.TextChannel,
        reason: str
    ):
        """
        Send an embedded log message to the mod log channel for channel-based actions (lock/unlock).
        """
        try:
            log_channel_id = await self.db.get_mod_log_channel(guild.id)
            if not log_channel_id:
                return
            log_channel = guild.get_channel(log_channel_id)
            if not log_channel:
                return

            embed = discord.Embed(
                title=f"📜 {action}",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Executor", value=f"{executor} (ID: {executor.id})", inline=True)
            embed.add_field(name="Channel", value=f"{channel.mention} (ID: {channel.id})", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"Guild: {guild.name} (ID: {guild.id})")

            await log_channel.send(embed=embed)
        except Exception as e:
            self.bot.logger.error(f"Failed to log channel moderation action: {e}")

    @app_commands.command(name="case", description="Look up data about a specific case.")
    @app_commands.describe(case_id="The ID of the case to look up (e.g. ABC123).")
    @app_commands.check(is_moderator)
    async def case_lookup(self, interaction: discord.Interaction, case_id: str):
        """
        Look up a specific moderation case by its random string ID.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            doc = await self.db.get_case(interaction.guild.id, case_id)
            if not doc:
                embed = discord.Embed(
                    title="Case Not Found",
                    description=f"No case with ID **{case_id}** found in this server.",
                    color=discord.Color.red()
                )
                return await interaction.followup.send(embed=embed, ephemeral=True)

            user_mention = f"<@{doc['user_id']}>"
            mod_mention = f"<@{doc['moderator_id']}>"
            action_type = doc["action_type"]
            reason = doc["reason"]
            timestamp_iso = doc["timestamp"]
            extra = doc.get("extra", {})

            embed = discord.Embed(
                title=f"Case {doc['case_id']} - {action_type.upper()}",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="User", value=user_mention, inline=True)
            embed.add_field(name="Moderator", value=mod_mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)

            dt_obj = datetime.fromisoformat(timestamp_iso)
            unix_ts = int(dt_obj.timestamp())
            embed.add_field(name="Created At", value=f"<t:{unix_ts}:F>", inline=False)

            # If there is any extra info, display it
            for k, v in extra.items():
                embed.add_field(name=k.capitalize(), value=str(v), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.bot.logger.error(f"Failed to fetch case {case_id} for guild {interaction.guild.id}: {e}")
            embed = discord.Embed(
                title="Error",
                description=f"An error occurred trying to fetch case {case_id}.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    #
    # --------------- Error Handling ---------------
    #

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """
        A common error handler for all app command errors in this Cog.
        """
        embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while processing the command.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        if isinstance(error, app_commands.MissingPermissions):
            embed.description = "You do not have the required permissions to use this command."
        elif isinstance(error, app_commands.CommandInvokeError):
            embed.description = "An error occurred while executing that command."
            self.bot.logger.error(f"CommandInvokeError: {error}")
        else:
            self.bot.logger.error(f"Unhandled error in command {interaction.command}: {error}")
            embed.description = str(error)

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

#
# Register the Cog
#
async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
    bot.logger.info("Moderation Cog has been added to the bot.")