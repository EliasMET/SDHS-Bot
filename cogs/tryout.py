import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta
import logging
import os

class PaginatedDropdownView(discord.ui.View):
    def __init__(self, groups, user, cohost, lock_time, group_settings, channel_id, bot, roblox_user_id, settings_cog, per_page=25):
        super().__init__(timeout=180)  # Set a timeout for the view
        self.groups = list(groups.items())
        self.user = user
        self.cohost = cohost
        self.lock_time = lock_time
        self.group_settings = group_settings
        self.channel_id = channel_id
        self.bot = bot
        self.settings_cog = settings_cog
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = (len(self.groups) - 1) // per_page + 1
        self.roblox_user_id = roblox_user_id

        # Initialize Select menu
        self.select = discord.ui.Select(
            placeholder="Select a group for the tryout",
            min_values=1,
            max_values=1,
            options=self.get_options()
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

        # Add navigation buttons if necessary
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

        selected_group_id = self.select.values[0]
        group_info = self.group_settings[selected_group_id]

        # Calculate lock time as Unix timestamp using discord.utils.utcnow()
        lock_timestamp = discord.utils.utcnow() + timedelta(minutes=self.lock_time)
        lock_unix = int(lock_timestamp.timestamp())
        lock_time_formatted = f"<t:{lock_unix}:R>"

        cohost_mention = self.cohost.mention if self.cohost else "N/A"

        # Fetch Ping Roles
        ping_roles = await self.bot.database.get_ping_roles(self.bot.guild_id)
        if ping_roles:
            ping_role_mentions = [f"<@&{role_id}>" for role_id in ping_roles]
            ping_roles_display = ", ".join(ping_role_mentions)
            ping_roles_text = " ".join(ping_role_mentions)
        else:
            ping_roles_display = "No roles set."
            ping_roles_text = ""

        # Build the plain text message for the tryout announcement with Roblox profile link
        tryout_message = (
            f"{ping_roles_text}\n"  # Ping the roles
            f"**[HOST]** {self.user.mention}\n\n"
            f"**[CO-HOST]** {cohost_mention}\n\n"
            f"**[EVENT]** {group_info['event_name']}\n\n"
            f"**[DESCRIPTION]** {group_info['description']}\n\n"
            f"**[LINK]** https://www.roblox.com/users/{self.roblox_user_id}/profile\n\n"
            f"**[LOCKS]** {lock_time_formatted}\n\n"
            f"**[PINGS]** {ping_roles_display}\n\n"  # Added PINGS section
            f"**[REQUIREMENTS]**\n\n"
            f"• Account age of 100+ Days\n\n"
            f"• No Safechat\n\n"
            f"• Disciplined\n\n"
            f"• Mature\n\n"
            f"• Professional at all times\n\n"
            f"• Agent and above"
        )

        # Send the message to the tryout channel
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            await channel.send(tryout_message)
            confirmation_embed = discord.Embed(
                title="Success",
                description=f"The tryout announcement for **{group_info['event_name']}** has been sent successfully!",
                color=0x00FF00,
            )
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=confirmation_embed, view=None)
            self.settings_cog.bot.logger.info(f"Tryout announcement for '{group_info['event_name']}' sent by {self.user} in guild ID {self.bot.guild_id}.")
        else:
            error_embed = discord.Embed(
                title="Error",
                description="Unable to find the specified channel.",
                color=0xFF0000,
            )
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=error_embed, view=None)
            self.settings_cog.bot.logger.error(f"Channel ID {self.channel_id} not found in guild ID {self.bot.guild_id}.")

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
        self.bot.guild_id = None  # To store the guild ID for easy access

    async def cog_load(self):
        """
        Initializes the database manager.
        """
        self.db = self.bot.database
        if not self.db:
            self.bot.logger.error("DatabaseManager is not initialized in the bot.")
            raise ValueError("DatabaseManager is not initialized in the bot.")
        self.bot.logger.info("Tryout Cog loaded successfully.")

    async def fetch_all_roblox_groups(self, session, roblox_url):
        all_groups = []
        cursor = None
        while True:
            url = roblox_url
            if cursor:
                url += f"?cursor={cursor}"
            async with session.get(url) as response:
                if response.status != 200:
                    self.bot.logger.error(f"Roblox API returned status {response.status}")
                    break
                data = await response.json()
                all_groups.extend(data.get("data", []))
                cursor = data.get("nextPageCursor")
                if not cursor:
                    break
        return all_groups

    @app_commands.command(
        name="tryout",
        description="Announce a tryout with configurable options.",
    )
    @app_commands.describe(
        cohost="Mention the co-host for the event.",
        lock_time="Set the lock time in minutes.",
    )
    async def tryout(
        self,
        interaction: discord.Interaction,
        cohost: discord.Member = None,
        lock_time: int = 10,
    ) -> None:
        bloxlink_api_key = os.getenv("BLOXLINK_TOKEN")
        guild_id = interaction.guild.id
        self.bot.guild_id = guild_id  # Store guild ID for easy access in views

        # Fetch required roles from the database
        required_roles = await self.db.get_tryout_required_roles(interaction.guild.id)
        if not required_roles:
            embed = discord.Embed(
                title="Configuration Error",
                description="No required roles are configured for tryouts. Please contact an administrator.",
                color=0xFF0000,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.bot.logger.warning(f"Tryout command used without required roles in guild ID {guild_id}.")
            return

        # Check if the user has any of the required roles
        user_roles = {role.id for role in interaction.user.roles}
        if not set(required_roles).intersection(user_roles):
            embed = discord.Embed(
                title="Permission Denied",
                description="You do not have the required roles to use this command.",
                color=0xFF0000,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.bot.logger.warning(f"User {interaction.user} lacks required roles for tryout in guild ID {guild_id}.")
            return

        await interaction.response.defer(ephemeral=True)

        # Fetch tryout channel ID from the database
        channel_id = await self.db.get_tryout_channel_id(interaction.guild.id)
        if not channel_id:
            embed = discord.Embed(
                title="Configuration Error",
                description="Tryout channel is not configured. Please contact an administrator.",
                color=0xFF0000,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.warning(f"Tryout channel not configured in guild ID {guild_id}.")
            return

        async with aiohttp.ClientSession() as session:
            try:
                # Fetch Roblox User ID from Bloxlink
                user_id = interaction.user.id
                bloxlink_url = f"https://api.blox.link/v4/public/guilds/{guild_id}/discord-to-roblox/{user_id}"
                headers = {"Authorization": bloxlink_api_key}

                async with session.get(bloxlink_url, headers=headers) as bloxlink_response:
                    bloxlink_data = await bloxlink_response.json()

                if bloxlink_response.status != 200 or not bloxlink_data.get('robloxID'):
                    embed = discord.Embed(
                        title="Error",
                        description="Failed to fetch Roblox User ID. Ensure Bloxlink is configured correctly.",
                        color=0xFF0000,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    self.bot.logger.error(f"Bloxlink API error for user ID {user_id} in guild ID {guild_id}.")
                    return

                roblox_user_id = bloxlink_data["robloxID"]

                # Fetch all Roblox Group Roles with pagination
                roblox_url = f"https://groups.roblox.com/v1/users/{roblox_user_id}/groups/roles"
                all_roblox_groups = await self.fetch_all_roblox_groups(session, roblox_url)

                if not all_roblox_groups:
                    embed = discord.Embed(
                        title="Error",
                        description="You are not in any Roblox groups.",
                        color=0xFF0000,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    self.bot.logger.info(f"User {interaction.user} is not in any Roblox groups.")
                    return

                # Fetch group settings from the database
                tryout_groups = await self.db.get_tryout_groups(interaction.guild.id)
                if not tryout_groups:
                    embed = discord.Embed(
                        title="Configuration Error",
                        description="No tryout groups are configured. Please contact an administrator.",
                        color=0xFF0000,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    self.bot.logger.warning(f"No tryout groups configured in guild ID {guild_id}.")
                    return

                # Convert tryout_groups to a dictionary
                group_settings = {
                    str(group[0]): {
                        'description': group[1],
                        'link': group[2],
                        'event_name': group[3]
                    } for group in tryout_groups
                }

                # Collect all matching groups
                matching_groups = {
                    str(group["group"]["id"]): group_settings[str(group["group"]["id"])]
                    for group in all_roblox_groups
                    if str(group["group"]["id"]) in group_settings
                }

                if not matching_groups:
                    embed = discord.Embed(
                        title="Error",
                        description="No matching group found for this command.",
                        color=0xFF0000,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    self.bot.logger.info(f"No matching Roblox groups found for user ID {roblox_user_id} in guild ID {guild_id}.")
                    return

                # If only one matching group, proceed directly
                if len(matching_groups) == 1:
                    selected_group_id = next(iter(matching_groups.keys()))
                    group_info = group_settings[selected_group_id]

                    # Calculate lock time as Unix timestamp using discord.utils.utcnow()
                    lock_timestamp = discord.utils.utcnow() + timedelta(minutes=lock_time)
                    lock_unix = int(lock_timestamp.timestamp())
                    lock_time_formatted = f"<t:{lock_unix}:R>"

                    cohost_mention = cohost.mention if cohost else "N/A"

                    # Fetch Ping Roles
                    ping_roles = await self.db.get_ping_roles(interaction.guild.id)
                    if ping_roles:
                        ping_role_mentions = [f"<@&{role_id}>" for role_id in ping_roles]
                        ping_roles_display = ", ".join(ping_role_mentions)
                        ping_roles_text = " ".join(ping_role_mentions)
                    else:
                        ping_roles_display = "No roles set."
                        ping_roles_text = ""

                    # Build the plain text message for the tryout announcement with Roblox profile link
                    tryout_message = (
                        f"{ping_roles_text}\n"  # Ping the roles
                        f"**[HOST]** {interaction.user.mention}\n\n"
                        f"**[CO-HOST]** {cohost_mention}\n\n"
                        f"**[EVENT]** {group_info['event_name']}\n\n"
                        f"**[DESCRIPTION]** {group_info['description']}\n\n"
                        f"**[LINK]** https://www.roblox.com/users/{roblox_user_id}/profile\n\n"
                        f"**[LOCKS]** {lock_time_formatted}\n\n"
                        f"**[PINGS]** {ping_roles_display}\n\n"  # Added PINGS section
                        f"**[REQUIREMENTS]**\n\n"
                        f"• Account age of 100+ Days\n\n"
                        f"• No Safechat\n\n"
                        f"• Disciplined\n\n"
                        f"• Mature\n\n"
                        f"• Professional at all times\n\n"
                        f"• Agent and above"
                    )

                    # Send the message to the tryout channel
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        await channel.send(tryout_message)
                        confirmation_embed = discord.Embed(
                            title="Success",
                            description=f"The tryout announcement for **{group_info['event_name']}** has been sent successfully!",
                            color=0x00FF00,
                        )
                        await interaction.followup.send(embed=confirmation_embed, ephemeral=True)
                        self.bot.logger.info(f"Tryout announcement for '{group_info['event_name']}' sent by {interaction.user} in guild ID {guild_id}.")
                    else:
                        error_embed = discord.Embed(
                            title="Error",
                            description="Unable to find the specified channel.",
                            color=0xFF0000,
                        )
                        await interaction.followup.send(embed=error_embed, ephemeral=True)
                        self.bot.logger.error(f"Channel ID {channel_id} not found in guild ID {guild_id}.")
                else:
                    # If multiple groups, show a paginated dropdown for selection
                    embed = discord.Embed(
                        title="Select Group",
                        description="Please select the group for this tryout.",
                        color=0x00FF00,
                    )
                    view = PaginatedDropdownView(
                        matching_groups,
                        interaction.user,
                        cohost,
                        lock_time,
                        group_settings,
                        channel_id,
                        self.bot,
                        roblox_user_id,
                        settings_cog=self  # Pass the cog instance
                    )
                    view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                    self.bot.logger.info(f"Paginated selection for tryout groups sent to {interaction.user} in guild ID {guild_id}.")

            except Exception as e:
                self.bot.logger.error(f"Error in tryout command: {e}")
                error_embed = discord.Embed(
                    title="Unexpected Error",
                    description="An unexpected error occurred.",
                    color=0xFF0000,
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)

# Setup function to add the cog (Asynchronous)
async def setup(bot) -> None:
    await bot.add_cog(Tryout(bot))
