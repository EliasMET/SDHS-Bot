import os
import re
import math
import aiohttp
import asyncio
import discord
from datetime import datetime, timedelta
from discord.ext import commands
from discord import app_commands

async def is_admin_or_owner(interaction: discord.Interaction) -> bool:
    return (
        interaction.user.guild_permissions.administrator
        or interaction.user.id == interaction.guild.owner_id
    )

async def is_moderator(interaction: discord.Interaction) -> bool:
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

def is_warning_expired(timestamp_val: int, days: int = 2) -> bool:
    warning_time = datetime.utcfromtimestamp(timestamp_val)
    return (datetime.utcnow() - warning_time) > timedelta(days=days)

class WarningsView(discord.ui.View):
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
            label="Next",
            style=discord.ButtonStyle.blurple,
            disabled=(self.total_pages <= 1),
        )
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

    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(member="The member to ban.", reason="Reason for banning the member.")
    @app_commands.check(is_moderator)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
        await interaction.response.defer(ephemeral=True)
        try:
            await member.ban(reason=reason, delete_message_days=0)

            # Random string case ID
            case_id = await self.db.add_case(
                server_id=interaction.guild.id,
                user_id=member.id,
                moderator_id=interaction.user.id,
                action_type="ban",
                reason=reason
            )

            embed = discord.Embed(
                description=f"✅ Successfully banned {member.mention}.\n**Reason:** {reason}\n**Case ID:** {case_id}",
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

    @app_commands.command(name="global_ban", description="Globally ban a user.")
    @app_commands.describe(user="The user to globally ban.", reason="Reason for the ban.")
    @app_commands.check(is_admin_or_owner)
    async def global_ban(self, interaction: discord.Interaction, user: discord.User, reason: str = "No reason provided."):
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
                        self.bot.logger.info(f"Fetched Roblox User ID {roblox_user_id} for {user} via Bloxlink.")

                        roblox_user_url = f"https://users.roblox.com/v1/users/{roblox_user_id}"
                        async with session.get(roblox_user_url) as roblox_user_response:
                            roblox_user_data = await roblox_user_response.json()
                            roblox_username = roblox_user_data.get("name", "Unknown")

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

    @app_commands.command(name="warns", description="View warnings for a user.")
    @app_commands.describe(user="The user to view warnings for.", show_expired="Whether to include expired warnings.")
    @app_commands.check(is_moderator)
    async def warns(self, interaction: discord.Interaction, user: discord.Member, show_expired: bool = False):
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
            self.bot.logger.info(f"{interaction.user} viewed warnings for {user} (show_expired={show_expired}).")
        except Exception as e:
            self.bot.logger.error(f"Failed to retrieve warnings for {user}: {e}")
            embed = discord.Embed(
                description="An error occurred while retrieving warnings.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="The member to kick.", reason="Reason for kicking the member.")
    @app_commands.check(is_moderator)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
        await interaction.response.defer(ephemeral=True)
        try:
            await member.kick(reason=reason)

            # Random string case ID
            case_id = await self.db.add_case(
                server_id=interaction.guild.id,
                user_id=member.id,
                moderator_id=interaction.user.id,
                action_type="kick",
                reason=reason
            )

            embed = discord.Embed(
                description=f"✅ Successfully kicked {member.mention}.\n**Reason:** {reason}\n**Case ID:** {case_id}",
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

    @app_commands.command(name="timeout", description="Timeout a member for a specified duration.")
    @app_commands.describe(
        member="The member to timeout.",
        duration="Duration (e.g. 10m, 2h, 1d).",
        reason="Reason for the timeout."
    )
    @app_commands.check(is_moderator)
    async def timeout_member(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided."):
        await interaction.response.defer(ephemeral=True)
        try:
            seconds = self.parse_duration(duration)
            if not seconds:
                raise ValueError("Invalid duration format. Please use 10m, 2h, or 1d.")
            until = discord.utils.utcnow() + timedelta(seconds=seconds)
            await member.timeout(until, reason=reason)
            embed = discord.Embed(
                description=(
                    f"✅ {member.mention} has been timed out for {duration}.\n"
                    f"**Reason:** {reason}"
                ),
                color=discord.Color.green()
            )

            # Random string case ID
            case_id = await self.db.add_case(
                server_id=interaction.guild.id,
                user_id=member.id,
                moderator_id=interaction.user.id,
                action_type="timeout",
                reason=reason,
                extra={"duration": duration}
            )

            embed.add_field(name="Case ID", value=case_id, inline=False)
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

    @app_commands.command(name="lock", description="Lock a specific text channel.")
    @app_commands.describe(channel="The channel to lock.", reason="Reason for locking.")
    @app_commands.check(is_moderator)
    async def lock_channel(self, interaction: discord.Interaction, channel: discord.TextChannel = None, reason: str = "No reason provided."):
        await interaction.response.defer(ephemeral=True)
        channel = channel or interaction.channel
        try:
            overwrite = channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = False
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)

            embed = discord.Embed(
                description=f"✅ {channel.mention} locked.\n**Reason:** {reason}",
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
        await interaction.response.defer(ephemeral=True)
        channel = channel or interaction.channel
        try:
            overwrite = channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = True
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)

            embed = discord.Embed(
                description=f"✅ {channel.mention} unlocked.\n**Reason:** {reason}",
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
        await interaction.response.defer(ephemeral=True)
        try:
            count = 0
            for channel in interaction.guild.text_channels:
                overwrite = channel.overwrites_for(interaction.guild.default_role)
                overwrite.send_messages = False
                await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
                count += 1

            embed = discord.Embed(
                description=f"✅ Locked {count} channels.\n**Reason:** {reason}",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.info(f"{interaction.user} locked all channels. Reason: {reason}")

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
        await interaction.response.defer(ephemeral=True)
        try:
            count = 0
            for channel in interaction.guild.text_channels:
                overwrite = channel.overwrites_for(interaction.guild.default_role)
                overwrite.send_messages = True
                await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
                count += 1

            embed = discord.Embed(
                description=f"✅ Unlocked {count} channels.\n**Reason:** {reason}",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.info(f"{interaction.user} unlocked all channels. Reason: {reason}")
        except Exception as e:
            embed = discord.Embed(
                description=f"❌ Failed to unlock all channels: {e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.error(f"Exception while unlocking all channels: {e}")

    async def log_action(
        self,
        guild: discord.Guild,
        action: str,
        executor: discord.User,
        target: discord.Member,
        reason: str,
        duration: str = None
    ):
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
            embed.add_field(
                name="Target",
                value=f"{target} (ID: {target.id})" if target else "N/A",
                inline=True
            )
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
            embed.add_field(
                name="Channel",
                value=f"{channel.mention} (ID: {channel.id})" if channel else "N/A",
                inline=True
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"Guild: {guild.name} (ID: {guild.id})")
            await log_channel.send(embed=embed)
        except Exception as e:
            self.bot.logger.error(f"Failed to log channel moderation action: {e}")

    # CHANGED to accept case_id as a string
    @app_commands.command(name="case", description="Look up data about a specific case.")
    @app_commands.describe(case_id="The ID of the case to look up (e.g. ABC123).")
    @app_commands.check(is_moderator)
    async def case_lookup(self, interaction: discord.Interaction, case_id: str):
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

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
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

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
    bot.logger.info("Moderation Cog has been added to the bot.")