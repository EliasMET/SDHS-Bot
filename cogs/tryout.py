import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta
import logging
import os

logger = logging.getLogger(__name__)

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
        guild_id = self.bot.guild_id
        selected_group_id = self.select.values[0]
        group_info = self.group_settings[selected_group_id]

        lock_timestamp = discord.utils.utcnow() + timedelta(minutes=self.lock_time)
        lock_unix = int(lock_timestamp.timestamp())
        lock_time_formatted = f"<t:{lock_unix}:R>"

        link = f"https://www.roblox.com/users/{self.roblox_user_id}/profile"
        reqs = group_info["requirements"] if group_info.get("requirements") else []
        req_text = "\n".join(reqs) if reqs else "None"

        # Fetch ping roles
        ping_roles = await self.bot.database.get_ping_roles(interaction.guild.id)
        pings = " ".join(f"<@&{rid}>" for rid in ping_roles) if ping_roles else ""

        # Generate a voice channel invite link if the user is in a voice channel
        voice_channel = interaction.user.voice.channel if interaction.user.voice else None
        vc_display = ""
        if voice_channel:
            invite = await voice_channel.create_invite(max_age=43200)  # 12 hours in seconds
            vc_display = invite.url

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
                await channel.send(tryout_message)
                confirmation_embed = discord.Embed(
                    title="Success",
                    description=f"The tryout announcement for **{group_info['event_name']}** has been sent!",
                    color=0x00FF00,
                )
                await interaction.followup.edit_message(
                    message_id=interaction.message.id, 
                    embed=confirmation_embed, 
                    view=None
                )
                logger.info(
                    f"Tryout announcement for '{group_info['event_name']}' sent by {self.user} (ID: {self.user.id}) in guild {guild_id}."
                )
            except Exception as e:
                logger.error(
                    f"Failed to send tryout announcement for '{group_info['event_name']}' by {self.user} (ID: {self.user.id}) "
                    f"to channel {self.channel_id} in guild {guild_id}: {e}",
                    exc_info=True
                )
                error_embed = discord.Embed(
                    title="Error",
                    description="An unexpected error occurred while sending the tryout announcement.",
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
        bloxlink_api_key = os.getenv("BLOXLINK_TOKEN")
        self.bot.guild_id = interaction.guild.id
        guild_id = self.bot.guild_id
        logger.info(
            f"User {interaction.user} (ID: {interaction.user.id}) triggered /tryout in guild {guild_id} "
            f"with lock_time={lock_time}."
        )

        # Check required roles
        required_roles = await self.db.get_tryout_required_roles(interaction.guild.id)
        user_roles = {role.id for role in interaction.user.roles}
        if not set(required_roles).intersection(user_roles):
            logger.warning(
                f"User {interaction.user} (ID: {interaction.user.id}) does not have required roles for /tryout in guild {guild_id}."
            )
            embed = discord.Embed(title="Permission Denied", description="You lack the required roles.", color=0xFF0000)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Check if user is in allowed voice channel
        allowed_vcs = await self.db.get_tryout_allowed_vcs(interaction.guild.id)
        user_vc = interaction.user.voice.channel if interaction.user.voice else None
        if not user_vc or user_vc.id not in allowed_vcs:
            logger.warning(
                f"User {interaction.user} (ID: {interaction.user.id}) is not in an allowed voice channel for /tryout in guild {guild_id}."
            )
            embed = discord.Embed(
                title="Voice Channel Required",
                description="You must be in one of the allowed voice channels to start a tryout.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Defer response
        await interaction.response.defer(ephemeral=True)

        # Check tryout channel config
        channel_id = await self.db.get_tryout_channel_id(interaction.guild.id)
        if not channel_id:
            logger.error(f"No tryout channel configured for guild {guild_id}.")
            embed = discord.Embed(title="Config Error", description="Tryout channel not set.", color=0xFF0000)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        async with aiohttp.ClientSession() as session:
            try:
                user_id = interaction.user.id
                bloxlink_url = f"https://api.blox.link/v4/public/guilds/{guild_id}/discord-to-roblox/{user_id}"
                headers = {"Authorization": bloxlink_api_key}

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
                    embed = discord.Embed(title="Error", description="No matching group found.", color=0xFF0000)
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

                logger.info(
                    f"Found {len(matching_groups)} matching groups for /tryout triggered by {interaction.user} (ID: {interaction.user.id}) in guild {guild_id}."
                )

                # Fetch ping roles
                ping_roles = await self.db.get_ping_roles(interaction.guild.id)
                pings = " ".join(f"<@&{rid}>" for rid in ping_roles) if ping_roles else ""

                # Generate a voice channel invite for the user's current VC
                vc_display = ""
                if user_vc:
                    invite = await user_vc.create_invite(max_age=43200)  # 12 hours in seconds
                    vc_display = invite.url

                if len(matching_groups) == 1:
                    selected_group_id = next(iter(matching_groups.keys()))
                    group_info = matching_groups[selected_group_id]

                    lock_timestamp = discord.utils.utcnow() + timedelta(minutes=lock_time)
                    lock_unix = int(lock_timestamp.timestamp())
                    lock_time_formatted = f"<t:{lock_unix}:R>"
                    link = f"https://www.roblox.com/users/{roblox_user_id}/profile"
                    reqs = group_info["requirements"] if group_info.get("requirements") else []
                    req_text = "\n".join(reqs) if reqs else "None"

                    # One empty line before [STATUS] and bold event name
                    tryout_message = (
                        f"[DIVISION] **{group_info['event_name']}**\n"
                        f"[HOST] {interaction.user.mention}\n"
                        f"[LOCATION] {link} < JOIN PROFILE\n"
                        f"[INFO] {group_info['description']}\n"
                        f"[REQUIREMENTS]\n"
                        f"{req_text}\n"
                        f"\n"  # Extra newline for empty line before STATUS
                        f"[STATUS] Locking at {lock_time_formatted}\n"
                        f"{pings}\n"
                        f"{vc_display}"
                    )

                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        try:
                            await channel.send(tryout_message)
                            confirmation_embed = discord.Embed(
                                title="Success",
                                description=f"The tryout for **{group_info['event_name']}** has been announced!",
                                color=0x00FF00,
                            )
                            await interaction.followup.send(embed=confirmation_embed, ephemeral=True)
                            logger.info(
                                f"Tryout announced for event '{group_info['event_name']}' by {interaction.user} (ID: {interaction.user.id}) in guild {guild_id}."
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to send tryout announcement for '{group_info['event_name']}' by {interaction.user} (ID: {interaction.user.id}) "
                                f"to channel {channel_id} in guild {guild_id}: {e}",
                                exc_info=True
                            )
                            error_embed = discord.Embed(
                                title="Error",
                                description="An unexpected error occurred while sending the tryout announcement. Please check bot permissions and try again.",
                                color=0xFF0000
                            )
                            await interaction.followup.send(embed=error_embed, ephemeral=True)
                    else:
                        logger.error(
                            f"Configured tryout channel {channel_id} not found in guild {guild_id}. "
                            f"User {interaction.user} (ID: {interaction.user.id}) tried announcing a tryout."
                        )
                        error_embed = discord.Embed(
                            title="Error",
                            description="Configured tryout channel not found. Please contact an administrator.",
                            color=0xFF0000
                        )
                        await interaction.followup.send(embed=error_embed, ephemeral=True)

                else:
                    logger.info(
                        f"Multiple ({len(matching_groups)}) matching tryout groups found for user {interaction.user} (ID: {interaction.user.id}) in guild {guild_id}. Presenting dropdown selection."
                    )
                    embed = discord.Embed(title="Select Group", description="Select the group for this tryout.", color=0x00FF00)
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
                    f"Unexpected error occurred during /tryout command for user {interaction.user} (ID: {interaction.user.id}) in guild {guild_id}: {e}",
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


async def setup(bot) -> None:
    await bot.add_cog(Tryout(bot))