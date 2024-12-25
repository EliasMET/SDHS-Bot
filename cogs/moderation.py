import os
import re
import math
import asyncio
import discord
from datetime import datetime, timedelta
from typing import Union, Optional
from discord.ext import commands
from discord import app_commands

#
# Permissions Checks
#
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
    user_roles = [r.id for r in interaction.user.roles]
    if any(r_id in allowed_roles for r_id in user_roles):
        return True

    raise app_commands.MissingPermissions(['administrator'])

#
# Logging
#
async def log_moderation_action(
    bot: commands.Bot,
    guild: discord.Guild,
    action: str,
    executor: discord.Member,
    target: Union[discord.Member, discord.User, None],
    reason: str,
    duration: Optional[str] = None
):
    """
    Logs a moderation action (ban, unban, kick, global_ban, etc.) to the set mod log channel.
    """
    try:
        log_ch_id = await bot.database.get_mod_log_channel(guild.id)
        if not log_ch_id:
            return
        channel = guild.get_channel(log_ch_id)
        if not channel:
            return

        embed = discord.Embed(
            title=action,
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Executor", value=f"{executor} (ID: {executor.id})", inline=True)
        if target:
            embed.add_field(name="Target", value=f"{target} (ID: {target.id})", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        if duration:
            embed.add_field(name="Duration", value=duration, inline=True)
        embed.set_footer(text=f"Guild: {guild.name} (ID: {guild.id})")

        await channel.send(embed=embed)
    except Exception as ex:
        bot.logger.warning(f"Failed to log moderation action: {ex}")


async def log_channel_action(
    bot: commands.Bot,
    guild: discord.Guild,
    action: str,
    executor: discord.Member,
    channel: discord.TextChannel,
    reason: str
):
    """
    Logs a channel-related moderation action (lock/unlock) to the mod log channel.
    """
    try:
        log_ch_id = await bot.database.get_mod_log_channel(guild.id)
        if not log_ch_id:
            return
        log_ch = guild.get_channel(log_ch_id)
        if not log_ch:
            return

        e = discord.Embed(title=action, color=discord.Color.gold(), timestamp=datetime.utcnow())
        e.add_field(name="Executor", value=f"{executor} (ID: {executor.id})", inline=True)
        e.add_field(name="Channel", value=f"{channel.mention} (ID: {channel.id})", inline=True)
        e.add_field(name="Reason", value=reason, inline=False)
        e.set_footer(text=f"Guild: {guild.name} (ID: {guild.id})")

        await log_ch.send(embed=e)
    except Exception as ex:
        bot.logger.warning(f"Failed to log channel action: {ex}")


#
# Expiration Checker
#
def is_warning_expired(timestamp_val: int, days: int = 2) -> bool:
    dt = datetime.utcfromtimestamp(timestamp_val)
    return (datetime.utcnow() - dt) > timedelta(days=days)

#
# Paginated View for Warnings
#
class WarningsView(discord.ui.View):
    def __init__(self, warnings, user, per_page=7):
        super().__init__(timeout=180)
        self.warnings = warnings
        self.user = user
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = math.ceil(len(warnings) / per_page)

        self.prev_btn = discord.ui.Button(label="Previous", style=discord.ButtonStyle.blurple, disabled=True)
        self.next_btn = discord.ui.Button(label="Next", style=discord.ButtonStyle.blurple, disabled=(self.total_pages <= 1))
        self.prev_btn.callback = self.previous_page
        self.next_btn.callback = self.next_page
        self.add_item(self.prev_btn)
        self.add_item(self.next_btn)

    def create_embed(self) -> discord.Embed:
        start = self.current_page * self.per_page
        end = start + self.per_page
        embed = discord.Embed(
            title=f"Warnings for {self.user}",
            color=0xFF0000,
            description=f"Page {self.current_page + 1}/{self.total_pages}",
            timestamp=datetime.utcnow(),
        )
        for warn in self.warnings[start:end]:
            mod_id = warn[2]
            reason = warn[3]
            ts = int(warn[4])
            warn_id = warn[5]
            embed.add_field(
                name=f"Warn ID: {warn_id}",
                value=(
                    f"**Reason:** {reason}\n"
                    f"**Moderator:** <@{mod_id}>\n"
                    f"**Date:** <t:{ts}:F>"
                ),
                inline=False,
            )
        return embed

    async def previous_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    def update_buttons(self):
        self.prev_btn.disabled = (self.current_page == 0)
        self.next_btn.disabled = (self.current_page >= self.total_pages - 1)


class Moderation(commands.Cog, name="moderation"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.global_ban_lock = asyncio.Lock()

    async def cog_load(self):
        self.db = self.bot.database
        if not self.db:
            self.bot.logger.error("DatabaseManager is not initialized in the bot.")
            raise ValueError("DatabaseManager is not initialized.")
        if not hasattr(self.bot, 'owner_id'):
            app_info = await self.bot.application_info()
            self.bot.owner_id = app_info.owner.id
        self.bot.logger.info("Moderation Cog loaded successfully.")

    #
    # --------------- /ban Command (Local or Global) ---------------
    #
    @app_commands.command(name="ban", description="Ban a member (optionally globally) with optional duration.")
    @app_commands.describe(
        member="The member to ban (mention or ID).",
        reason="Reason for banning.",
        global_ban="If True, ban user across all servers.",
        duration="Optional: 10m, 2h, 1d, etc. (for global ban expiration)."
    )
    @app_commands.check(is_moderator)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: Union[discord.Member, discord.User],
        reason: str = "No reason provided.",
        global_ban: bool = False,
        duration: str = None
    ):
        """
        If global_ban=True, hack-ban across all servers (optionally timed).
        Otherwise, a normal single-guild ban.
        """
        await interaction.response.defer(ephemeral=True)

        if global_ban:
            expires_at_dt = None
            if duration:
                secs = self.parse_duration(duration)
                if not secs:
                    e_err = discord.Embed(
                        description="❌ Invalid duration. Use e.g. `10m`, `2h`, or `1d`.",
                        color=discord.Color.red()
                    )
                    return await interaction.followup.send(embed=e_err, ephemeral=True)
                expires_at_dt = datetime.utcnow() + timedelta(seconds=secs)

            # DM embed
            dm_embed = discord.Embed(
                title="🚫 Ultra Ban Notice",
                description=(
                    f"You have been **ultra banned** from all Homeland Security related servers.\n"
                    f"**Reason:** {reason}\n\n"
                    "If you believe this is a mistake, please contact an admin."
                ),
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            try:
                await member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

            # Possibly get Roblox info from Bloxlink
            roblox_user_id = None
            roblox_username = "Unknown"
            bloxlink_api_key = os.getenv("BLOXLINK_TOKEN")
            if bloxlink_api_key:
                try:
                    guild_id = interaction.guild.id
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        url = f"https://api.blox.link/v4/public/guilds/{guild_id}/discord-to-roblox/{member.id}"
                        headers = {"Authorization": bloxlink_api_key}
                        async with session.get(url, headers=headers) as resp:
                            data = await resp.json()
                            if resp.status == 200 and "robloxID" in data:
                                roblox_user_id = str(data["robloxID"])
                                # fetch more from Roblox
                                roblox_url = f"https://users.roblox.com/v1/users/{roblox_user_id}"
                                async with session.get(roblox_url) as r2:
                                    r2_json = await r2.json()
                                    roblox_username = r2_json.get("name", "Unknown")
                except Exception as e:
                    self.bot.logger.warning(f"Bloxlink error: {e}")

            # DB write for global ban
            async with self.global_ban_lock:
                try:
                    await self.db.add_global_ban(
                        discord_user_id=member.id,
                        roblox_user_id=roblox_user_id,
                        reason=reason,
                        moderator_discord_id=interaction.user.id,
                        expires_at=expires_at_dt
                    )
                except Exception as e:
                    e_db_err = discord.Embed(
                        description=f"❌ Failed to add global ban record: {e}",
                        color=discord.Color.red()
                    )
                    return await interaction.followup.send(embed=e_db_err, ephemeral=True)

                # Add a "global_ban" case
                extra_info = {
                    "roblox_id": roblox_user_id,
                    "roblox_username": roblox_username,
                    "duration": duration or "indefinite",
                    "expires_at": expires_at_dt.isoformat() if expires_at_dt else None
                }
                case_id = await self.db.add_case(
                    interaction.guild.id,
                    member.id,
                    interaction.user.id,
                    "global_ban",
                    reason,
                    extra=extra_info
                )

                # Hack-ban across all guilds
                ban_details = []
                for g in self.bot.guilds:
                    if g.me.guild_permissions.ban_members:
                        was_in = g.get_member(member.id) is not None
                        try:
                            await g.ban(discord.Object(id=member.id), reason=f"[Global Ban] {reason}")
                            ban_details.append((g.name, was_in, True))
                        except Exception:
                            ban_details.append((g.name, was_in, False))

            # Summaries
            success_lines = []
            fail_lines = []
            for guild_name, was_in_guild, success in ban_details:
                if success:
                    success_lines.append(f"✅ **{guild_name}** (in_guild={was_in_guild})")
                else:
                    fail_lines.append(f"❌ **{guild_name}** (in_guild={was_in_guild})")

            succ_txt = "\n".join(success_lines) if success_lines else "None"
            fail_txt = "\n".join(fail_lines) if fail_lines else "None"

            desc = (
                f"**Global Ban** on {member.mention}\n"
                f"**Reason:** {reason}\n"
                f"Roblox: {roblox_username} (ID: {roblox_user_id or 'N/A'})\n"
                f"Duration: {duration or 'indefinite'}\n\n"
                f"**Successful**:\n{succ_txt}\n\n"
                f"**Failed**:\n{fail_txt}\n\n"
                f"**Case ID:** `{case_id}`"
            )
            e_done = discord.Embed(description=desc, color=discord.Color.green())
            await interaction.followup.send(embed=e_done, ephemeral=True)

            # log
            await log_moderation_action(
                self.bot,
                interaction.guild,
                "Global Ban",
                interaction.user,
                member,
                reason,
                duration
            )

        else:
            # single-guild ban
            if isinstance(member, discord.Member):
                try:
                    await member.ban(reason=reason, delete_message_days=0)
                except discord.Forbidden:
                    e_p = discord.Embed(description="❌ Missing perms to ban user.", color=discord.Color.red())
                    return await interaction.followup.send(embed=e_p, ephemeral=True)
                except discord.HTTPException as exc:
                    e_p = discord.Embed(description=f"❌ Ban failed: {exc}", color=discord.Color.red())
                    return await interaction.followup.send(embed=e_p, ephemeral=True)
            else:
                try:
                    await interaction.guild.ban(discord.Object(id=member.id), reason=f"[Local Ban] {reason}")
                except discord.Forbidden:
                    e_p = discord.Embed(description="❌ Missing perms to ban user.", color=discord.Color.red())
                    return await interaction.followup.send(embed=e_p, ephemeral=True)
                except discord.HTTPException as exc:
                    e_p = discord.Embed(description=f"❌ Ban failed: {exc}", color=discord.Color.red())
                    return await interaction.followup.send(embed=e_p, ephemeral=True)

            case_id = await self.db.add_case(
                interaction.guild.id, member.id, interaction.user.id, "ban", reason
            )
            e_done = discord.Embed(
                description=f"🔨 **Banned** {member.mention}\n**Reason:** {reason}\n**Case:** `{case_id}`",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=e_done, ephemeral=True)

            await log_moderation_action(
                self.bot,
                interaction.guild,
                "Ban",
                interaction.user,
                member,
                reason
            )

    #
    # --------------- /unban Command ---------------
    #
    @app_commands.command(name="unban", description="Unban a user from the current server by ID.")
    @app_commands.describe(user_id="ID of the user to unban.", reason="Reason for unbanning.")
    @app_commands.check(is_moderator)
    async def unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
        reason: str = "No reason provided."
    ):
        """
        Unban a user from this server by user ID. 
        We'll attempt to find them in the ban list and unban if found.
        """
        await interaction.response.defer(ephemeral=True)

        # convert ID to int
        try:
            user_id_int = int(user_id)
        except ValueError:
            e_err = discord.Embed(
                description="❌ Invalid user ID (must be a number).",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=e_err, ephemeral=True)

        guild = interaction.guild
        try:
            # guild.bans() is an async iterator in newer libraries, so we do:
            ban_entries = [entry async for entry in guild.bans()]

            # see if user is actually banned
            banned_user = None
            for entry in ban_entries:
                if entry.user.id == user_id_int:
                    banned_user = entry.user
                    break

            if not banned_user:
                e_none = discord.Embed(
                    description=f"❌ User `{user_id_int}` is not banned here or no matching ban found.",
                    color=discord.Color.red()
                )
                return await interaction.followup.send(embed=e_none, ephemeral=True)

            await guild.unban(banned_user, reason=reason)
            case_id = await self.db.add_case(
                guild.id, banned_user.id, interaction.user.id, "unban", reason
            )
            e_done = discord.Embed(
                description=(
                    f"🔓 **Unbanned** <@{banned_user.id}> (ID: {banned_user.id})\n"
                    f"**Reason:** {reason}\n"
                    f"**Case:** `{case_id}`"
                ),
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=e_done, ephemeral=True)

            # log
            await log_moderation_action(
                self.bot,
                guild,
                "Unban",
                interaction.user,
                banned_user,
                reason
            )

        except discord.Forbidden:
            e = discord.Embed(description="❌ Missing permission to unban.", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)
        except discord.HTTPException as ex:
            e = discord.Embed(description=f"❌ Failed to unban user: {ex}", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)

    #
    # parse_duration
    #
    def parse_duration(self, s: str) -> Optional[int]:
        pat = re.compile(r'^(\d+)([mhd])$', re.IGNORECASE)
        match = pat.match(s)
        if not match:
            return None
        val = int(match.group(1))
        unit = match.group(2).lower()
        if unit == 'm':
            return val * 60
        elif unit == 'h':
            return val * 3600
        elif unit == 'd':
            return val * 86400
        return None

    #
    # --------------- Warnings ---------------
    #
    @app_commands.command(name="warns", description="View warnings for a user.")
    @app_commands.describe(user="The user to view warnings for.", show_expired="Include expired warnings?")
    @app_commands.check(is_moderator)
    async def warns(self, interaction: discord.Interaction, user: discord.Member, show_expired: bool = False):
        await interaction.response.defer(ephemeral=True)
        try:
            all_warns = await self.db.get_warnings(user.id, interaction.guild.id)
            if not show_expired:
                all_warns = [w for w in all_warns if not is_warning_expired(int(w[4]))]
            if not all_warns:
                e = discord.Embed(description=f"No warnings found for {user.mention}.", color=discord.Color.green())
                return await interaction.followup.send(embed=e, ephemeral=True)

            view = WarningsView(all_warns, user)
            await interaction.followup.send(embed=view.create_embed(), view=view, ephemeral=True)
        except Exception as ex:
            e = discord.Embed(description=f"❌ Error retrieving warnings: {ex}", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)

    #
    # --------------- Kick ---------------
    #
    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="The member to kick.", reason="Reason for kicking.")
    @app_commands.check(is_moderator)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
        await interaction.response.defer(ephemeral=True)
        try:
            await member.kick(reason=reason)
            case_id = await self.db.add_case(
                interaction.guild.id, member.id, interaction.user.id, "kick", reason
            )
            e = discord.Embed(
                description=f"👢 **Kicked** {member.mention}\n**⚠️ Reason:** {reason}\n**🆔 Case:** `{case_id}`",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=e, ephemeral=True)

            # Log
            await log_moderation_action(
                self.bot, interaction.guild, "Kick", interaction.user, member, reason
            )

        except discord.Forbidden:
            e = discord.Embed(description="❌ Missing permission to kick.", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)
        except discord.HTTPException as ex:
            e = discord.Embed(description=f"❌ Kick failed: {ex}", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)

    #
    # --------------- Timeout ---------------
    #
    @app_commands.command(name="timeout", description="Timeout a member for a certain duration.")
    @app_commands.describe(member="The member to timeout.", duration="e.g., 10m, 2h, 1d", reason="Reason.")
    @app_commands.check(is_moderator)
    async def timeout_member(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided."):
        await interaction.response.defer(ephemeral=True)
        try:
            secs = self.parse_duration(duration)
            if not secs:
                raise ValueError("Invalid duration (use 10m, 2h, 1d, etc.)")
            until = discord.utils.utcnow() + timedelta(seconds=secs)
            await member.timeout(until, reason=reason)
            case_id = await self.db.add_case(
                interaction.guild.id, member.id, interaction.user.id,
                "timeout", reason, extra={"duration": duration}
            )
            e = discord.Embed(
                description=f"⏲️ **Timeout** {member.mention} for `{duration}`\n**⚠️ Reason:** {reason}\n**🆔 Case:** `{case_id}`",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=e, ephemeral=True)

            # Log
            await log_moderation_action(
                self.bot, interaction.guild, "Timeout", interaction.user, member, reason, duration
            )

        except ValueError as ve:
            e = discord.Embed(description=f"❌ {ve}", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)
        except discord.Forbidden:
            e = discord.Embed(description="❌ Missing permission to timeout.", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)
        except discord.HTTPException as ex:
            e = discord.Embed(description=f"❌ Timeout failed: {ex}", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)

    #
    # --------------- Lock/Unlock Single ---------------
    #
    @app_commands.command(name="lock", description="Lock a single channel.")
    @app_commands.describe(channel="Channel to lock.", reason="Reason for locking.")
    @app_commands.check(is_moderator)
    async def lock_channel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        reason: str = "No reason provided."
    ):
        await interaction.response.defer(ephemeral=True)
        if channel is None:
            channel = interaction.channel
        try:
            if await self.db.is_channel_locked(interaction.guild.id, channel.id):
                return await interaction.followup.send(
                    embed=discord.Embed(description=f"❌ {channel.mention} is already locked.", color=discord.Color.red()),
                    ephemeral=True
                )

            overwrite = channel.overwrites_for(interaction.guild.default_role)
            if overwrite.send_messages is False:
                await self.db.lock_channel_in_db(interaction.guild.id, channel.id)
                return await interaction.followup.send(
                    embed=discord.Embed(description=f"❌ {channel.mention} appears locked already.", color=discord.Color.red()),
                    ephemeral=True
                )

            overwrite.send_messages = False
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
            await self.db.lock_channel_in_db(interaction.guild.id, channel.id)

            case_id = await self.db.add_case(
                interaction.guild.id, interaction.user.id, interaction.user.id,
                "channel_lock", reason, extra={"channel_id": channel.id, "channel_name": channel.name}
            )
            lock_embed = discord.Embed(description=f"**⚠️ Reason:** {reason}", color=discord.Color.red())
            lock_embed.set_footer(text=f"🆔 Case: {case_id}")
            await channel.send(embed=lock_embed)

            e = discord.Embed(
                description=f"🔒 **Locked** {channel.mention}\n**⚠️ Reason:** {reason}\n**🆔 Case:** `{case_id}`",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=e, ephemeral=True)

            # Log
            await log_channel_action(self.bot, interaction.guild, "Lock", interaction.user, channel, reason)

        except discord.Forbidden:
            e = discord.Embed(description="❌ I lack permissions to lock this channel.", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)
        except discord.HTTPException as ex:
            e = discord.Embed(description=f"❌ Failed to lock channel: {ex}", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="unlock", description="Unlock a single channel.")
    @app_commands.describe(channel="Channel to unlock.", reason="Reason for unlocking.")
    @app_commands.check(is_moderator)
    async def unlock_channel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        reason: str = "No reason provided."
    ):
        await interaction.response.defer(ephemeral=True)
        if channel is None:
            channel = interaction.channel
        try:
            if not await self.db.is_channel_locked(interaction.guild.id, channel.id):
                return await interaction.followup.send(
                    embed=discord.Embed(description=f"❌ {channel.mention} is not locked by me.", color=discord.Color.red()),
                    ephemeral=True
                )

            overwrite = channel.overwrites_for(interaction.guild.default_role)
            if overwrite.send_messages is True or overwrite.send_messages is None:
                await self.db.unlock_channel_in_db(interaction.guild.id, channel.id)
                return await interaction.followup.send(
                    embed=discord.Embed(description=f"❌ {channel.mention} is already unlocked.", color=discord.Color.red()),
                    ephemeral=True
                )

            overwrite.send_messages = True
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
            await self.db.unlock_channel_in_db(interaction.guild.id, channel.id)

            case_id = await self.db.add_case(
                interaction.guild.id, interaction.user.id, interaction.user.id,
                "channel_unlock", reason, extra={"channel_id": channel.id, "channel_name": channel.name}
            )
            unlock_embed = discord.Embed(description=f"**⚠️ Reason:** {reason}", color=discord.Color.green())
            unlock_embed.set_footer(text=f"🆔 Case: {case_id}")
            await channel.send(embed=unlock_embed)

            e = discord.Embed(
                description=f"🔓 **Unlocked** {channel.mention}\n**⚠️ Reason:** {reason}\n**🆔 Case:** `{case_id}`",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=e, ephemeral=True)

            # Log
            await log_channel_action(self.bot, interaction.guild, "Unlock", interaction.user, channel, reason)

        except discord.Forbidden:
            e = discord.Embed(description="❌ No permission to unlock this channel.", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)
        except discord.HTTPException as ex:
            e = discord.Embed(description=f"❌ Failed to unlock channel: {ex}", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)

    #
    # --------------- Mass Lock/Unlock ---------------
    #
    @app_commands.command(name="lockall", description="Lock all channels (live progress).")
    @app_commands.describe(reason="Reason for locking.")
    @app_commands.check(is_moderator)
    async def lock_all_channels(self, interaction: discord.Interaction, reason: str = "No reason provided."):
        """
        Lock all channels in the guild that aren't already locked.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            case_id = await self.db.add_case(
                interaction.guild.id, interaction.user.id, interaction.user.id,
                "mass_channel_lock", reason
            )

            progress_embed = discord.Embed(
                title="🔒 Mass Lock in Progress...",
                color=discord.Color.yellow(),
                description=(
                    f"Reason: **{reason}**\n\n"
                    "Locking channels; please wait..."
                )
            )
            progress_message = await interaction.followup.send(embed=progress_embed, ephemeral=True)
            locked_count = 0
            channels = list(interaction.guild.text_channels)

            chunk_size = 10
            for i in range(0, len(channels), chunk_size):
                batch = channels[i : i + chunk_size]
                for ch in batch:
                    if await self.db.is_channel_locked(interaction.guild.id, ch.id):
                        continue

                    overwrite = ch.overwrites_for(interaction.guild.default_role)
                    if overwrite.send_messages is False:
                        await self.db.lock_channel_in_db(interaction.guild.id, ch.id)
                        continue

                    overwrite.send_messages = False
                    await ch.set_permissions(interaction.guild.default_role, overwrite=overwrite)
                    await self.db.lock_channel_in_db(interaction.guild.id, ch.id)
                    locked_count += 1

                    emb = discord.Embed(description=f"**⚠️ Reason:** {reason}", color=discord.Color.red())
                    emb.set_footer(text=f"🆔 Case: {case_id}")
                    await ch.send(embed=emb)

                progress_embed.title = "🔒 Mass Lock in Progress..."
                progress_embed.description = (
                    f"Reason: **{reason}**\n\n"
                    f"Locked **{locked_count}** channel(s) so far.\n"
                    f"Remaining: {max(0, len(channels) - (i+chunk_size))}\n\n"
                    "Please wait..."
                )
                await progress_message.edit(embed=progress_embed)

            final_embed = discord.Embed(
                title="✅ Mass Lock Complete",
                color=discord.Color.green(),
                description=(
                    f"Locked **{locked_count}** channel(s)\n"
                    f"**⚠️ Reason:** {reason}\n"
                    f"**🆔 Case:** `{case_id}`"
                )
            )
            await progress_message.edit(embed=final_embed)

        except Exception as ex:
            err = discord.Embed(description=f"❌ Failed to lock all channels: {ex}", color=discord.Color.red())
            await interaction.followup.send(embed=err, ephemeral=True)

    @app_commands.command(name="unlockall", description="Unlock all channels currently locked by me (live progress).")
    @app_commands.describe(reason="Reason for unlocking.")
    @app_commands.check(is_moderator)
    async def unlock_all_channels(self, interaction: discord.Interaction, reason: str = "No reason provided."):
        """
        Unlock only channels that the bot recorded as locked in the DB.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            case_id = await self.db.add_case(
                interaction.guild.id, interaction.user.id, interaction.user.id,
                "mass_channel_unlock", reason
            )

            progress_embed = discord.Embed(
                title="🔓 Mass Unlock in Progress...",
                color=discord.Color.yellow(),
                description=(
                    f"Reason: **{reason}**\n\n"
                    "Unlocking channels; please wait..."
                )
            )
            progress_message = await interaction.followup.send(embed=progress_embed, ephemeral=True)

            unlocked_count = 0
            channels = list(interaction.guild.text_channels)
            chunk_size = 10

            for i in range(0, len(channels), chunk_size):
                batch = channels[i : i + chunk_size]
                for ch in batch:
                    if not await self.db.is_channel_locked(interaction.guild.id, ch.id):
                        continue
                    overwrite = ch.overwrites_for(interaction.guild.default_role)
                    if overwrite.send_messages is True or overwrite.send_messages is None:
                        await self.db.unlock_channel_in_db(interaction.guild.id, ch.id)
                        continue

                    overwrite.send_messages = True
                    await ch.set_permissions(interaction.guild.default_role, overwrite=overwrite)
                    await self.db.unlock_channel_in_db(interaction.guild.id, ch.id)
                    unlocked_count += 1

                    emb = discord.Embed(description=f"**⚠️ Reason:** {reason}", color=discord.Color.green())
                    emb.set_footer(text=f"🆔 Case: {case_id}")
                    await ch.send(embed=emb)

                progress_embed.title = "🔓 Mass Unlock in Progress..."
                progress_embed.description = (
                    f"Reason: **{reason}**\n\n"
                    f"Unlocked **{unlocked_count}** channel(s) so far.\n"
                    f"Remaining: {max(0, len(channels) - (i+chunk_size))}\n\n"
                    "Please wait..."
                )
                await progress_message.edit(embed=progress_embed)

            final_embed = discord.Embed(
                title="✅ Mass Unlock Complete",
                color=discord.Color.green(),
                description=(
                    f"Unlocked **{unlocked_count}** channel(s)\n"
                    f"**⚠️ Reason:** {reason}\n"
                    f"**🆔 Case:** `{case_id}`"
                )
            )
            await progress_message.edit(embed=final_embed)

        except Exception as ex:
            err = discord.Embed(description=f"❌ Failed to unlock all channels: {ex}", color=discord.Color.red())
            await interaction.followup.send(embed=err, ephemeral=True)

    #
    # --------------- /case (Prettier) ---------------
    #
    @app_commands.command(name="case", description="Look up a specific moderation case with improved formatting.")
    @app_commands.describe(case_id="The short case ID (e.g. ABC123).")
    @app_commands.check(is_moderator)
    async def case_lookup(self, interaction: discord.Interaction, case_id: str):
        await interaction.response.defer(ephemeral=True)
        try:
            doc = await self.db.get_case(interaction.guild.id, case_id)
            if not doc:
                e = discord.Embed(title="Case Not Found", description=f"No case with ID **{case_id}**.", color=0xFF0000)
                return await interaction.followup.send(embed=e, ephemeral=True)

            user_id = doc["user_id"]
            mod_id = doc["moderator_id"]
            action_type = doc["action_type"]
            reason = doc["reason"]
            timestamp_str = doc["timestamp"]
            extra = doc.get("extra", {})

            # Convert to display forms
            user_mention = f"<@{user_id}>"
            mod_mention = f"<@{mod_id}>"

            dt_obj = datetime.fromisoformat(timestamp_str)
            unix_ts = int(dt_obj.timestamp())

            # Build a nicer embed
            embed = discord.Embed(
                title=f"Case {case_id} - {action_type.upper()}",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text=f"Server ID: {interaction.guild.id}")

            embed.add_field(name="User", value=user_mention, inline=True)
            embed.add_field(name="Moderator", value=mod_mention, inline=True)
            embed.add_field(name="Action", value=action_type.upper(), inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Created At", value=f"<t:{unix_ts}:F>", inline=False)

            # Show relevant extras
            if "expires_at" in extra and extra["expires_at"]:
                embed.add_field(name="Expires At", value=str(extra["expires_at"]), inline=False)

            # If we have a 'roblox_id' or 'roblox_username' or 'duration', let's show them
            if "roblox_id" in extra and extra["roblox_id"]:
                embed.add_field(name="Roblox ID", value=str(extra["roblox_id"]), inline=True)
            if "roblox_username" in extra and extra["roblox_username"]:
                embed.add_field(name="Roblox User", value=str(extra["roblox_username"]), inline=True)
            if "duration" in extra and extra["duration"]:
                embed.add_field(name="Duration", value=str(extra["duration"]), inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as ex:
            err = discord.Embed(
                title="Error",
                description=f"Error fetching case {case_id}: {ex}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=err, ephemeral=True)

    #
    # --------------- Error Handling ---------------
    #
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        e = discord.Embed(
            title="❌ Error",
            description="An error occurred while processing the command.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        if isinstance(error, app_commands.MissingPermissions):
            e.description = "You do not have the required permissions."
        elif isinstance(error, app_commands.CommandInvokeError):
            e.description = "An error occurred while executing that command."
            self.bot.logger.error(f"CommandInvokeError: {error}")
        else:
            self.bot.logger.error(f"Unhandled error in command {interaction.command}: {error}")
            e.description = str(error)

        if interaction.response.is_done():
            await interaction.followup.send(embed=e, ephemeral=True)
        else:
            await interaction.response.send_message(embed=e, ephemeral=True)

    #
    # Utility: parse_duration
    #
    def parse_duration(self, s: str) -> Optional[int]:
        """
        e.g. 10m -> 600 secs, 2h -> 7200 secs, 1d -> 86400 secs.
        Returns None if invalid.
        """
        pat = re.compile(r'^(\d+)([mhd])$', re.IGNORECASE)
        match = pat.match(s)
        if not match:
            return None
        val = int(match.group(1))
        unit = match.group(2).lower()
        if unit == 'm':
            return val * 60
        elif unit == 'h':
            return val * 3600
        elif unit == 'd':
            return val * 86400
        return None

#
# Cog setup
#
async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
    bot.logger.info("Moderation Cog added.")
