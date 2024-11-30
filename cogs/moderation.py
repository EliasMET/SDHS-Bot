"""
Moderation Cog
Provides ban, kick, timeout, lock channel, unlock channel,
lock all channels, and unlock all channels commands.

Version: 1.1.0
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import re
from datetime import timedelta
import logging

# Logger setup for the Moderation Cog
logger = logging.getLogger("ModerationCog")
logger.setLevel(logging.DEBUG)  # Set to DEBUG for detailed logs
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
logger.addHandler(handler)

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
        # Initialize the database manager
        self.db = self.bot.database
        if not self.db:
            logger.error("DatabaseManager is not initialized in the bot.")
            raise ValueError("DatabaseManager is not initialized in the bot.")

        # Ensure owner_id is cached
        if not hasattr(self.bot, 'owner_id'):
            app_info = await self.bot.application_info()
            self.bot.owner_id = app_info.owner.id

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
        try:
            await member.ban(reason=reason, delete_message_days=0)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"✅ Successfully banned {member.mention}.\n**Reason:** {reason}",
                    color=0x00FF00
                ),
                ephemeral=True
            )
            logger.info(f"{interaction.user} banned {member} for reason: {reason}")
            # Log the action
            await self.log_action(interaction.guild, "Ban", interaction.user, member, reason)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ I do not have permission to ban this member.",
                    color=0xFF0000
                ),
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ Failed to ban member: {e}",
                    color=0xFF0000
                ),
                ephemeral=True
            )

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
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"✅ Successfully kicked {member.mention}.\n**Reason:** {reason}",
                    color=0x00FF00
                ),
                ephemeral=True
            )
            logger.info(f"{interaction.user} kicked {member} for reason: {reason}")
            # Log the action
            await self.log_action(interaction.guild, "Kick", interaction.user, member, reason)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ I do not have permission to kick this member.",
                    color=0xFF0000
                ),
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ Failed to kick member: {e}",
                    color=0xFF0000
                ),
                ephemeral=True
            )

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
        try:
            timeout_seconds = self.parse_duration(duration)
            if timeout_seconds is None:
                raise ValueError("Invalid duration format. Use formats like `10m`, `2h`, `1d`.")

            await member.timeout(timedelta(seconds=timeout_seconds), reason=reason)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"✅ Successfully timed out {member.mention} for {duration}.\n**Reason:** {reason}",
                    color=0x00FF00
                ),
                ephemeral=True
            )
            logger.info(f"{interaction.user} timed out {member} for {duration} with reason: {reason}")
            # Log the action
            await self.log_action(interaction.guild, "Timeout", interaction.user, member, reason, duration)
        except ValueError as ve:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ {ve}",
                    color=0xFF0000
                ),
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ I do not have permission to timeout this member.",
                    color=0xFF0000
                ),
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ Failed to timeout member: {e}",
                    color=0xFF0000
                ),
                ephemeral=True
            )

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
        channel = channel or interaction.channel
        try:
            # Prevent @everyone from sending messages
            overwrite = channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = False
            # Ensure the bot can send messages in the channel
            overwrite_bot = channel.overwrites_for(interaction.guild.me)
            overwrite_bot.send_messages = True
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)
            await channel.set_permissions(interaction.guild.me, overwrite=overwrite_bot, reason=reason)

            # Send a message in the channel about the lock
            embed = discord.Embed(
                description=f"🔒 This channel has been locked by {interaction.user.mention}.\n**Reason:** {reason}",
                color=0xFFA500  # Orange color for notifications
            )
            await channel.send(embed=embed)

            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"✅ {channel.mention} has been locked.\n**Reason:** {reason}",
                    color=0x00FF00
                ),
                ephemeral=True
            )
            logger.info(f"{interaction.user} locked {channel} for reason: {reason}")
            # Log the action
            await self.log_channel_action(interaction.guild, "Lock Channel", interaction.user, channel, reason)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ I do not have permission to modify this channel.",
                    color=0xFF0000
                ),
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ Failed to lock channel: {e}",
                    color=0xFF0000
                ),
                ephemeral=True
            )

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
        channel = channel or interaction.channel
        try:
            # Allow @everyone to send messages
            overwrite = channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = True
            # Ensure the bot can send messages in the channel
            overwrite_bot = channel.overwrites_for(interaction.guild.me)
            overwrite_bot.send_messages = True
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)
            await channel.set_permissions(interaction.guild.me, overwrite=overwrite_bot, reason=reason)

            # Send a message in the channel about the unlock
            embed = discord.Embed(
                description=f"🔓 This channel has been unlocked by {interaction.user.mention}.\n**Reason:** {reason}",
                color=0xFFA500  # Orange color for notifications
            )
            await channel.send(embed=embed)

            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"✅ {channel.mention} has been unlocked.\n**Reason:** {reason}",
                    color=0x00FF00
                ),
                ephemeral=True
            )
            logger.info(f"{interaction.user} unlocked {channel} for reason: {reason}")
            # Log the action
            await self.log_channel_action(interaction.guild, "Unlock Channel", interaction.user, channel, reason)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ I do not have permission to modify this channel.",
                    color=0xFF0000
                ),
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ Failed to unlock channel: {e}",
                    color=0xFF0000
                ),
                ephemeral=True
            )

    # Lock All Channels Command
    @app_commands.command(name="lockall", description="Lock all text channels in the server.")
    @app_commands.describe(reason="Reason for locking all channels.")
    @app_commands.check(is_moderator)
    async def lock_all_channels(self, interaction: discord.Interaction, reason: str = "No reason provided."):
        """
        Locks all text channels in the server by preventing @everyone from sending messages.

        :param interaction: The command interaction.
        :param reason: Reason for locking all channels.
        """
        try:
            for channel in interaction.guild.text_channels:
                overwrite = channel.overwrites_for(interaction.guild.default_role)
                overwrite.send_messages = False
                overwrite_bot = channel.overwrites_for(interaction.guild.me)
                overwrite_bot.send_messages = True
                await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)
                await channel.set_permissions(interaction.guild.me, overwrite=overwrite_bot, reason=reason)

                # Send a message in each channel about the lock
                embed = discord.Embed(
                    description=f"🔒 This channel has been locked by {interaction.user.mention}.\n**Reason:** {reason}",
                    color=0xFFA500  # Orange color for notifications
                )
                await channel.send(embed=embed)

            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"✅ All text channels have been locked.\n**Reason:** {reason}",
                    color=0x00FF00
                ),
                ephemeral=True
            )
            logger.info(f"{interaction.user} locked all channels for reason: {reason}")
            # Log the action
            await self.log_channel_action(interaction.guild, "Lock All Channels", interaction.user, None, reason)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ I do not have permission to modify one or more channels.",
                    color=0xFF0000
                ),
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ Failed to lock all channels: {e}",
                    color=0xFF0000
                ),
                ephemeral=True
            )

    # Unlock All Channels Command
    @app_commands.command(name="unlockall", description="Unlock all text channels in the server.")
    @app_commands.describe(reason="Reason for unlocking all channels.")
    @app_commands.check(is_moderator)
    async def unlock_all_channels(self, interaction: discord.Interaction, reason: str = "No reason provided."):
        """
        Unlocks all text channels in the server by allowing @everyone to send messages.

        :param interaction: The command interaction.
        :param reason: Reason for unlocking all channels.
        """
        try:
            for channel in interaction.guild.text_channels:
                overwrite = channel.overwrites_for(interaction.guild.default_role)
                overwrite.send_messages = True
                overwrite_bot = channel.overwrites_for(interaction.guild.me)
                overwrite_bot.send_messages = True
                await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)
                await channel.set_permissions(interaction.guild.me, overwrite=overwrite_bot, reason=reason)

                # Send a message in each channel about the unlock
                embed = discord.Embed(
                    description=f"🔓 This channel has been unlocked by {interaction.user.mention}.\n**Reason:** {reason}",
                    color=0xFFA500  # Orange color for notifications
                )
                await channel.send(embed=embed)

            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"✅ All text channels have been unlocked.\n**Reason:** {reason}",
                    color=0x00FF00
                ),
                ephemeral=True
            )
            logger.info(f"{interaction.user} unlocked all channels for reason: {reason}")
            # Log the action
            await self.log_channel_action(interaction.guild, "Unlock All Channels", interaction.user, None, reason)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ I do not have permission to modify one or more channels.",
                    color=0xFF0000
                ),
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ Failed to unlock all channels: {e}",
                    color=0xFF0000
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
                logger.warning(f"Mod log channel not set for guild {guild.name} (ID: {guild.id}).")
                return
            log_channel = guild.get_channel(log_channel_id)
            if not log_channel:
                logger.warning(f"Mod log channel ID {log_channel_id} not found in guild {guild.name} (ID: {guild.id}).")
                return

            embed = discord.Embed(
                title=f"📜 {action}",
                color=0xFFD700,  # Gold color for logs
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Executor", value=f"{executor} (ID: {executor.id})", inline=True)
            embed.add_field(name="Target", value=f"{target} (ID: {target.id})", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            if duration:
                embed.add_field(name="Duration", value=duration, inline=False)
            embed.set_footer(text=f"Guild: {guild.name} (ID: {guild.id})")
            await log_channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to log moderation action: {e}")

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
                logger.warning(f"Mod log channel not set for guild {guild.name} (ID: {guild.id}).")
                return
            log_channel = guild.get_channel(log_channel_id)
            if not log_channel:
                logger.warning(f"Mod log channel ID {log_channel_id} not found in guild {guild.name} (ID: {guild.id}).")
                return

            embed = discord.Embed(
                title=f"📜 {action}",
                color=0xFFD700,  # Gold color for logs
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Executor", value=f"{executor} (ID: {executor.id})", inline=True)
            if channel:
                embed.add_field(name="Channel", value=f"{channel.mention} (ID: {channel.id})", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"Guild: {guild.name} (ID: {guild.id})")
            await log_channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to log channel moderation action: {e}")

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
        elif isinstance(error, app_commands.CommandInvokeError):
            embed = discord.Embed(
                title="Error",
                description=f"An unexpected error occurred: {error.original}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.error(f"Error in command {interaction.command.name}: {error.original}")
        else:
            embed = discord.Embed(
                title="Error",
                description=f"An error occurred: {error}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.error(f"Unhandled error in command {interaction.command.name}: {error}")

# Setup function to add the cog to the bot
async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
