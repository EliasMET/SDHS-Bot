import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import logging
import os
import asyncio
import matplotlib.pyplot as plt
import io
from collections import defaultdict

logger = logging.getLogger('discord_bot')

class PaginatedDropdownView(discord.ui.View):
    def __init__(self, groups, user, lock_time, group_settings, channel_id, bot, roblox_user_id, settings_cog, per_page=25):
        super().__init__(timeout=180)
        self.groups = list(groups.items())
        self.user = user
        self.lock_time = lock_time
        self.group_settings = group_settings
        self.channel_id = channel_id
        self.bot = bot
        self.settings_cog = settings_cog
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = (len(self.groups) - 1) // per_page + 1
        self.roblox_user_id = roblox_user_id

        self.select = discord.ui.Select(
            placeholder="Select a group",
            min_values=1,
            max_values=1,
            options=self.get_options()
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

        if self.total_pages > 1:
            self.prev_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.primary)
            self.next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.primary)
            self.prev_button.callback = self.prev_page
            self.next_button.callback = self.next_page
            self.add_item(self.prev_button)
            self.add_item(self.next_button)

    def get_options(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        return [
            discord.SelectOption(
                label=group['event_name'],
                description=group['description'][:50],
                value=str(group_id)
            )
            for group_id, group in self.groups[start:end]
        ]

    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        selected_group_id = self.select.values[0]
        group_info = self.group_settings[selected_group_id]

        lock_timestamp = discord.utils.utcnow() + timedelta(minutes=self.lock_time)
        lock_unix = int(lock_timestamp.timestamp())
        lock_time_formatted = f"<t:{lock_unix}:R>"

        link = f"https://www.roblox.com/users/{self.roblox_user_id}/profile"
        reqs = group_info["requirements"] if group_info.get("requirements") else []
        req_text = "\n".join(reqs) if reqs else "None"

        # Get ping roles for this specific group
        group_data = await self.bot.database.get_tryout_group(interaction.guild.id, selected_group_id)
        ping_roles = group_data[4] if group_data else []  # Index 4 contains ping_roles
        pings = " ".join(f"<@&{rid}>" for rid in ping_roles) if ping_roles else ""

        # Generate a voice channel invite link if the user is in a voice channel
        voice_channel = interaction.user.voice.channel if interaction.user.voice else None
        vc_display = ""
        voice_invite = None
        if voice_channel:
            invite = await voice_channel.create_invite(max_age=43200)  # 12 hours in seconds
            vc_display = invite.url
            voice_invite = invite.url

        # Add one empty line between requirements and status
        # Bold the event name after [DIVISION]
        tryout_message = (
            f"[DIVISION] **{group_info['event_name']}**\n"
            f"[HOST] {self.user.mention}\n"
            f"[LOCATION] {link} < JOIN PROFILE\n"
            f"[INFO] {group_info['description']}\n"
            f"[REQUIREMENTS]\n"
            f"{req_text}\n"
            f"\n"  # One extra newline for empty line before STATUS
            f"[STATUS] Locking at {lock_time_formatted}\n"
            f"{pings}\n"
            f"{vc_display}"
        )

        channel = self.bot.get_channel(self.channel_id)
        if channel:
            try:
                # Send the tryout message first
                message = await channel.send(tryout_message)
                
                # Log the tryout session
                session_id = await self.bot.database.create_tryout_session(
                    guild_id=guild_id,
                    host_id=self.user.id,
                    group_id=selected_group_id,
                    group_name=group_info['event_name'],
                    channel_id=self.channel_id,
                    voice_channel_id=voice_channel.id if voice_channel else None,
                    lock_timestamp=lock_timestamp.isoformat(),
                    requirements=reqs,
                    description=group_info['description'],
                    message_id=message.id,
                    voice_invite=voice_invite
                )

                # Send log message with session ID
                logger.info(f"Attempting to send tryout log for group {group_info['event_name']} in guild {guild_id}")
                tryout_cog = self.bot.get_cog('tryout')
                await tryout_cog.send_tryout_log(guild_id, interaction.user, group_info, lock_timestamp, session_id)
                logger.info(f"Successfully sent tryout log for group {group_info['event_name']}")

                # Schedule message deletion
                total_delete_delay = (self.lock_time + 25) * 60  # Convert to seconds (lock time + 25 minutes)
                task = asyncio.create_task(self.bot.get_cog('tryout').delete_tryout_message(channel.id, message.id, total_delete_delay))
                self.bot.get_cog('tryout').message_deletion_tasks[message.id] = task

                confirmation_embed = discord.Embed(
                    title="✅ Success",
                    description=(
                        f"🎯 The tryout announcement for **{group_info['event_name']}** has been sent!\n"
                        f"📝 Session ID: `{session_id}`"
                    ),
                    color=0x00FF00,
                )
                await interaction.followup.edit_message(
                    message_id=interaction.message.id, 
                    embed=confirmation_embed, 
                    view=None
                )
                logger.info(
                    f"Tryout session {session_id} created for '{group_info['event_name']}' by {self.user} (ID: {self.user.id}) in guild {guild_id}."
                )
            except Exception as e:
                logger.error(
                    f"Failed to create tryout session for '{group_info['event_name']}' by {self.user} (ID: {self.user.id}) "
                    f"to channel {self.channel_id} in guild {guild_id}: {e}",
                    exc_info=True
                )
                error_embed = discord.Embed(
                    title="Error",
                    description="An unexpected error occurred while creating the tryout session.",
                    color=0xFF0000,
                )
                await interaction.followup.edit_message(
                    message_id=interaction.message.id, 
                    embed=error_embed, 
                    view=None
                )
        else:
            logger.error(
                f"Channel ID {self.channel_id} not found in guild {guild_id}. Unable to send tryout announcement for '{group_info['event_name']}'."
            )
            error_embed = discord.Embed(
                title="Error",
                description="Unable to find the specified channel for the tryout announcement.",
                color=0xFF0000,
            )
            await interaction.followup.edit_message(
                message_id=interaction.message.id, 
                embed=error_embed, 
                view=None
            )

    async def prev_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.select.options = self.get_options()
            await interaction.response.edit_message(view=self)

    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.select.options = self.get_options()
            await interaction.response.edit_message(view=self)


class Tryout(commands.Cog, name="tryout"):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.db = None
        self.bot.guild_id = None
        self.logger = logging.getLogger('discord_bot')
        self.message_deletion_tasks = {}

    async def delete_tryout_message(self, channel_id: int, message_id: int, delay: int):
        """Delete a tryout message after the specified delay in seconds"""
        await asyncio.sleep(delay)
        try:
            channel = self.bot.get_channel(channel_id)
            if channel:
                message = await channel.fetch_message(message_id)
                if message:
                    await message.delete()
                    self.logger.info(f"Deleted tryout message {message_id} from channel {channel_id}")
        except Exception as e:
            self.logger.error(f"Failed to delete tryout message {message_id}: {e}")
        finally:
            # Clean up the task reference
            if message_id in self.message_deletion_tasks:
                del self.message_deletion_tasks[message_id]

    async def schedule_message_deletion(self, channel_id: int, message_id: int, lock_time: int):
        """Schedule a message for deletion after lock_time + 25 minutes"""
        total_delete_delay = (lock_time + 25) * 60  # Convert to seconds (lock time + 25 minutes)
        task = asyncio.create_task(self.delete_tryout_message(channel_id, message_id, total_delete_delay))
        self.message_deletion_tasks[message_id] = task

    async def send_tryout_log(self, guild_id: int, host_user, group_info: dict, lock_timestamp: datetime, session_id: str = None):
        """Send a log message to the configured tryout log channel"""
        try:
            self.logger.info(f"Attempting to send tryout log for guild {guild_id}")
            
            log_channel_id = await self.db.get_tryout_log_channel_id(guild_id)
            self.logger.info(f"Retrieved log channel ID: {log_channel_id}")
            
            if not log_channel_id:
                self.logger.warning(f"No tryout log channel configured for guild {guild_id}")
                return

            log_channel = self.bot.get_channel(log_channel_id)
            self.logger.info(f"Retrieved channel object: {log_channel}")
            
            if not log_channel:
                self.logger.warning(f"Tryout log channel {log_channel_id} not found in guild {guild_id}")
                return

            embed = discord.Embed(
                title=f"🎯 {group_info['event_name']}",
                color=discord.Color.blue(),
                description=f"{host_user.mention} • <t:{int(lock_timestamp.timestamp())}:R>"
            )
            
            if session_id:
                embed.set_footer(text=f"ID: {session_id}")

            self.logger.info(f"Sending tryout log message to channel {log_channel.id}")
            await log_channel.send(embed=embed)
            self.logger.info(f"Successfully sent tryout log for {group_info['event_name']} by {host_user} in guild {guild_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to send tryout log: {str(e)}", exc_info=True)

    async def cog_load(self):
        self.db = self.bot.database
        if not self.db:
            logger.error("DatabaseManager not initialized in the bot. Cannot load Tryout Cog.")
            raise ValueError("DatabaseManager is not initialized in the bot.")
        self.bot.logger.info("Tryout Cog loaded successfully.")

    async def fetch_all_roblox_groups(self, session, roblox_url):
        all_groups = []
        cursor = None
        guild_id = self.bot.guild_id
        logger.info(f"Fetching Roblox groups for guild {guild_id} from {roblox_url}")
        while True:
            url = roblox_url
            if cursor:
                url += f"?cursor={cursor}"
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Roblox API returned status {response.status} for URL: {url} in guild {guild_id}")
                    break
                data = await response.json()
                all_groups.extend(data.get("data", []))
                cursor = data.get("nextPageCursor")
                if not cursor:
                    break
        logger.info(f"Fetched total {len(all_groups)} Roblox groups for guild {guild_id}.")
        return all_groups

    @app_commands.command(
        name="tryout",
        description="Announce a tryout."
    )
    async def tryout(
        self,
        interaction: discord.Interaction,
        lock_time: int = 10,
    ) -> None:
        """Announce a tryout."""
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id

        try:
            # Check if user has required roles
            required_roles = await self.db.get_tryout_required_roles(guild_id)
            if required_roles:
                has_required_role = any(
                    str(role.id) in map(str, required_roles)
                    for role in interaction.user.roles
                )
                if not has_required_role:
                    logger.warning(
                        f"User {interaction.user} (ID: {interaction.user.id}) attempted /tryout without required roles in guild {guild_id}."
                    )
                    embed = discord.Embed(
                        title="Permission Error",
                        description="You don't have the required roles to use this command.",
                        color=0xFF0000
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

            # Get the configured tryout channel
            channel_id = await self.db.get_tryout_channel_id(guild_id)
            if not channel_id:
                logger.warning(
                    f"No tryout channel configured in guild {guild_id}. "
                    f"User {interaction.user} (ID: {interaction.user.id}) attempted /tryout."
                )
                embed = discord.Embed(
                    title="Config Error",
                    description="No tryout channel configured.",
                    color=0xFF0000
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Check if user is in an allowed voice channel
            user_vc = interaction.user.voice.channel if interaction.user.voice else None
            allowed_vcs = await self.db.get_tryout_allowed_vcs(guild_id)
            if allowed_vcs and (not user_vc or user_vc.id not in allowed_vcs):
                logger.warning(
                    f"User {interaction.user} (ID: {interaction.user.id}) attempted /tryout "
                    f"without being in an allowed voice channel in guild {guild_id}."
                )
                embed = discord.Embed(
                    title="Voice Channel Error",
                    description="You must be in an allowed voice channel to use this command.",
                    color=0xFF0000
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            async with aiohttp.ClientSession() as session:
                user_id = interaction.user.id
                bloxlink_url = f"https://api.blox.link/v4/public/guilds/{guild_id}/discord-to-roblox/{user_id}"
                headers = {"Authorization": os.getenv("BLOXLINK_TOKEN")}

                logger.info(
                    f"Fetching Roblox ID from Bloxlink for user {interaction.user} (ID: {interaction.user.id}) in guild {guild_id} via {bloxlink_url}"
                )
                async with session.get(bloxlink_url, headers=headers) as bloxlink_response:
                    bloxlink_data = await bloxlink_response.json()

                if bloxlink_response.status != 200 or not bloxlink_data.get('robloxID'):
                    logger.error(
                        f"Bloxlink API error for user {interaction.user} (ID: {interaction.user.id}) in guild {guild_id}. "
                        f"Status: {bloxlink_response.status}, Data: {bloxlink_data}"
                    )
                    embed = discord.Embed(
                        title="Error",
                        description="Failed to fetch Roblox User ID from Bloxlink. Ensure Bloxlink is configured correctly, or try again later.",
                        color=0xFF0000
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

                roblox_user_id = bloxlink_data["robloxID"]
                logger.info(f"Resolved Roblox user ID {roblox_user_id} for {interaction.user} (ID: {interaction.user.id}) in guild {guild_id}.")

                roblox_url = f"https://groups.roblox.com/v1/users/{roblox_user_id}/groups/roles"
                all_roblox_groups = await self.fetch_all_roblox_groups(session, roblox_url)

                if not all_roblox_groups:
                    logger.warning(
                        f"User {interaction.user} (ID: {interaction.user.id}) is not in any Roblox groups for guild {guild_id}."
                    )
                    embed = discord.Embed(title="Error", description="You are not in any Roblox groups.", color=0xFF0000)
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

                tryout_groups = await self.db.get_tryout_groups(interaction.guild.id)
                if not tryout_groups:
                    logger.warning(
                        f"No tryout groups configured in guild {guild_id}. "
                        f"User {interaction.user} (ID: {interaction.user.id}) attempted /tryout."
                    )
                    embed = discord.Embed(title="Config Error", description="No tryout groups set.", color=0xFF0000)
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

                # Process groups and find matches
                group_settings = {
                    str(g[0]): {
                        'description': g[1],
                        'event_name': g[2],
                        'requirements': g[3]
                    } for g in tryout_groups
                }

                matching_groups = {
                    str(group["group"]["id"]): group_settings[str(group["group"]["id"])]
                    for group in all_roblox_groups
                    if str(group["group"]["id"]) in group_settings
                }

                if not matching_groups:
                    logger.info(
                        f"No matching tryout groups found for user {interaction.user} (ID: {interaction.user.id}) in guild {guild_id}."
                    )
                    embed = discord.Embed(
                        title="Error",
                        description="No matching group found.",
                        color=0xFF0000
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

                # Get channel and verify it exists
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    logger.error(
                        f"Configured tryout channel {channel_id} not found in guild {guild_id}. "
                        f"User {interaction.user} (ID: {interaction.user.id}) tried announcing a tryout."
                    )
                    embed = discord.Embed(
                        title="Error",
                        description="Configured tryout channel not found. Please contact an administrator.",
                        color=0xFF0000
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

                # Handle single group case
                if len(matching_groups) == 1:
                    selected_group_id = next(iter(matching_groups.keys()))
                    group_info = matching_groups[selected_group_id]

                    # Prepare message content
                    lock_timestamp = discord.utils.utcnow() + timedelta(minutes=lock_time)
                    lock_unix = int(lock_timestamp.timestamp())
                    lock_time_formatted = f"<t:{lock_unix}:R>"
                    link = f"https://www.roblox.com/users/{roblox_user_id}/profile"
                    reqs = group_info["requirements"] if group_info.get("requirements") else []
                    req_text = "\n".join(reqs) if reqs else "None"

                    # Get ping roles for this specific group
                    group_data = await self.db.get_tryout_group(interaction.guild.id, selected_group_id)
                    ping_roles = group_data[4] if group_data else []  # Index 4 contains ping_roles
                    pings = " ".join(f"<@&{rid}>" for rid in ping_roles) if ping_roles else ""

                    # Generate voice channel invite
                    vc_display = ""
                    if user_vc:
                        invite = await user_vc.create_invite(max_age=43200)  # 12 hours
                        vc_display = invite.url

                    # Create tryout message
                    tryout_message = (
                        f"[DIVISION] **{group_info['event_name']}**\n"
                        f"[HOST] {interaction.user.mention}\n"
                        f"[LOCATION] {link} < JOIN PROFILE\n"
                        f"[INFO] {group_info['description']}\n"
                        f"[REQUIREMENTS]\n"
                        f"{req_text}\n"
                        f"\n"
                        f"[STATUS] Locking at {lock_time_formatted}\n"
                        f"{pings}\n"
                        f"{vc_display}"
                    )

                    try:
                        # Send the tryout message first
                        message = await channel.send(tryout_message)

                        # Create tryout session
                        session_id = await self.db.create_tryout_session(
                            guild_id=guild_id,
                            host_id=interaction.user.id,
                            group_id=selected_group_id,
                            group_name=group_info['event_name'],
                            channel_id=channel_id,
                            voice_channel_id=user_vc.id if user_vc else None,
                            lock_timestamp=lock_timestamp.isoformat(),
                            requirements=reqs,
                            description=group_info['description'],
                            message_id=message.id,
                            voice_invite=vc_display if user_vc else None
                        )

                        # Send log message with session ID
                        logger.info(f"Attempting to send tryout log for group {group_info['event_name']} in guild {guild_id}")
                        await self.send_tryout_log(guild_id, interaction.user, group_info, lock_timestamp, session_id)
                        logger.info(f"Successfully sent tryout log for group {group_info['event_name']}")

                        # Schedule message deletion
                        await self.schedule_message_deletion(channel.id, message.id, lock_time)

                        # Send confirmation
                        confirmation_embed = discord.Embed(
                            title="✅ Success",
                            description=(
                                f"🎯 The tryout for **{group_info['event_name']}** has been announced!\n"
                                f"📝 Session ID: `{session_id}`"
                            ),
                            color=0x00FF00,
                        )
                        await interaction.followup.send(embed=confirmation_embed, ephemeral=True)
                        logger.info(
                            f"Tryout session {session_id} created for '{group_info['event_name']}' by {interaction.user} "
                            f"(ID: {interaction.user.id}) in guild {guild_id}."
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to create tryout session for '{group_info['event_name']}' by {interaction.user} "
                            f"(ID: {interaction.user.id}) in guild {guild_id}: {e}",
                            exc_info=True
                        )
                        error_embed = discord.Embed(
                            title="Error",
                            description="An unexpected error occurred while creating the tryout session. Please try again.",
                            color=0xFF0000
                        )
                        await interaction.followup.send(embed=error_embed, ephemeral=True)
                        return
                else:
                    # Handle multiple groups case
                    logger.info(
                        f"Multiple ({len(matching_groups)}) matching groups found for user {interaction.user} "
                        f"(ID: {interaction.user.id}) in guild {guild_id}. Presenting dropdown selection."
                    )
                    embed = discord.Embed(
                        title="Select Group",
                        description="Select the group for this tryout.",
                        color=0x00FF00
                    )
                    view = PaginatedDropdownView(
                        matching_groups,
                        interaction.user,
                        lock_time,
                        matching_groups,
                        channel_id,
                        self.bot,
                        roblox_user_id,
                        settings_cog=self
                    )
                    view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(
                f"Unexpected error in /tryout command for user {interaction.user} (ID: {interaction.user.id}) "
                f"in guild {guild_id}: {e}",
                exc_info=True
            )
            error_embed = discord.Embed(
                title="Unexpected Error",
                description=(
                    "An unexpected error occurred. Please try again later or contact an administrator.\n"
                    f"Error: {type(e).__name__}: {e}"
                ),
                color=0xFF0000
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)

    @app_commands.command(
        name="data",
        description="Show tryout statistics for the server."
    )
    @app_commands.describe(
        days="Number of days to show (2-180 days, default 30)",
        user="Show only tryouts hosted by a specific user"
    )
    async def data(
        self,
        interaction: discord.Interaction,
        days: int = 30,
        user: discord.User = None
    ) -> None:
        """Show tryout statistics with a graph."""
        await interaction.response.defer()

        try:
            # Validate days parameter
            if days < 2:
                days = 2
            elif days > 180:
                days = 180

            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            start_unix = int(start_date.timestamp())
            end_unix = int(end_date.timestamp())

            # Build query
            query = {
                "guild_id": str(interaction.guild.id),
                "created_at": {
                    "$gte": start_date.isoformat(),
                    "$lte": end_date.isoformat()
                }
            }
            
            # Add user filter if specified
            if user:
                query["host_id"] = str(user.id)

            # Get tryout sessions
            sessions = await self.db.db["tryout_sessions"].find(query).to_list(None)

            if not sessions:
                embed = discord.Embed(
                    title="📊 No Data Available",
                    description=(
                        f"No tryouts were hosted between <t:{start_unix}:D> and <t:{end_unix}:D>"
                        f"{' by ' + user.mention if user else ''}"
                    ),
                    color=0x5865F2
                )
                await interaction.followup.send(embed=embed)
                return

            # Process data
            tryouts_by_date = defaultdict(int)
            tryouts_by_group = defaultdict(int)
            total_tryouts = len(sessions)
            active_hosts = set()

            # Fill in all dates in range with 0
            current_date = start_date
            while current_date <= end_date:
                tryouts_by_date[current_date.date()] = 0
                current_date += timedelta(days=1)

            # Count tryouts and gather additional stats
            for session in sessions:
                date = datetime.fromisoformat(session["created_at"]).date()
                tryouts_by_date[date] += 1
                tryouts_by_group[session["group_name"]] += 1
                active_hosts.add(session["host_id"])

            # Create the graph with improved styling
            plt.figure(figsize=(12, 6))
            plt.style.use('dark_background')
            
            # Plot data with enhanced visuals
            dates = list(tryouts_by_date.keys())
            counts = list(tryouts_by_date.values())
            
            # Create gradient fill
            gradient = plt.fill_between(dates, counts, alpha=0.2, color='#5865F2')
            line = plt.plot(dates, counts, marker='o', linestyle='-', linewidth=3, 
                    markersize=8, color='#5865F2', markerfacecolor='white', 
                    markeredgewidth=2, markeredgecolor='#5865F2', zorder=5)
            
            # Add value labels on points with date
            for x, y in zip(dates, counts):
                if y > 0:  # Only show label if there were tryouts
                    date_str = x.strftime('%b %d')  # Format date as "Jan 01"
                    label = f"{y}\n{date_str}"
                    plt.annotate(label, 
                        (x, y),
                        textcoords="offset points",
                        xytext=(0, 10),
                        ha='center',
                        fontsize=10,
                        fontweight='bold',
                        color='white',
                        bbox=dict(
                            boxstyle='round,pad=0.5',
                            fc='#2F3136',
                            ec='#5865F2',
                            alpha=0.8
                        )
                    )
            
            # Enhance grid and styling
            plt.grid(True, alpha=0.1, linestyle='--', color='gray')
            title = 'Tryout Activity Overview'
            if user:
                title += f' for {user.name}'
            plt.title(title, pad=20, color='white', fontsize=16, fontweight='bold')
            
            # Only show date labels if we have more than 14 days
            if days > 14:
                plt.xlabel('Date', color='white', fontsize=12, fontweight='bold', labelpad=10)
            
            plt.ylabel('Number of Tryouts', color='white', fontsize=12, fontweight='bold', labelpad=10)
            
            # Improve axis styling
            ax = plt.gca()
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_alpha(0.3)
            ax.spines['bottom'].set_alpha(0.3)
            
            # Format y-axis to show only integers
            ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
            
            # Format dates on x-axis based on time period
            if days <= 14:
                # For short periods, hide x-axis labels since we show dates in the bubbles
                ax.xaxis.set_ticklabels([])
                ax.xaxis.set_ticks([])
            else:
                # For longer periods, show abbreviated dates
                if days > 90:
                    date_formatter = plt.matplotlib.dates.DateFormatter('%b %Y')  # "Jan 2024"
                else:
                    date_formatter = plt.matplotlib.dates.DateFormatter('%b %d')  # "Jan 01"
                ax.xaxis.set_major_formatter(date_formatter)
                plt.xticks(rotation=30, ha='right', fontsize=10)
            
            plt.yticks(fontsize=10)
            
            # Add subtle background color
            ax.set_facecolor('#2F3136')
            
            # Adjust layout with more space for labels
            plt.tight_layout()
            
            # Save plot with higher quality
            buf = io.BytesIO()
            plt.savefig(buf, format='png', facecolor='#2F3136', 
                       bbox_inches='tight', dpi=300, 
                       edgecolor='none', pad_inches=0.2)
            buf.seek(0)
            plt.close()

            # Create embed with enhanced formatting
            title = "📊 Tryout Statistics Overview"
            if user:
                title += f" for {user.name}"
            
            embed = discord.Embed(
                title=title,
                description=(
                    f"Showing data from <t:{start_unix}:D> to <t:{end_unix}:D>\n"
                    f"Time period: `{days} days`"
                ),
                color=0x5865F2,
                timestamp=datetime.utcnow()
            )
            
            # Add statistics with emojis and better formatting
            daily_average = total_tryouts / days
            embed.add_field(
                name="📈 Total Tryouts",
                value=f"```{total_tryouts:,}```",
                inline=True
            )
            embed.add_field(
                name="📊 Daily Average",
                value=f"```{int(daily_average) if daily_average >= 1 else daily_average:.1f}```",
                inline=True
            )
            
            if not user:
                embed.add_field(
                    name="👥 Unique Hosts",
                    value=f"```{len(active_hosts):,}```",
                    inline=True
                )

            # Add top groups with improved formatting
            if tryouts_by_group:
                top_groups = sorted(tryouts_by_group.items(), key=lambda x: x[1], reverse=True)[:5]
                top_groups_text = "\n".join(
                    f"#{idx + 1} {name}: {count:,} tryout{'s' if count != 1 else ''}"
                    for idx, (name, count) in enumerate(top_groups)
                )
                embed.add_field(
                    name="🏆 Most Active Groups",
                    value=f"```{top_groups_text}```",
                    inline=False
                )

            # Add activity summary
            peak_day = max(tryouts_by_date.items(), key=lambda x: x[1])
            peak_unix = int(datetime.combine(peak_day[0], datetime.min.time()).timestamp())
            embed.add_field(
                name="📅 Peak Activity",
                value=f"{peak_day[1]} tryout{'s' if peak_day[1] != 1 else ''} on <t:{peak_unix}:D>",
                inline=False
            )

            # Add footer with additional info
            footer_text = "Use /data [days] to change the time range (2-180 days)"
            if not user:
                footer_text += " • Add user parameter to see specific host stats"
            embed.set_footer(text=footer_text)
            
            # Send the embed with the graph
            file = discord.File(buf, filename="tryout_stats.png")
            embed.set_image(url="attachment://tryout_stats.png")
            
            await interaction.followup.send(embed=embed, file=file)

        except Exception as e:
            self.logger.error(f"Error generating tryout statistics: {e}", exc_info=True)
            error_embed = discord.Embed(
                title="❌ Error",
                description=(
                    "An error occurred while generating the statistics.\n"
                    f"```{str(e)}```"
                ),
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)


async def setup(bot) -> None:
    await bot.add_cog(Tryout(bot))