"""
Moderation Cog
Provides ban, kick, timeout, lock channel, unlock channel,
lock all channels, and unlock all channels commands.

Version: 1.3.0
"""

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import re
from datetime import timedelta
import logging
import aiohttp
import os

async def is_admin_or_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator or interaction.user.id == interaction.guild.owner_id

# Define the check function for admin, owner, or allowed roles outside the class
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

class Moderation(commands.Cog, name="moderation"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.database

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
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"✅ Successfully banned {member.mention}.\n**Reason:** {reason}",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )
            self.bot.logger.info(f"{interaction.user} banned {member} for reason: {reason}")
            await self.log_action(interaction.guild, "Ban", interaction.user, member, reason)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ I do not have permission to ban this member.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            self.bot.logger.warning(f"Failed to ban {member}: Missing Permissions.")
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Failed to ban member: {e}",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            self.bot.logger.error(f"HTTPException while banning {member}: {e}")

    @app_commands.command(name="global_ban", description="Globally ban a user.")
    @app_commands.describe(user="The user to globally ban.", reason="Reason for the ban.")
    @app_commands.check(is_admin_or_owner)
    async def global_ban(self, interaction: discord.Interaction, user: discord.User, reason: str = "No reason provided."):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        bloxlink_api_key = os.getenv("BLOXLINK_TOKEN")
        if not bloxlink_api_key:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ BLOXLINK_TOKEN not set in environment variables.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            self.bot.logger.error("BLOXLINK_TOKEN is missing.")
            return

        try:
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
                        if roblox_user_response.status != 200:
                            raise RuntimeError(
                                f"Roblox Users API responded with status {roblox_user_response.status}"
                            )
                        roblox_user_data = await roblox_user_response.json()
                        roblox_username = roblox_user_data.get("name", "Unknown")

            # Add user to global bans in the database including the moderator's ID
            await self.db.add_global_ban(user.id, roblox_user_id, reason, interaction.user.id)

            await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        f"✅ Successfully globally banned {user.mention}.\n"
                        f"**Reason:** {reason}\n"
                        f"**Roblox Username:** {roblox_username}\n"
                        f"**Roblox ID:** {roblox_user_id}"
                    ),
                    color=discord.Color.green()
                ),
                ephemeral=True
            )
            self.bot.logger.info(
                f"{interaction.user} globally banned {user} (Roblox ID: {roblox_user_id}) for reason: {reason}"
            )

        except Exception as e:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Failed to globally ban user: {e}",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            self.bot.logger.error(f"Exception while globally banning {user}: {e}")

    @app_commands.command(name="global_unban", description="Remove a global ban from a user.")
    @app_commands.describe(user="The user to remove the global ban from.")
    @app_commands.check(is_admin_or_owner)
    async def global_unban(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        try:
            removed = await self.db.remove_global_ban(user.id)
            if removed:
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=f"✅ Successfully removed global ban for {user.mention}.",
                        color=discord.Color.green()
                    ),
                    ephemeral=True
                )
                self.bot.logger.info(f"{interaction.user} removed global ban for {user}")
            else:
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=f"❌ No global ban found for {user.mention}.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
                self.bot.logger.warning(f"{interaction.user} attempted to remove non-existent global ban for {user}")
        except Exception as e:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Failed to remove global ban: {e}",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            self.bot.logger.error(f"Exception while removing global ban for {user}: {e}")

    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="The member to kick.", reason="Reason for kicking the member.")
    @app_commands.check(is_moderator)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
        await interaction.response.defer(ephemeral=True)
        try:
            await member.kick(reason=reason)
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"✅ Successfully kicked {member.mention}.\n**Reason:** {reason}",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )
            self.bot.logger.info(f"{interaction.user} kicked {member} for reason: {reason}")
            await self.log_action(interaction.guild, "Kick", interaction.user, member, reason)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ I do not have permission to kick this member.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            self.bot.logger.warning(f"Failed to kick {member}: Missing Permissions.")
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Failed to kick member: {e}",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            self.bot.logger.error(f"HTTPException while kicking {member}: {e}")

    @app_commands.command(name="timeout", description="Timeout a member for a specified duration.")
    @app_commands.describe(member="The member to timeout.", duration="Duration (e.g. 10m, 2h, 1d).", reason="Reason for the timeout.")
    @app_commands.check(is_moderator)
    async def timeout_member(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided."):
        await interaction.response.defer(ephemeral=True)
        try:
            timeout_seconds = self.parse_duration(duration)
            if timeout_seconds is None:
                raise ValueError("Invalid duration format. Use formats like `10m`, `2h`, `1d`.")

            await member.timeout(timedelta(seconds=timeout_seconds), reason=reason)
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"✅ Successfully timed out {member.mention} for {duration}.\n**Reason:** {reason}",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )
            self.bot.logger.info(f"{interaction.user} timed out {member} for {duration} with reason: {reason}")
            await self.log_action(interaction.guild, "Timeout", interaction.user, member, reason, duration)
        except ValueError as ve:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ {ve}",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            self.bot.logger.warning(f"Invalid duration format provided by {interaction.user}: {duration}")
        except discord.Forbidden:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ I do not have permission to timeout this member.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            self.bot.logger.warning(f"Failed to timeout {member}: Missing Permissions.")
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Failed to timeout member: {e}",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
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
        else:
            return None

    @app_commands.command(name="lock", description="Lock a specific text channel.")
    @app_commands.describe(channel="The channel to lock.", reason="Reason for locking.")
    @app_commands.check(is_moderator)
    async def lock_channel(self, interaction: discord.Interaction, channel: discord.TextChannel = None, reason: str = "No reason provided."):
        await interaction.response.defer(ephemeral=True)
        channel = channel or interaction.channel
        try:
            can_send_messages = channel.permissions_for(interaction.guild.default_role).send_messages
            if can_send_messages is False:
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=f"ℹ️ {channel.mention} is already locked.",
                        color=discord.Color.blue()
                    ),
                    ephemeral=True
                )
                self.bot.logger.info(f"{interaction.user} attempted to lock {channel}, but it was already locked.")
                return

            overwrite = channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = False
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

            await self.db.lock_channel_in_db(interaction.guild.id, channel.id)
            await channel.send(
                embed=discord.Embed(
                    description=f"🔒 This channel has been locked by {interaction.user.mention}.\n**Reason:** {reason}",
                    color=discord.Color.orange()
                )
            )

            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"✅ {channel.mention} has been locked.\n**Reason:** {reason}",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )
            self.bot.logger.info(f"{interaction.user} locked {channel} for reason: {reason}")
            await self.log_channel_action(interaction.guild, "Lock Channel", interaction.user, channel, reason)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ I do not have permission to modify this channel.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            self.bot.logger.warning(f"Failed to lock {channel}: Missing Permissions.")
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Failed to lock channel: {e}",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            self.bot.logger.error(f"HTTPException while locking {channel}: {e}")

    @app_commands.command(name="unlock", description="Unlock a specific text channel.")
    @app_commands.describe(channel="The channel to unlock.", reason="Reason for unlocking.")
    @app_commands.check(is_moderator)
    async def unlock_channel(self, interaction: discord.Interaction, channel: discord.TextChannel = None, reason: str = "No reason provided."):
        await interaction.response.defer(ephemeral=True)
        channel = channel or interaction.channel
        try:
            is_locked_by_bot = await self.db.is_channel_locked(interaction.guild.id, channel.id)
            if not is_locked_by_bot:
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=f"ℹ️ {channel.mention} is not locked by me.",
                        color=discord.Color.blue()
                    ),
                    ephemeral=True
                )
                self.bot.logger.info(f"{interaction.user} attempted to unlock {channel}, but it was not locked by the bot.")
                return

            overwrite = channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = True
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

            await self.db.unlock_channel_in_db(interaction.guild.id, channel.id)
            await channel.send(
                embed=discord.Embed(
                    description=f"🔓 This channel has been unlocked by {interaction.user.mention}.\n**Reason:** {reason}",
                    color=discord.Color.green()
                )
            )

            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"✅ {channel.mention} has been unlocked.\n**Reason:** {reason}",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )
            self.bot.logger.info(f"{interaction.user} unlocked {channel} for reason: {reason}")
            await self.log_channel_action(interaction.guild, "Unlock Channel", interaction.user, channel, reason)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ I do not have permission to modify this channel.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            self.bot.logger.warning(f"Failed to unlock {channel}: Missing Permissions.")
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Failed to unlock channel: {e}",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            self.bot.logger.error(f"HTTPException while unlocking {channel}: {e}")

    @app_commands.command(name="lockall", description="Lock all text channels in the server.")
    @app_commands.describe(reason="Reason for locking all channels.")
    @app_commands.check(is_moderator)
    async def lock_all_channels(self, interaction: discord.Interaction, reason: str = "No reason provided."):
        await interaction.response.defer(ephemeral=True)
        try:
            text_channels = interaction.guild.text_channels
            total_channels = len(text_channels)
            locked_channels = 0

            progress_embed = discord.Embed(
                title="🔒 Locking All Channels",
                description=f"Locked {locked_channels}/{total_channels} channels.",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            progress_embed.set_footer(text=f"Reason: {reason}")
            progress_message = await interaction.followup.send(embed=progress_embed, ephemeral=True)

            for idx, channel in enumerate(text_channels, start=1):
                try:
                    can_send_messages = channel.permissions_for(interaction.guild.default_role).send_messages
                    if can_send_messages is False:
                        self.bot.logger.info(f"Skipped locking {channel} as it was already locked.")
                        continue

                    overwrite = channel.overwrites_for(interaction.guild.default_role)
                    overwrite.send_messages = False
                    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

                    await self.db.lock_channel_in_db(interaction.guild.id, channel.id)
                    await channel.send(
                        embed=discord.Embed(
                            description=f"🔒 This channel has been locked by {interaction.user.mention}.\n**Reason:** {reason}",
                            color=discord.Color.orange()
                        )
                    )

                    locked_channels += 1
                    self.bot.logger.info(f"{interaction.user} locked {channel} for reason: {reason}")

                    if idx % 5 == 0 or idx == total_channels:
                        updated_embed = discord.Embed(
                            title="🔒 Locking All Channels",
                            description=f"Locked {locked_channels}/{total_channels} channels.",
                            color=discord.Color.orange(),
                            timestamp=discord.utils.utcnow()
                        )
                        updated_embed.set_footer(text=f"Reason: {reason}")
                        await progress_message.edit(embed=updated_embed)

                except discord.Forbidden:
                    self.bot.logger.warning(f"Failed to lock {channel}: Missing Permissions.")
                except discord.HTTPException as e:
                    self.bot.logger.error(f"HTTPException while locking {channel}: {e}")

            final_embed = discord.Embed(
                title="🔒 All Channels Locked",
                description=f"✅ Locked {locked_channels}/{total_channels} text channels.\n**Reason:** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            await progress_message.edit(embed=final_embed)
            self.bot.logger.info(f"{interaction.user} locked all channels for reason: {reason} ({locked_channels}/{total_channels} successful)")
            await self.log_channel_action(interaction.guild, "Lock All Channels", interaction.user, None, reason)
        except Exception as e:
            self.bot.logger.error(f"Failed to lock all channels: {e}")
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Failed to lock all channels: {e}",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

    @app_commands.command(name="unlockall", description="Unlock all text channels in the server.")
    @app_commands.describe(reason="Reason for unlocking all channels.")
    @app_commands.check(is_moderator)
    async def unlock_all_channels(self, interaction: discord.Interaction, reason: str = "No reason provided."):
        await interaction.response.defer(ephemeral=True)
        try:
            text_channels = interaction.guild.text_channels
            total_channels = len(text_channels)
            unlocked_channels = 0

            progress_embed = discord.Embed(
                title="🔓 Unlocking All Channels",
                description=f"Unlocked {unlocked_channels}/{total_channels} channels.",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            progress_embed.set_footer(text=f"Reason: {reason}")
            progress_message = await interaction.followup.send(embed=progress_embed, ephemeral=True)

            for idx, channel in enumerate(text_channels, start=1):
                try:
                    is_locked_by_bot = await self.db.is_channel_locked(interaction.guild.id, channel.id)
                    if not is_locked_by_bot:
                        self.bot.logger.info(f"Skipped unlocking {channel} as it was not locked by the bot.")
                        continue

                    overwrite = channel.overwrites_for(interaction.guild.default_role)
                    overwrite.send_messages = True
                    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

                    await self.db.unlock_channel_in_db(interaction.guild.id, channel.id)
                    await channel.send(
                        embed=discord.Embed(
                            description=f"🔓 This channel has been unlocked by {interaction.user.mention}.\n**Reason:** {reason}",
                            color=discord.Color.green()
                        )
                    )

                    unlocked_channels += 1
                    self.bot.logger.info(f"{interaction.user} unlocked {channel} for reason: {reason}")

                    if idx % 5 == 0 or idx == total_channels:
                        updated_embed = discord.Embed(
                            title="🔓 Unlocking All Channels",
                            description=f"Unlocked {unlocked_channels}/{total_channels} channels.",
                            color=discord.Color.green(),
                            timestamp=discord.utils.utcnow()
                        )
                        updated_embed.set_footer(text=f"Reason: {reason}")
                        await progress_message.edit(embed=updated_embed)

                except discord.Forbidden:
                    self.bot.logger.warning(f"Failed to unlock {channel}: Missing Permissions.")
                except discord.HTTPException as e:
                    self.bot.logger.error(f"HTTPException while unlocking {channel}: {e}")

            final_embed = discord.Embed(
                title="🔓 All Channels Unlocked",
                description=f"✅ Unlocked {unlocked_channels}/{total_channels} text channels.\n**Reason:** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            await progress_message.edit(embed=final_embed)
            self.bot.logger.info(f"{interaction.user} unlocked all channels for reason: {reason} ({unlocked_channels}/{total_channels} successful)")
            await self.log_channel_action(interaction.guild, "Unlock All Channels", interaction.user, None, reason)
        except Exception as e:
            self.bot.logger.error(f"Failed to unlock all channels: {e}")
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Failed to unlock all channels: {e}",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

    async def log_action(self, guild: discord.Guild, action: str, executor: discord.User, target: discord.Member, reason: str, duration: str = None):
        try:
            log_channel_id = await self.db.get_mod_log_channel(guild.id)
            if not log_channel_id:
                self.bot.logger.warning(f"Mod log channel not set for guild {guild.name} (ID: {guild.id}).")
                return
            log_channel = guild.get_channel(log_channel_id)
            if not log_channel:
                self.bot.logger.warning(f"Mod log channel ID {log_channel_id} not found in guild {guild.name} (ID: {guild.id}).")
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
                embed.add_field(name="Duration", value=duration, inline=False)
            embed.set_footer(text=f"Guild: {guild.name} (ID: {guild.id})")
            await log_channel.send(embed=embed)
        except Exception as e:
            self.bot.logger.error(f"Failed to log moderation action: {e}")

    async def log_channel_action(self, guild: discord.Guild, action: str, executor: discord.User, channel: discord.TextChannel, reason: str):
        try:
            log_channel_id = await self.db.get_mod_log_channel(guild.id)
            if not log_channel_id:
                self.bot.logger.warning(f"Mod log channel not set for guild {guild.name} (ID: {guild.id}).")
                return
            log_channel = guild.get_channel(log_channel_id)
            if not log_channel:
                self.bot.logger.warning(f"Mod log channel ID {log_channel_id} not found in guild {guild.name} (ID: {guild.id}).")
                return

            embed = discord.Embed(
                title=f"📜 {action}",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Executor", value=f"{executor} (ID: {executor.id})", inline=True)
            embed.add_field(name="Channel", value=f"{channel.mention} (ID: {channel.id})" if channel else "N/A", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"Guild: {guild.name} (ID: {guild.id})")
            await log_channel.send(embed=embed)
        except Exception as e:
            self.bot.logger.error(f"Failed to log channel moderation action: {e}")

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="Missing Permissions",
                description="You need the `Administrator` permission to use this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.bot.logger.warning(f"{interaction.user} lacks permissions to execute {interaction.command.name}.")
        elif isinstance(error, app_commands.CommandInvokeError):
            embed = discord.Embed(
                title="Error",
                description=f"An unexpected error occurred: {error.original}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.bot.logger.error(f"Error in command {interaction.command.name}: {error.original}")
        else:
            embed = discord.Embed(
                title="Error",
                description=f"An error occurred: {error}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.bot.logger.error(f"Unhandled error in command {interaction.command.name}: {error}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
    bot.logger.info("Moderation Cog has been added to the bot.")
