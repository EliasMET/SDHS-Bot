import discord
from discord.ext import commands, tasks
from discord import app_commands

import re
import logging
from datetime import datetime, timedelta
import math
import aiohttp
import asyncio

# Logger setup
logger = logging.getLogger("AutoMod")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
logger.addHandler(handler)

# Define the check function outside the class
async def is_admin_or_owner(interaction: discord.Interaction) -> bool:
    # Access bot via interaction.client
    bot = interaction.client
    # Check if owner_id is cached
    if not hasattr(bot, 'owner_id'):
        app_info = await bot.application_info()
        bot.owner_id = app_info.owner.id
    bot_owner_id = bot.owner_id
    if interaction.user.id == bot_owner_id:
        return True
    if interaction.user.guild_permissions.administrator:
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

        self.previous_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.blurple)
        self.next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.blurple)
        self.previous_button.callback = self.previous_page
        self.next_button.callback = self.next_page

        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.update_buttons()

    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1

    def create_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        embed = discord.Embed(
            title=f"Warnings for {self.user}",
            color=0xFF0000,
            description=f"Page {self.current_page + 1}/{self.total_pages}",
        )
        for warn in self.warnings[start:end]:
            embed.add_field(
                name=f"Warning ID: {warn[5]}",
                value=(
                    f"**Reason:** {warn[3]}\n"
                    f"**Moderator:** <@{warn[2]}>\n"
                    f"**Date:** <t:{int(warn[4])}:F>"
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

class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = None  # Placeholder for the database manager instance
        self.target_server_id = 1287288514186182686  # Replace with your server ID

        # Patterns for auto-moderation
        self.roblox_group_regex = re.compile(
            r"https?://www\.roblox\.com/communities/\d+/[a-zA-Z0-9\-]+",
            re.IGNORECASE
        )
        self.discord_invite_regex = re.compile(
            r"(https?://)?(www\.)?(discord\.(gg|io|me|li)|discordapp\.com/invite)/[a-zA-Z0-9]+",
            re.IGNORECASE
        )
        self.profanity_list = []  # Will be loaded asynchronously
        self.profanity_pattern = None  # Will be set after loading

        # Start the tasks
        self.expire_warnings_task.start()
        self.load_profanity_list_task.start()

    async def cog_load(self):
        self.db = self.bot.database  # Access DatabaseManager from the bot instance
        if not self.db:
            raise ValueError("DatabaseManager is not initialized in the bot.")

    def is_target_server(self, guild: discord.Guild) -> bool:
        return guild and guild.id == self.target_server_id

    async def handle_message_violation(self, message: discord.Message, reason: str):
        try:
            # Delete the violating message instantly
            await message.delete()

            # Log the violation to the database
            warn_id = await self.db.add_warn(
                user_id=message.author.id,
                server_id=message.guild.id,
                moderator_id=self.bot.user.id,
                reason=reason,
            )

            # Send a plain warning message
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
            if warning_count == 3:
                timeout_duration = timedelta(minutes=10)
                await message.author.timeout(timeout_duration, reason="Reached 3 warnings")
                await message.channel.send(
                    f"🚫 {message.author.mention} has been timed out for 10 minutes due to accumulating 3 warnings."
                )
            elif warning_count == 6:
                timeout_duration = timedelta(hours=24)
                await message.author.timeout(timeout_duration, reason="Reached 6 warnings")
                await message.channel.send(
                    f"🚫 {message.author.mention} has been timed out for 24 hours due to accumulating 6 warnings."
                )

            # Delete the moderation message after 10 seconds
            await asyncio.sleep(10)
            await moderation_message.delete()

            # Log the automod action if logging is enabled
            server_settings = await self.db.get_server_settings(message.guild.id)
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
                        log_embed.set_footer(text=f"User ID: {message.author.id}")
                        await log_channel.send(embed=log_embed)
        except Exception as e:
            logger.error(f"Failed to handle message violation: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.is_target_server(message.guild) or message.author.bot:
            return

        # Check if automod is enabled for this server
        server_settings = await self.db.get_server_settings(message.guild.id)
        if not server_settings.get('automod_enabled', True):
            return

        content = message.content

        if self.roblox_group_regex.search(content):
            await self.handle_message_violation(message, "Posting Roblox group links.")
        elif self.discord_invite_regex.search(content):
            await self.handle_message_violation(message, "Posting Discord invite links.")
        elif self.profanity_pattern and self.profanity_pattern.search(content):
            await self.handle_message_violation(message, "Using prohibited language.")

    @tasks.loop(minutes=5)
    async def expire_warnings_task(self):
        """Task to expire warnings older than 1 hour."""
        try:
            expiration_timestamp = int((datetime.now() - timedelta(hours=1)).timestamp())
            # Remove expired warnings directly
            await self.db.remove_expired_warnings(expiration_timestamp)
            logger.info(f"Expired warnings older than {expiration_timestamp}.")
        except Exception as e:
            logger.error(f"Error in warning expiration task: {e}")

    @tasks.loop(count=1)
    async def load_profanity_list_task(self):
        """Load the profanity list and compile the regex pattern."""
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
                        logger.info("Profanity list loaded and regex compiled successfully.")
                    else:
                        logger.error(f"Failed to load profanity list: HTTP {response.status}")
        except Exception as e:
            logger.error(f"Error loading profanity list: {e}")

    @app_commands.command(name="settings", description="Configure automod settings.")
    @app_commands.check(is_admin_or_owner)
    async def settings(self, interaction: discord.Interaction):
        if not self.is_target_server(interaction.guild):
            embed = discord.Embed(
                title="Permission Denied",
                description="This command can only be used in the designated server.",
                color=0xFF0000,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Use the thinking function
        await interaction.response.defer(ephemeral=True)

        # Fetch current settings
        server_settings = await self.db.get_server_settings(interaction.guild.id)
        if not server_settings:
            await self.db.initialize_server_settings(interaction.guild.id)
            server_settings = await self.db.get_server_settings(interaction.guild.id)

        # Create the settings embed
        embed = self.create_settings_embed(server_settings)

        # Create the view with buttons
        view = SettingsView(self.db, interaction.guild)
        view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    def create_settings_embed(self, server_settings):
        automod_status = "✅ Enabled" if server_settings.get('automod_enabled') else "❌ Disabled"
        logging_status = "✅ Enabled" if server_settings.get('automod_logging_enabled') else "❌ Disabled"
        log_channel_id = server_settings.get('automod_log_channel_id')
        if log_channel_id:
            log_channel = f"<#{log_channel_id}>"
        else:
            log_channel = "Not Set"

        embed = discord.Embed(
            title="⚙️ Automod Settings",
            color=0x5865F2,
            description="Use the buttons below to configure settings."
        )
        embed.add_field(name="Automod Status", value=automod_status, inline=True)
        embed.add_field(name="Logging Status", value=logging_status, inline=True)
        embed.add_field(name="Log Channel", value=log_channel, inline=False)
        embed.set_footer(text="Settings will timeout after 3 minutes of inactivity.")
        return embed

    @app_commands.command(name="warns", description="View all warnings for a user.")
    @app_commands.describe(user="The user to view warnings for.")
    @app_commands.check(is_admin_or_owner)
    async def warns(self, interaction: discord.Interaction, user: discord.Member):
        if not self.is_target_server(interaction.guild):
            embed = discord.Embed(
                title="Permission Denied",
                description="This command can only be used in the designated server.",
                color=0xFF0000,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Use the thinking function
        await interaction.response.defer(ephemeral=True)

        warnings = await self.db.get_warnings(user_id=user.id, server_id=interaction.guild.id)
        if warnings:
            if len(warnings) > 7:
                view = WarningsView(warnings, user)
                embed = view.create_embed()
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                embed = discord.Embed(
                    title=f"Warnings for {user}",
                    color=0xFF0000,
                )
                for warn in warnings:
                    embed.add_field(
                        name=f"Warning ID: {warn[5]}",
                        value=(
                            f"**Reason:** {warn[3]}\n"
                            f"**Moderator:** <@{warn[2]}>\n"
                            f"**Date:** <t:{int(warn[4])}:F>"
                        ),
                        inline=False,
                    )
                await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="No Warnings Found",
                description=f"{user.mention} has no recorded warnings.",
                color=0x00FF00,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Clear all warnings for a user.")
    @app_commands.describe(user="The user to clear warnings for.")
    @app_commands.check(is_admin_or_owner)
    async def clearwarnings(self, interaction: discord.Interaction, user: discord.Member):
        if not self.is_target_server(interaction.guild):
            embed = discord.Embed(
                title="Permission Denied",
                description="This command can only be used in the designated server.",
                color=0xFF0000,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Use the thinking function
        await interaction.response.defer(ephemeral=True)

        await self.db.clear_all_warnings(user_id=user.id, server_id=interaction.guild.id)
        embed = discord.Embed(
            title="Warnings Cleared",
            description=f"All warnings for {user.mention} have been cleared.",
            color=0x00FF00,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarn", description="Clear a specific warning for a user.")
    @app_commands.describe(user="The user to clear warning for.", warn_id="The ID of the warning to clear.")
    @app_commands.check(is_admin_or_owner)
    async def clearwarn(self, interaction: discord.Interaction, user: discord.Member, warn_id: int):
        if not self.is_target_server(interaction.guild):
            embed = discord.Embed(
                title="Permission Denied",
                description="This command can only be used in the designated server.",
                color=0xFF0000,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Use the thinking function
        await interaction.response.defer(ephemeral=True)

        # Attempt to remove the warning
        result = await self.db.remove_warn(warn_id=warn_id, user_id=user.id, server_id=interaction.guild.id)
        if result:
            embed = discord.Embed(
                title="Warning Removed",
                description=f"Warning ID {warn_id} for {user.mention} has been removed.",
                color=0x00FF00,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="Warning Not Found",
                description=f"No warning with ID {warn_id} found for {user.mention}.",
                color=0xFF0000,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    # Error handlers for commands
    @warns.error
    async def warns_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="Missing Permissions",
                description="You need the `Administrator` permission to use this command.",
                color=0xFF0000,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            logger.error(f"Error in /warns command: {error}")
            raise error

    @clearwarnings.error
    async def clearwarnings_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="Missing Permissions",
                description="You need the `Administrator` permission to use this command.",
                color=0xFF0000,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            logger.error(f"Error in /clearwarnings command: {error}")
            raise error

    @clearwarn.error
    async def clearwarn_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="Missing Permissions",
                description="You need the `Administrator` permission to use this command.",
                color=0xFF0000,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            logger.error(f"Error in /clearwarn command: {error}")
            raise error

    @settings.error
    async def settings_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="Missing Permissions",
                description="You need the `Administrator` permission to use this command.",
                color=0xFF0000,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            logger.error(f"Error in /settings command: {error}")
            raise error

# Define the SettingsView for interactive settings configuration
class SettingsView(discord.ui.View):
    def __init__(self, db, guild):
        super().__init__(timeout=180)  # View will timeout after 3 minutes
        self.db = db
        self.guild = guild
        self.message = None  # Will be set when the message is sent

    @discord.ui.button(label="Toggle Automod", style=discord.ButtonStyle.primary, emoji="🔄")
    async def toggle_automod(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.db.toggle_server_setting(self.guild.id, 'automod_enabled')
        await self.update_settings_message()

    @discord.ui.button(label="Toggle Logging", style=discord.ButtonStyle.primary, emoji="📝")
    async def toggle_logging(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.db.toggle_server_setting(self.guild.id, 'automod_logging_enabled')
        await self.update_settings_message()

    @discord.ui.button(label="Set Log Channel", style=discord.ButtonStyle.primary, emoji="📌")
    async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Please mention the channel you want to set as the log channel.",
            ephemeral=True
        )

        def check(m):
            return m.author.id == interaction.user.id and m.channel == interaction.channel

        try:
            msg = await interaction.client.wait_for('message', check=check, timeout=60)
            if msg.channel_mentions:
                channel = msg.channel_mentions[0]
                await self.db.update_server_setting(self.guild.id, 'automod_log_channel_id', str(channel.id))
                await msg.delete()
                await self.update_settings_message()
            else:
                await interaction.followup.send("No channel mentioned. Please try again.", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("You took too long to respond.", ephemeral=True)

    async def update_settings_message(self):
        server_settings = await self.db.get_server_settings(self.guild.id)
        embed = AutoMod.create_settings_embed(self=None, server_settings=server_settings)
        await self.message.edit(embed=embed, view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)

# Setup function
async def setup(bot):
    await bot.add_cog(AutoMod(bot))
