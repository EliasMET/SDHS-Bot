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

# Define the check function for admin, owner, or allowed roles outside the class
async def is_moderator(interaction: discord.Interaction) -> bool:
    """
    Check if the user is an administrator, the bot owner, or has an allowed role.

    :param interaction: The interaction context.
    :return: True if user is admin, owner, or has an allowed role, else raises MissingPermissions.
    """
    bot = interaction.client
    # Cache owner_id if not already cached
    if not hasattr(bot, 'owner_id'):
        app_info = await bot.application_info()
        bot.owner_id = app_info.owner.id

    if interaction.user.id == bot.owner_id:
        return True
    if interaction.user.guild_permissions.administrator:
        return True
    # Fetch allowed roles from the database
    allowed_roles = await bot.database.get_moderation_allowed_roles(interaction.guild.id)
    user_roles = [role.id for role in interaction.user.roles]
    if any(role_id in allowed_roles for role_id in user_roles):
        return True
    raise app_commands.MissingPermissions(['administrator'])

class Moderation(commands.Cog, name="moderation"):
    """
    A cog for server moderation commands.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = None  # Will be initialized in cog_load

    async def cog_load(self):
        """
        Initialize the cog by setting up the database and caching owner_id.
        """
        self.db = self.bot.database  # Access DatabaseManager from the bot instance
        if not self.db:
            self.bot.logger.error("DatabaseManager is not initialized in the bot.")
            raise ValueError("DatabaseManager is not initialized in the bot.")
        # Ensure owner_id is cached
        if not hasattr(self.bot, 'owner_id'):
            app_info = await self.bot.application_info()
            self.bot.owner_id = app_info.owner.id
        self.bot.logger.info("Moderation Cog loaded successfully.")

    # Ban Command
    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(member="The member to ban.", reason="Reason for banning the member.")
    @app_commands.check(is_moderator)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
        """
        Bans a member from the server.

        :param interaction: The command interaction.
        :param member: The member to ban.
        :param reason: Reason for the ban.
        """
        await interaction.response.defer(ephemeral=True)  # Use the thinking function
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
            # Log the action
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

    # Kick Command
    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="The member to kick.", reason="Reason for kicking the member.")
    @app_commands.check(is_moderator)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
        """
        Kicks a member from the server.

        :param interaction: The command interaction.
        :param member: The member to kick.
        :param reason: Reason for the kick.
        """
        await interaction.response.defer(ephemeral=True)  # Use the thinking function
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
            # Log the action
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

    # Timeout Command
    @app_commands.command(name="timeout", description="Timeout a member for a specified duration.")
    @app_commands.describe(member="The member to timeout.", duration="Duration for the timeout (e.g., 10m, 2h, 1d).", reason="Reason for the timeout.")
    @app_commands.check(is_moderator)
    async def timeout_member(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided."):
        """
        Temporarily restricts a member from interacting in the server.

        :param interaction: The command interaction.
        :param member: The member to timeout.
        :param duration: Duration for the timeout (e.g., 10m, 2h, 1d).
        :param reason: Reason for the timeout.
        """
        await interaction.response.defer(ephemeral=True)  # Use the thinking function
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
            # Log the action
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
        """
        Parses a duration string into seconds.
        Supported formats: Xm, Xh, Xd (minutes, hours, days)

        :param duration_str: Duration string.
        :return: Duration in seconds or None if invalid.
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
        else:
            return None

    # Lock Channel Command
    @app_commands.command(name="lock", description="Lock a specific text channel.")
    @app_commands.describe(channel="The channel to lock.", reason="Reason for locking the channel.")
    @app_commands.check(is_moderator)
    async def lock_channel(self, interaction: discord.Interaction, channel: discord.TextChannel = None, reason: str = "No reason provided."):
        """
        Locks a specific text channel by preventing @everyone from sending messages.

        :param interaction: The command interaction.
        :param channel: The channel to lock. Defaults to the current channel.
        :param reason: Reason for locking the channel.
        """
        await interaction.response.defer(ephemeral=True)  # Use the thinking function
        channel = channel or interaction.channel
        try:
            # Check if @everyone already cannot send messages
            can_send_messages = channel.permissions_for(interaction.guild.default_role).send_messages
            if not can_send_messages:
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=f"ℹ️ {channel.mention} is already locked.",
                        color=discord.Color.blue()
                    ),
                    ephemeral=True
                )
                self.bot.logger.info(f"{interaction.user} attempted to lock {channel}, but it was already locked.")
                return

            # Lock the channel
            overwrite = channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = False
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

            # Record the locked channel in the database
            await self.db.lock_channel_in_db(interaction.guild.id, channel.id)

            # Send a message in the locked channel indicating the reason
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
            # Log the action
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

    # Unlock Channel Command
    @app_commands.command(name="unlock", description="Unlock a specific text channel.")
    @app_commands.describe(channel="The channel to unlock.", reason="Reason for unlocking the channel.")
    @app_commands.check(is_moderator)
    async def unlock_channel(self, interaction: discord.Interaction, channel: discord.TextChannel = None, reason: str = "No reason provided."):
        """
        Unlocks a specific text channel by allowing @everyone to send messages.

        :param interaction: The command interaction.
        :param channel: The channel to unlock. Defaults to the current channel.
        :param reason: Reason for unlocking the channel.
        """
        await interaction.response.defer(ephemeral=True)  # Use the thinking function
        channel = channel or interaction.channel
        try:
            # Check if the bot had previously locked this channel
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

            # Unlock the channel
            overwrite = channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = True
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

            # Remove the locked channel from the database
            await self.db.unlock_channel_in_db(interaction.guild.id, channel.id)

            # Send a message in the unlocked channel indicating the reason
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
            # Log the action
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

    # Lock All Channels Command with Progress Indicator
    @app_commands.command(name="lockall", description="Lock all text channels in the server.")
    @app_commands.describe(reason="Reason for locking all channels.")
    @app_commands.check(is_moderator)
    async def lock_all_channels(self, interaction: discord.Interaction, reason: str = "No reason provided."):
        """
        Locks all text channels in the server by preventing @everyone from sending messages.

        :param interaction: The command interaction.
        :param reason: Reason for locking all channels.
        """
        await interaction.response.defer(ephemeral=True)  # Use the thinking function
        try:
            text_channels = interaction.guild.text_channels
            total_channels = len(text_channels)
            locked_channels = 0

            # Send initial progress embed
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
                    # Check if @everyone can already send messages
                    can_send_messages = channel.permissions_for(interaction.guild.default_role).send_messages
                    if not can_send_messages:
                        self.bot.logger.info(f"Skipped locking {channel} as @everyone cannot send messages.")
                        continue  # Skip channels already locked

                    # Lock the channel
                    overwrite = channel.overwrites_for(interaction.guild.default_role)
                    overwrite.send_messages = False
                    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

                    # Record the locked channel in the database
                    await self.db.lock_channel_in_db(interaction.guild.id, channel.id)

                    # Send a message in the locked channel indicating the reason
                    await channel.send(
                        embed=discord.Embed(
                            description=f"🔒 This channel has been locked by {interaction.user.mention}.\n**Reason:** {reason}",
                            color=discord.Color.orange()
                        )
                    )

                    locked_channels += 1
                    self.bot.logger.info(f"{interaction.user} locked {channel} for reason: {reason}")

                    # Update progress embed every 5 channels to prevent rate limits
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

            # Final update
            final_embed = discord.Embed(
                title="🔒 All Channels Locked",
                description=f"✅ Locked {locked_channels}/{total_channels} text channels.\n**Reason:** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            await progress_message.edit(embed=final_embed)
            self.bot.logger.info(f"{interaction.user} locked all channels for reason: {reason} ({locked_channels}/{total_channels} successful)")
            # Log the action
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

    # Unlock All Channels Command with Progress Indicator
    @app_commands.command(name="unlockall", description="Unlock all text channels in the server.")
    @app_commands.describe(reason="Reason for unlocking all channels.")
    @app_commands.check(is_moderator)
    async def unlock_all_channels(self, interaction: discord.Interaction, reason: str = "No reason provided."):
        """
        Unlocks all text channels in the server by allowing @everyone to send messages.

        :param interaction: The command interaction.
        :param reason: Reason for unlocking all channels.
        """
        await interaction.response.defer(ephemeral=True)  # Use the thinking function
        try:
            text_channels = interaction.guild.text_channels
            total_channels = len(text_channels)
            unlocked_channels = 0

            # Send initial progress embed
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
                    # Check if the bot had previously locked this channel
                    is_locked_by_bot = await self.db.is_channel_locked(interaction.guild.id, channel.id)
                    if not is_locked_by_bot:
                        self.bot.logger.info(f"Skipped unlocking {channel} as it was not locked by the bot.")
                        continue  # Skip channels not locked by the bot

                    # Unlock the channel
                    overwrite = channel.overwrites_for(interaction.guild.default_role)
                    overwrite.send_messages = True
                    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

                    # Remove the locked channel from the database
                    await self.db.unlock_channel_in_db(interaction.guild.id, channel.id)

                    # Send a message in the unlocked channel indicating the reason
                    await channel.send(
                        embed=discord.Embed(
                            description=f"🔓 This channel has been unlocked by {interaction.user.mention}.\n**Reason:** {reason}",
                            color=discord.Color.green()
                        )
                    )

                    unlocked_channels += 1
                    self.bot.logger.info(f"{interaction.user} unlocked {channel} for reason: {reason}")

                    # Update progress embed every 5 channels to prevent rate limits
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

            # Final update
            final_embed = discord.Embed(
                title="🔓 All Channels Unlocked",
                description=f"✅ Unlocked {unlocked_channels}/{total_channels} text channels.\n**Reason:** {reason}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            await progress_message.edit(embed=final_embed)
            self.bot.logger.info(f"{interaction.user} unlocked all channels for reason: {reason} ({unlocked_channels}/{total_channels} successful)")
            # Log the action
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
        """
        Logs a moderation action to the designated moderation log channel.

        :param guild: The guild where the action took place.
        :param action: The type of action (e.g., Ban, Kick).
        :param executor: The user who performed the action.
        :param target: The member who was acted upon.
        :param reason: The reason for the action.
        :param duration: Duration for timeout actions.
        """
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
        """
        Logs a channel moderation action to the designated moderation log channel.

        :param guild: The guild where the action took place.
        :param action: The type of action (e.g., Lock Channel, Unlock Channel).
        :param executor: The user who performed the action.
        :param channel: The channel acted upon.
        :param reason: The reason for the action.
        """
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

    # Cog-level error handler
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """
        Handles errors for all commands in this cog.

        :param interaction: The command interaction.
        :param error: The error that occurred.
        """
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

# Setup function to add the cog to the bot
async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
    bot.logger.info("Moderation Cog has been added to the bot.")
