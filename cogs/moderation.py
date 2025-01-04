import os
import re
import math
import asyncio
import discord
from datetime import datetime, timedelta, timezone
from typing import Union, Optional
from discord.ext import commands
from discord import app_commands
import logging

#
# Permissions Checks
#
async def is_admin_or_owner(interaction: discord.Interaction) -> bool:
    """Check if user is admin or owner with detailed error handling"""
    try:
        # Check bot owner status first
        if not hasattr(interaction.client, 'owner_id'):
            app_info = await interaction.client.application_info()
            interaction.client.owner_id = app_info.owner.id
        
        if interaction.user.id == interaction.client.owner_id:
            return True

        # Check admin status
        if interaction.user.guild_permissions.administrator:
            return True

        # If neither, raise with detailed message
        roles_str = ", ".join(role.name for role in interaction.user.roles[1:])  # Skip @everyone
        raise app_commands.MissingPermissions(['administrator'])
    except Exception as e:
        interaction.client.logger.error(
            f"Permission check error in is_admin_or_owner: {str(e)} | "
            f"User: {interaction.user} ({interaction.user.id}) | "
            f"Guild: {interaction.guild.name} ({interaction.guild.id})"
        )
        raise

async def is_moderator(interaction: discord.Interaction) -> bool:
    """Check if user is moderator with detailed error handling"""
    try:
        bot = interaction.client
        
        # Check bot owner status first
        if not hasattr(bot, 'owner_id'):
            app_info = await bot.application_info()
            bot.owner_id = app_info.owner.id

        if interaction.user.id == bot.owner_id:
            return True

        # Check admin status
        if interaction.user.guild_permissions.administrator:
            return True

        # Check mod roles
        allowed_roles = await bot.database.get_moderation_allowed_roles(interaction.guild.id)
        user_roles = [r.id for r in interaction.user.roles]
        if any(r_id in allowed_roles for r_id in user_roles):
            return True

        # If we get here, user doesn't have permission
        # Create detailed error message
        roles_str = ", ".join(role.name for role in interaction.user.roles[1:])  # Skip @everyone
        
        # Log the permission denial
        bot.logger.warning(
            f"Permission denied | "
            f"User: {interaction.user} ({interaction.user.id}) | "
            f"Guild: {interaction.guild.name} ({interaction.guild.id}) | "
            f"Roles: {roles_str}"
        )
        
        # Raise with more specific error message
        raise app_commands.MissingPermissions(['moderator'])
    except app_commands.MissingPermissions:
        raise
    except Exception as e:
        interaction.client.logger.error(
            f"Permission check error in is_moderator: {str(e)} | "
            f"User: {interaction.user} ({interaction.user.id}) | "
            f"Guild: {interaction.guild.name} ({interaction.guild.id})"
        )
        raise

class ModCommandError(Exception):
    """Custom exception for moderation command errors"""
    def __init__(self, message: str, error_type: str = "Error", context: dict = None):
        super().__init__(message)
        self.error_type = error_type
        self.context = context or {}

class Moderation(commands.Cog, name="moderation"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.global_ban_lock = asyncio.Lock()
        self.logger = logging.getLogger('moderation')
        # List of users authorized to use global ban commands
        self.global_ban_authorized_users = [
            828336361928130583,  # User 1
            1178294054170153010, # User 2
            1261031293744058532  # User 3
        ]

    async def check_global_ban_permission(self, user_id: int) -> bool:
        """Check if a user is authorized to use global ban commands"""
        return user_id in self.global_ban_authorized_users

    async def cog_load(self):
        self.db = self.bot.database
        if not self.db:
            self.logger.error("DatabaseManager is not initialized in the bot.")
            raise ValueError("DatabaseManager is not initialized.")
        if not hasattr(self.bot, 'owner_id'):
            app_info = await self.bot.application_info()
            self.bot.owner_id = app_info.owner.id
        self.logger.info("Moderation Cog loaded successfully.")

    async def handle_mod_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        command_name: str,
        context: dict = None
    ) -> None:
        """Handle errors for moderation commands with detailed logging"""
        error_data = {
            "command": command_name,
            "error": str(error),
            "error_type": type(error).__name__,
            "user_id": interaction.user.id,
            "guild_id": interaction.guild.id if interaction.guild else None,
            "timestamp": datetime.utcnow().isoformat(),
            "context": context or {}
        }

        # Add user roles and permissions to error data
        if interaction.guild:
            error_data.update({
                "user_roles": [f"{role.name} ({role.id})" for role in interaction.user.roles],
                "user_permissions": [
                    perm[0] for perm, value in interaction.user.guild_permissions if value
                ]
            })

        # Log to database
        try:
            await self.bot.database.log_command(error_data)
        except Exception as e:
            self.logger.error(f"Failed to log moderation error to database: {str(e)}")

        # Log to console
        self.logger.error(
            f"Moderation error in {command_name} | "
            f"User: {interaction.user} ({interaction.user.id}) | "
            f"Guild: {interaction.guild.name if interaction.guild else 'DM'} | "
            f"Error: {str(error)}"
        )

        # Create error embed
        embed = discord.Embed(
            title=f"❌ {command_name.title()} Error",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        # Handle different error types
        if isinstance(error, app_commands.MissingPermissions):
            embed.description = (
                "You don't have the required permissions for this command.\n\n"
                f"**Required:** {', '.join(error.missing_permissions)}\n"
                f"**Your Roles:** {', '.join(r.name for r in interaction.user.roles)}"
            )
            embed.add_field(
                name="How to Fix",
                value="Contact a server administrator to get the necessary roles or permissions.",
                inline=False
            )
        elif isinstance(error, discord.Forbidden):
            embed.description = (
                "I don't have the required permissions to perform this action.\n"
                "Please check my role permissions and try again."
            )
            embed.add_field(
                name="How to Fix",
                value=(
                    "1. Check my role position in the server settings\n"
                    "2. Ensure I have the necessary permissions\n"
                    "3. Try the command again"
                ),
                inline=False
            )
        elif isinstance(error, ModCommandError):
            embed.title = f"❌ {error.error_type}"
            embed.description = str(error)
            if error.context:
                embed.add_field(
                    name="Additional Information",
                    value="\n".join(f"**{k}:** {v}" for k, v in error.context.items()),
                    inline=False
                )
        else:
            embed.description = f"An unexpected error occurred:\n```{str(error)}```"
            embed.add_field(
                name="What to do?",
                value=(
                    "• Try the command again\n"
                    "• Check if all parameters are correct\n"
                    "• Contact a server administrator if the issue persists"
                ),
                inline=False
            )

        # Add error context
        embed.add_field(
            name="Context",
            value=(
                f"**Command:** /{command_name}\n"
                f"**User:** {interaction.user.mention} ({interaction.user.id})\n"
                f"**Channel:** {interaction.channel.mention if interaction.channel else 'DM'}\n"
                f"**Time:** <t:{int(datetime.utcnow().timestamp())}:F>"
            ),
            inline=False
        )

        # Send error message
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            # Fallback to simple message if embed fails
            await interaction.followup.send(
                f"Error in {command_name}: {str(error)}",
                ephemeral=True
            )

    #
    # Logging
    #
    async def log_moderation_action(
        self,
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
            log_ch_id = await self.db.get_mod_log_channel(guild.id)
            if not log_ch_id:
                return
            channel = guild.get_channel(log_ch_id)
            if not channel:
                return

            embed = discord.Embed(
                title=action,
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc)
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
            self.logger.warning(f"Failed to log moderation action: {ex}")


    async def log_channel_action(
        self,
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
            log_ch_id = await self.db.get_mod_log_channel(guild.id)
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
            self.logger.warning(f"Failed to log channel action: {ex}")


    #
    # Expiration Checker
    #
    def is_warning_expired(self, timestamp_val: int, days: int = 2) -> bool:
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
            # Check if user is authorized for global bans
            if not await self.check_global_ban_permission(interaction.user.id):
                return await interaction.followup.send(
                    embed=discord.Embed(
                        description="❌ You are not authorized to use global bans.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
            
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
                description=reason,
                color=discord.Color.red()
            )
            try:
                await member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException) as e:
                self.logger.warning(f"Could not DM user {member.id} after auto-ban: {e}")

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
                    self.logger.warning(f"Bloxlink error: {e}")

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
                    # Only ban in guilds where global bans are enabled
                    if not await self.db.should_sync_global_bans(g.id):
                        continue
                        
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
            await self.log_moderation_action(
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

            await self.log_moderation_action(
                interaction.guild,
                "Ban",
                interaction.user,
                member,
                reason
            )

    #
    # --------------- /unban Command ---------------
    #
    @app_commands.command(name="unban", description="Unban a user from the current server or globally.")
    @app_commands.describe(
        user_id="ID of the user to unban.",
        reason="Reason for unbanning.",
        global_unban="If True, unban user across all servers."
    )
    @app_commands.check(is_moderator)
    async def unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
        reason: str = "No reason provided.",
        global_unban: bool = False
    ):
        await interaction.response.defer(ephemeral=True)

        if global_unban:
            # Check if user is authorized for global unbans
            if not await self.check_global_ban_permission(interaction.user.id):
                return await interaction.followup.send(
                    embed=discord.Embed(
                        description="❌ You are not authorized to use global unbans.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            # Check if global bans are enabled for this server
            settings = await self.db.get_server_settings(interaction.guild.id)
            if not settings.get('global_bans_enabled', True):
                return await interaction.followup.send(
                    embed=discord.Embed(
                        description="❌ Global bans are disabled for this server.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
            
            # Convert ID to int
            try:
                user_id_int = int(user_id)
            except ValueError:
                return await interaction.followup.send(
                    embed=discord.Embed(
                        description="❌ Invalid user ID (must be a number).",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            try:
                # Remove from global ban database
                removed = await self.db.remove_global_ban(user_id_int)
                if not removed:
                    return await interaction.followup.send(
                        embed=discord.Embed(
                            description="❌ No active global ban found for this user.",
                            color=discord.Color.red()
                        ),
                        ephemeral=True
                    )

                # Unban from all guilds
                unban_details = []
                for g in self.bot.guilds:
                    if g.me.guild_permissions.ban_members:
                        try:
                            await g.unban(discord.Object(id=user_id_int), reason=f"[Global Unban] {reason}")
                            unban_details.append((g.name, True))
                        except Exception:
                            unban_details.append((g.name, False))

                # Format results
                success_guilds = [f"✅ **{n}**" for (n, ok) in unban_details if ok]
                failed_guilds = [f"❌ **{n}**" for (n, ok) in unban_details if not ok]

                succ_text = "\n".join(success_guilds) if success_guilds else "None"
                fail_text = "\n".join(failed_guilds) if failed_guilds else "None"

                # Add case
                case_id = await self.db.add_case(
                    interaction.guild.id,
                    user_id_int,
                    interaction.user.id,
                    "global_unban",
                    reason
                )

                # Create response embed
                desc = (
                    f"🌐 **Global Unban** on <@{user_id_int}>\n"
                    f"**Reason:** {reason}\n\n"
                    f"**Successful Unbans:**\n{succ_text}\n\n"
                    f"**Failed Unbans:**\n{fail_text}\n\n"
                    f"**Case ID:** `{case_id}`"
                )
                embed = discord.Embed(description=desc, color=discord.Color.green())
                await interaction.followup.send(embed=embed, ephemeral=True)

                # Log action
                await self.log_moderation_action(
                    interaction.guild,
                    "Global Unban",
                    interaction.user,
                    await self.bot.fetch_user(user_id_int),
                    reason
                )

            except Exception as e:
                return await interaction.followup.send(
                    embed=discord.Embed(
                        description=f"❌ Failed to process global unban: {e}",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

        else:
            # Regular single-guild unban
            guild = interaction.guild
            try:
                # guild.bans() is an async iterator in newer libraries
                ban_entries = [entry async for entry in guild.bans()]

                # See if user is actually banned
                banned_user = None
                for entry in ban_entries:
                    if entry.user.id == user_id_int:
                        banned_user = entry.user
                        break

                if not banned_user:
                    return await interaction.followup.send(
                        embed=discord.Embed(
                            description=f"❌ User `{user_id_int}` is not banned here.",
                            color=discord.Color.red()
                        ),
                        ephemeral=True
                    )

                await guild.unban(banned_user, reason=reason)
                case_id = await self.db.add_case(
                    guild.id,
                    banned_user.id,
                    interaction.user.id,
                    "unban",
                    reason
                )

                embed = discord.Embed(
                    description=(
                        f"🔓 **Unbanned** <@{banned_user.id}> (ID: {banned_user.id})\n"
                        f"**Reason:** {reason}\n"
                        f"**Case:** `{case_id}`"
                    ),
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

                # Log action
                await self.log_moderation_action(
                    guild,
                    "Unban",
                    interaction.user,
                    banned_user,
                    reason
                )

            except discord.Forbidden:
                return await interaction.followup.send(
                    embed=discord.Embed(
                        description="❌ Missing permission to unban.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
            except discord.HTTPException as ex:
                return await interaction.followup.send(
                    embed=discord.Embed(
                        description=f"❌ Failed to unban user: {ex}",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

    #
    # parse_duration
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
                all_warns = [w for w in all_warns if not self.is_warning_expired(int(w[4]))]
            if not all_warns:
                e = discord.Embed(description=f"No warnings found for {user.mention}.", color=discord.Color.green())
                return await interaction.followup.send(embed=e, ephemeral=True)

            view = self.WarningsView(all_warns, user)
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
            # Log the command attempt
            self.logger.info(
                f"Kick command used | "
                f"Executor: {interaction.user} ({interaction.user.id}) | "
                f"Target: {member} ({member.id}) | "
                f"Guild: {interaction.guild.name} ({interaction.guild.id})"
            )

            case_id = await self.db.add_case(
                interaction.guild.id, member.id, interaction.user.id, "kick", reason
            )

            # Send DM before kicking
            dm_sent = await self.send_moderation_dm(
                member,
                "Kick",
                interaction.guild,
                reason,
                case_id=case_id
            )

            # Perform the kick
            await member.kick(reason=reason)

            # Create response embed
            e = discord.Embed(
                description=(
                    f"👢 **Kicked** {member.mention}\n"
                    f"**⚠️ Reason:** {reason}\n"
                    f"**🆔 Case:** `{case_id}`"
                ),
                color=discord.Color.green()
            )
            if not dm_sent:
                e.add_field(
                    name="Note",
                    value="⚠️ Could not send DM to user",
                    inline=False
                )

            await interaction.followup.send(embed=e, ephemeral=True)

            # Log the action
            await self.log_moderation_action(
                interaction.guild,
                "Kick",
                interaction.user,
                member,
                reason
            )

            # Log successful command execution
            self.logger.info(
                f"Kick successful | "
                f"Case: {case_id} | "
                f"Executor: {interaction.user} ({interaction.user.id}) | "
                f"Target: {member} ({member.id}) | "
                f"Guild: {interaction.guild.name} ({interaction.guild.id})"
            )

        except discord.Forbidden:
            self.logger.error(
                f"Kick failed (Forbidden) | "
                f"Executor: {interaction.user} ({interaction.user.id}) | "
                f"Target: {member} ({member.id}) | "
                f"Guild: {interaction.guild.name} ({interaction.guild.id})"
            )
            e = discord.Embed(description="❌ Missing permission to kick.", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)
        except discord.HTTPException as ex:
            self.logger.error(
                f"Kick failed (HTTP Error) | "
                f"Executor: {interaction.user} ({interaction.user.id}) | "
                f"Target: {member} ({member.id}) | "
                f"Guild: {interaction.guild.name} ({interaction.guild.id}) | "
                f"Error: {ex}"
            )
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
            # Log the command attempt
            self.logger.info(
                f"Timeout command used | "
                f"Executor: {interaction.user} ({interaction.user.id}) | "
                f"Target: {member} ({member.id}) | "
                f"Duration: {duration} | "
                f"Guild: {interaction.guild.name} ({interaction.guild.id})"
            )

            secs = self.parse_duration(duration)
            if not secs:
                raise ValueError("Invalid duration (use 10m, 2h, 1d, etc.)")
            
            # Calculate timeout end time in UTC
            until = datetime.now(timezone.utc) + timedelta(seconds=secs)
            await member.timeout(until, reason=reason)
            
            case_id = await self.db.add_case(
                interaction.guild.id, member.id, interaction.user.id,
                "timeout", reason, extra={
                    "duration": duration,
                    "expires_at": until.isoformat()
                }
            )

            # Send DM to the user
            dm_sent = await self.send_moderation_dm(
                member,
                "Timeout",
                interaction.guild,
                reason,
                duration,
                case_id
            )

            # Create response embed
            e = discord.Embed(
                description=(
                    f"⏲️ **Timeout** {member.mention} for `{duration}`\n"
                    f"**⚠️ Reason:** {reason}\n"
                    f"**🆔 Case:** `{case_id}`\n"
                    f"**Expires:** <t:{self.format_timestamp(until)}:R>"
                ),
                color=discord.Color.yellow(),
                timestamp=datetime.now(timezone.utc)
            )
            if not dm_sent:
                e.add_field(
                    name="Note",
                    value="⚠️ Could not send DM to user",
                    inline=False
                )

            await interaction.followup.send(embed=e, ephemeral=True)

            # Log the action
            await self.log_moderation_action(
                interaction.guild,
                "Timeout",
                interaction.user,
                member,
                reason,
                duration
            )

            # Log successful command execution
            self.logger.info(
                f"Timeout successful | "
                f"Case: {case_id} | "
                f"Executor: {interaction.user} ({interaction.user.id}) | "
                f"Target: {member} ({member.id}) | "
                f"Duration: {duration} | "
                f"Guild: {interaction.guild.name} ({interaction.guild.id})"
            )

        except ValueError as ve:
            self.logger.warning(
                f"Timeout failed (Invalid Duration) | "
                f"Executor: {interaction.user} ({interaction.user.id}) | "
                f"Target: {member} ({member.id}) | "
                f"Duration: {duration} | "
                f"Guild: {interaction.guild.name} ({interaction.guild.id}) | "
                f"Error: {ve}"
            )
            e = discord.Embed(description=f"❌ {ve}", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)
        except discord.Forbidden:
            self.logger.error(
                f"Timeout failed (Forbidden) | "
                f"Executor: {interaction.user} ({interaction.user.id}) | "
                f"Target: {member} ({member.id}) | "
                f"Guild: {interaction.guild.name} ({interaction.guild.id})"
            )
            e = discord.Embed(description="❌ Missing permission to timeout.", color=discord.Color.red())
            await interaction.followup.send(embed=e, ephemeral=True)
        except discord.HTTPException as ex:
            self.logger.error(
                f"Timeout failed (HTTP Error) | "
                f"Executor: {interaction.user} ({interaction.user.id}) | "
                f"Target: {member} ({member.id}) | "
                f"Guild: {interaction.guild.name} ({interaction.guild.id}) | "
                f"Error: {ex}"
            )
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
            await self.log_channel_action(
                interaction.guild,
                "Lock",
                interaction.user,
                channel,
                reason
            )

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
            await self.log_channel_action(
                interaction.guild,
                "Unlock",
                interaction.user,
                channel,
                reason
            )

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
    def get_action_emoji(self, action_type: str) -> str:
        """Get the appropriate emoji for a moderation action"""
        action_emojis = {
            "ban": "🔨",
            "global_ban": "🌐",
            "unban": "🔓",
            "kick": "👢",
            "timeout": "⏲️",
            "warn": "⚠️",
            "channel_lock": "🔒",
            "channel_unlock": "🔓",
            "note": "📝"
        }
        return action_emojis.get(action_type.lower(), "❓")

    def get_action_color(self, action_type: str) -> discord.Color:
        """Get the appropriate color for a moderation action"""
        action_colors = {
            "ban": discord.Color.red(),
            "global_ban": discord.Color.dark_red(),
            "unban": discord.Color.green(),
            "kick": discord.Color.orange(),
            "timeout": discord.Color.yellow(),
            "warn": discord.Color.gold(),
            "channel_lock": discord.Color.blue(),
            "channel_unlock": discord.Color.green(),
            "note": discord.Color.light_grey()
        }
        return action_colors.get(action_type.lower(), discord.Color.blurple())

    def format_timestamp(self, dt: datetime) -> int:
        """Convert datetime to Unix timestamp, ensuring UTC"""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())

    def get_current_timestamp(self) -> int:
        """Get current UTC timestamp"""
        return int(datetime.now(timezone.utc).timestamp())

    @app_commands.command(name="case", description="Look up a specific moderation case with improved formatting.")
    @app_commands.describe(case_id="The case ID to look up (e.g. ABC123)")
    @app_commands.check(is_moderator)
    async def case_lookup(self, interaction: discord.Interaction, case_id: str):
        await interaction.response.defer(ephemeral=True)
        try:
            doc = await self.db.get_case(interaction.guild.id, case_id)
            if not doc:
                raise ModCommandError(
                    f"No case found with ID {case_id}",
                    error_type="Case Not Found",
                    context={"case_id": case_id}
                )

            user_id = doc["user_id"]
            mod_id = doc["moderator_id"]
            action_type = doc["action_type"]
            reason = doc["reason"]
            timestamp_str = doc["timestamp"]
            extra = doc.get("extra", {})

            # Get user and mod objects if possible
            try:
                user = await self.bot.fetch_user(user_id)
                user_str = f"{user} ({user.id})"
            except Exception:
                user_str = f"Unknown User ({user_id})"

            try:
                mod = await self.bot.fetch_user(mod_id)
                mod_str = f"{mod} ({mod.id})"
            except Exception:
                mod_str = f"Unknown Moderator ({mod_id})"

            # Format timestamp
            dt_obj = datetime.fromisoformat(timestamp_str).replace(tzinfo=timezone.utc)
            unix_ts = self.format_timestamp(dt_obj)

            # Get action emoji and color
            action_emoji = self.get_action_emoji(action_type)
            action_color = self.get_action_color(action_type)

            # Build a nicer embed
            embed = discord.Embed(
                title=f"{action_emoji} Case {case_id}",
                color=action_color,
                timestamp=dt_obj
            )

            # Add case information with better formatting
            embed.add_field(
                name="📋 Action",
                value=f"**{action_type.upper()}**",
                inline=True
            )
            
            embed.add_field(
                name="👤 Target User",
                value=f"{user_str}\n<@{user_id}>",
                inline=True
            )

            embed.add_field(
                name="👮 Moderator",
                value=f"{mod_str}\n<@{mod_id}>",
                inline=True
            )

            # Add reason with proper formatting
            formatted_reason = reason if len(reason) <= 1024 else reason[:1021] + "..."
            embed.add_field(
                name="📝 Reason",
                value=formatted_reason,
                inline=False
            )

            # Add timestamps with proper UTC handling
            embed.add_field(
                name="⏰ Executed",
                value=f"<t:{unix_ts}:F> (<t:{unix_ts}:R>)",
                inline=False
            )

            # Handle extra information
            if extra:
                extras_field = []
                
                # Duration for timeouts
                if "duration" in extra:
                    extras_field.append(f"**Duration:** {extra['duration']}")
                
                # Expiration for timed actions
                if "expires_at" in extra and extra["expires_at"]:
                    try:
                        exp_dt = datetime.fromisoformat(extra["expires_at"]).replace(tzinfo=timezone.utc)
                        exp_ts = self.format_timestamp(exp_dt)
                        extras_field.append(f"**Expires:** <t:{exp_ts}:R>")
                    except Exception:
                        extras_field.append(f"**Expires:** {extra['expires_at']}")

                # Roblox information for global bans
                if "roblox_username" in extra or "roblox_id" in extra:
                    roblox_info = []
                    if "roblox_username" in extra and extra["roblox_username"]:
                        roblox_info.append(f"**Username:** {extra['roblox_username']}")
                    if "roblox_id" in extra and extra["roblox_id"]:
                        roblox_info.append(f"**ID:** {extra['roblox_id']}")
                    if roblox_info:
                        extras_field.append("**Roblox Info:**\n" + "\n".join(roblox_info))

                # Channel information for channel actions
                if "channel_id" in extra:
                    extras_field.append(f"**Channel:** <#{extra['channel_id']}> ({extra['channel_id']})")

                if extras_field:
                    embed.add_field(
                        name="📌 Additional Information",
                        value="\n".join(extras_field),
                        inline=False
                    )

            # Add footer with IDs
            embed.set_footer(
                text=f"Server ID: {interaction.guild.id} • Case ID: {case_id}"
            )

            # Log successful case lookup
            log_data = {
                "command": "case",
                "case_id": case_id,
                "user_id": interaction.user.id,
                "guild_id": interaction.guild.id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": True,
                "target_user_id": user_id,
                "action_type": action_type
            }
            try:
                await self.bot.database.log_command(log_data)
            except Exception as e:
                self.logger.error(f"Failed to log successful case lookup: {str(e)}")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except ModCommandError as ex:
            await self.handle_mod_error(interaction, ex, "case", {"case_id": case_id})
        except Exception as ex:
            await self.handle_mod_error(
                interaction,
                ex,
                "case",
                {
                    "case_id": case_id,
                    "guild_id": interaction.guild.id,
                    "user_id": interaction.user.id
                }
            )

    #
    # --------------- Error Handling ---------------
    #
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # Create error log entry
        log_data = {
            "command": interaction.command.name if interaction.command else "Unknown",
            "full_command": str(interaction.data) if interaction.data else "Unknown",
            "user_id": interaction.user.id,
            "user_name": str(interaction.user),
            "channel_id": interaction.channel.id if interaction.channel else None,
            "channel_name": interaction.channel.name if interaction.channel else "DM",
            "guild_id": interaction.guild.id if interaction.guild else None,
            "guild_name": interaction.guild.name if interaction.guild else "DM",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(error),
            "error_type": type(error).__name__
        }

        if interaction.guild:
            log_data.update({
                "roles": [f"{role.name} ({role.id})" for role in interaction.user.roles],
                "permissions": [perm[0] for perm, value in interaction.user.guild_permissions if value],
                "is_admin": interaction.user.guild_permissions.administrator
            })

        # Log to database
        try:
            await self.bot.database.log_command(log_data)
        except Exception as e:
            self.logger.error(f"Failed to log command error to database: {str(e)}")

        # Create error embed
        e = discord.Embed(
            title="❌ Command Error",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        # Handle specific error types
        if isinstance(error, app_commands.MissingPermissions):
            # Get allowed roles for moderation if this is a moderation command
            allowed_roles_str = ""
            if interaction.command and interaction.command.parent and interaction.command.parent.name == "moderation":
                try:
                    allowed_roles = await self.bot.database.get_moderation_allowed_roles(interaction.guild.id)
                    role_names = []
                    for role_id in allowed_roles:
                        role = interaction.guild.get_role(role_id)
                        if role:
                            role_names.append(role.name)
                    if role_names:
                        allowed_roles_str = f"\n**Allowed Roles:** {', '.join(role_names)}"
                except Exception:
                    pass

            e.description = (
                "You don't have permission to use this command.\n\n"
                f"**Required:** Administrator or Moderator role{allowed_roles_str}\n"
                f"**Your Roles:** {', '.join(r.name for r in interaction.user.roles[1:]) or 'None'}"
            )
            e.add_field(
                name="How to Fix",
                value="Contact a server administrator to get the necessary roles or permissions.",
                inline=False
            )
            self.logger.warning(
                f"Permission denied for {interaction.command.name} | "
                f"User: {interaction.user} ({interaction.user.id}) | "
                f"Guild: {interaction.guild.name} ({interaction.guild.id})"
            )
        elif isinstance(error, app_commands.CommandInvokeError):
            if isinstance(error.original, discord.Forbidden):
                e.description = (
                    "I don't have the required permissions to perform this action.\n"
                    "Please check my role permissions and try again."
                )
                e.add_field(
                    name="How to Fix",
                    value=(
                        "1. Check my role position in the server settings\n"
                        "2. Ensure I have the necessary permissions\n"
                        "3. Try the command again"
                    ),
                    inline=False
                )
                self.logger.error(
                    f"Bot missing permissions for {interaction.command.name} | "
                    f"Guild: {interaction.guild.name} ({interaction.guild.id})"
                )
            else:
                e.description = (
                    "An error occurred while executing the command.\n"
                    f"```{str(error.original)}```"
                )
                e.add_field(
                    name="What to do?",
                    value=(
                        "• Try the command again\n"
                        "• Check if all parameters are correct\n"
                        "• Contact a server administrator if the issue persists"
                    ),
                    inline=False
                )
                self.logger.error(
                    f"Error in {interaction.command.name}: {str(error.original)} | "
                    f"User: {interaction.user} ({interaction.user.id}) | "
                    f"Guild: {interaction.guild.name} ({interaction.guild.id})"
                )
        else:
            e.description = str(error)
            e.add_field(
                name="What to do?",
                value=(
                    "• Try the command again\n"
                    "• Check if all parameters are correct\n"
                    "• Contact a server administrator if the issue persists"
                ),
                inline=False
            )
            self.logger.error(
                f"Unhandled error in {interaction.command.name}: {error} | "
                f"User: {interaction.user} ({interaction.user.id}) | "
                f"Guild: {interaction.guild.name} ({interaction.guild.id})"
            )

        # Add error context to embed
        e.add_field(
            name="Context",
            value=(
                f"**Command:** /{interaction.command.name if interaction.command else 'Unknown'}\n"
                f"**User:** {interaction.user.mention} ({interaction.user.id})\n"
                f"**Channel:** {interaction.channel.mention if interaction.channel else 'DM'}\n"
                f"**Time:** <t:{int(datetime.utcnow().timestamp())}:F>"
            ),
            inline=False
        )

        # Send error message
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=e, ephemeral=True)
            else:
                await interaction.response.send_message(embed=e, ephemeral=True)
        except discord.HTTPException:
            # If we can't send the fancy embed, try to send a simple message
            simple_error = (
                f"Error in command {interaction.command.name if interaction.command else 'Unknown'}: {str(error)}"
            )
            if interaction.response.is_done():
                await interaction.followup.send(simple_error, ephemeral=True)
            else:
                await interaction.response.send_message(simple_error, ephemeral=True)

    #
    # --------------- Case Error Handling ---------------
    #
    async def handle_case_error(self, interaction: discord.Interaction, case_id: str, error: Exception) -> None:
        """Handle errors specifically for case-related commands"""
        error_data = {
            "command": "case",
            "case_id": case_id,
            "error": str(error),
            "error_type": type(error).__name__,
            "user_id": interaction.user.id,
            "guild_id": interaction.guild.id if interaction.guild else None,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Log to database
        try:
            await self.bot.database.log_command(error_data)
        except Exception as e:
            self.logger.error(f"Failed to log case error to database: {str(e)}")

        # Log to console
        self.logger.error(
            f"Case lookup error | Case: {case_id} | "
            f"User: {interaction.user} ({interaction.user.id}) | "
            f"Guild: {interaction.guild.name if interaction.guild else 'DM'} | "
            f"Error: {str(error)}"
        )

        # Create error embed
        embed = discord.Embed(
            title="❌ Case Lookup Error",
            description=(
                f"An error occurred while looking up case `{case_id}`:\n"
                f"```{str(error)}```"
            ),
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(
            name="What to do?",
            value=(
                "• Check if the case ID is correct\n"
                "• Verify the case exists in this server\n"
                "• Try again later or contact an administrator"
            ),
            inline=False
        )
        embed.set_footer(text=f"Error Type: {type(error).__name__}")

        # Send error message
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            # Fallback to simple message if embed fails
            await interaction.followup.send(
                f"Error looking up case {case_id}: {str(error)}",
                ephemeral=True
            )

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

    async def send_moderation_dm(
        self,
        user: Union[discord.Member, discord.User],
        action: str,
        guild: discord.Guild,
        reason: str,
        duration: Optional[str] = None,
        case_id: Optional[str] = None
    ):
        """Send a DM to a user about a moderation action"""
        try:
            embed = discord.Embed(
                title=f"Moderation Action: {action}",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Server", value=guild.name, inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            if duration:
                embed.add_field(name="Duration", value=duration, inline=False)
                # If it's a timeout, calculate and show expiration
                if action.lower() == "timeout":
                    secs = self.parse_duration(duration)
                    if secs:
                        expires_at = datetime.now(timezone.utc) + timedelta(seconds=secs)
                        embed.add_field(
                            name="Expires",
                            value=f"<t:{self.format_timestamp(expires_at)}:R>",
                            inline=False
                        )
            if case_id:
                embed.add_field(name="Case ID", value=case_id, inline=False)
            
            embed.set_footer(text=f"Server ID: {guild.id}")
            
            await user.send(embed=embed)
            return True
        except (discord.Forbidden, discord.HTTPException) as e:
            self.logger.warning(
                f"Failed to send moderation DM to {user} ({user.id}): {str(e)}"
            )
            return False

    async def handle_global_ban(self, guild: discord.Guild, user_id: int, reason: str, moderator_id: int = None):
        """Handle a global ban across all servers where enabled"""
        try:
            # Only apply the ban if the guild has global bans enabled
            if not await self.db.should_sync_global_bans(guild.id):
                return

            try:
                await guild.ban(discord.Object(id=user_id), reason=f"Global Ban: {reason}")
                self.logger.info(f"Successfully banned {user_id} from {guild.name} (Global Ban)")
            except discord.Forbidden:
                self.logger.warning(f"Missing permissions to ban {user_id} from {guild.name}")
            except discord.NotFound:
                self.logger.warning(f"User {user_id} not found in {guild.name}")
            except Exception as e:
                self.logger.error(f"Error banning {user_id} from {guild.name}: {e}")

        except Exception as e:
            self.logger.error(f"Error handling global ban in guild {guild.id}: {e}")

    async def handle_global_unban(self, guild: discord.Guild, user_id: int, reason: str = "Global Ban Removed"):
        """Handle a global unban across all servers where enabled"""
        try:
            # Only apply the unban if the guild has global bans enabled
            if not await self.db.should_sync_global_bans(guild.id):
                return

            try:
                await guild.unban(discord.Object(id=user_id), reason=reason)
                self.logger.info(f"Successfully unbanned {user_id} from {guild.name} (Global Unban)")
            except discord.Forbidden:
                self.logger.warning(f"Missing permissions to unban {user_id} from {guild.name}")
            except discord.NotFound:
                self.logger.warning(f"User {user_id} not found in {guild.name} ban list")
            except Exception as e:
                self.logger.error(f"Error unbanning {user_id} from {guild.name}: {e}")

        except Exception as e:
            self.logger.error(f"Error handling global unban in guild {guild.id}: {e}")

    async def sync_global_bans_for_guild(self, guild: discord.Guild):
        """Sync all active global bans to a guild that just enabled global bans"""
        try:
            successful, failed = await self.db.sync_global_bans_for_guild(guild.id)
            
            for user_id in successful:
                ban = await self.db.get_global_ban(user_id)
                if ban:
                    await self.handle_global_ban(
                        guild,
                        user_id,
                        f"Global Ban Sync: {ban.get('reason', 'No reason provided')}",
                        int(ban.get('moderator_discord_id', 0))
                    )
            
            if successful:
                self.logger.info(f"Synced {len(successful)} global bans to {guild.name}")
            if failed:
                self.logger.warning(f"Failed to sync {len(failed)} global bans to {guild.name}")
                
        except Exception as e:
            self.logger.error(f"Error syncing global bans for guild {guild.id}: {e}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """When the bot joins a guild, sync global bans if enabled"""
        if await self.db.should_sync_global_bans(guild.id):
            await self.sync_global_bans_for_guild(guild)

#
# Cog setup
#
async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
