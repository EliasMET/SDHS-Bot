import os
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class GroupDropdown(discord.ui.Select):
    def __init__(self, groups, user, cohost, lock_time, group_settings, announcement_channel_id, bot, logging_channel_id, logging_guild_id):
        options = [
            discord.SelectOption(label=group['event'], description=group['description'][:50], value=str(group_id))
            for group_id, group in groups.items()
        ]
        super().__init__(placeholder="Select a group for the tryout", options=options)
        self.groups = groups
        self.user = user
        self.cohost = cohost
        self.lock_time = lock_time
        self.group_settings = group_settings
        self.announcement_channel_id = announcement_channel_id
        self.bot = bot
        self.logging_channel_id = logging_channel_id
        self.logging_guild_id = logging_guild_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)  # Defer the interaction

        selected_group_id = self.values[0]
        group_info = self.group_settings[selected_group_id]

        # Calculate lock time as Unix timestamp
        lock_timestamp = datetime.utcnow() + timedelta(minutes=self.lock_time)
        lock_unix = int(lock_timestamp.timestamp())
        lock_time_formatted = f"<t:{lock_unix}:R>"

        cohost_mention = self.cohost.mention if self.cohost else "N/A"

        # Build the plain text message for the tryout announcement
        tryout_message = (
            f"**[HOST]** {self.user.mention}\n\n"
            f"**[CO-HOST]** {cohost_mention}\n\n"
            f"**[EVENT]** {group_info['event']}\n\n"
            f"**[DESCRIPTION]** {group_info['description']}\n\n"
            f"**[LINK]** {group_info['link']}\n\n"
            f"**[LOCKS]** {lock_time_formatted}\n\n"
            f"**[REQUIREMENTS]**\n\n"
            f"• Account age of 100+ Days\n"
            f"• No Safechat\n"
            f"• Disciplined\n"
            f"• Mature\n"
            f"• Professional at all times\n"
            f"• Agent and above"
        )

        # Send the message to the tryout announcement channel
        announcement_channel = self.bot.get_channel(self.announcement_channel_id)
        if announcement_channel:
            await announcement_channel.send(tryout_message)
            confirmation_embed = discord.Embed(
                title="Success",
                description=f"The tryout announcement for **{group_info['event']}** has been sent successfully!",
                color=0x00FF00,
            )
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=confirmation_embed, view=None)

            # Log the tryout announcement
            logging_guild = self.bot.get_guild(self.logging_guild_id)
            logging_channel = logging_guild.get_channel(self.logging_channel_id) if logging_guild else None
            if logging_channel:
                log_embed = discord.Embed(
                    title="Tryout Announcement Sent",
                    description=(
                        f"**User:** {self.user} (ID: {self.user.id})\n"
                        f"**Event:** {group_info['event']}\n"
                        f"**Channel:** {announcement_channel.mention}\n"
                        f"**Timestamp:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    ),
                    color=0x00FF00,
                )
                await logging_channel.send(embed=log_embed)
        else:
            error_embed = discord.Embed(
                title="Error",
                description="Unable to find the specified announcement channel.",
                color=0xFF0000,
            )
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=error_embed, view=None)

            # Log the error
            logging_guild = self.bot.get_guild(self.logging_guild_id)
            logging_channel = logging_guild.get_channel(self.logging_channel_id) if logging_guild else None
            if logging_channel:
                error_log_embed = discord.Embed(
                    title="Error Sending Tryout Announcement",
                    description=(
                        f"**User:** {self.user} (ID: {self.user.id})\n"
                        f"**Error:** Unable to find the specified announcement channel.\n"
                        f"**Timestamp:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    ),
                    color=0xFF0000,
                )
                await logging_channel.send(embed=error_log_embed)


class DropdownView(discord.ui.View):
    def __init__(self, groups, user, cohost, lock_time, group_settings, announcement_channel_id, bot, logging_channel_id, logging_guild_id):
        super().__init__()
        self.add_item(
            GroupDropdown(
                groups,
                user,
                cohost,
                lock_time,
                group_settings,
                announcement_channel_id,
                bot,
                logging_channel_id,
                logging_guild_id,
            )
        )


class Tryout(commands.Cog, name="tryout"):
    def __init__(self, bot) -> None:
        self.bot = bot

        # Group-specific settings with customizable events
        self.group_settings = {
            "34995316": {
                "description": "Ever wanted to be the HQ’s Guard or Protect the Academy? Participate in dangerous missions? Well now is your chance! The Community Emergency Response Team is hosting a Tryout! Come to the Parade Deck to attend a Tryout now!",
                "link": "https://www.roblox.com/groups/34995316/CERT-Community-Emergency-Response-Team#!/about",
                "event": "CERT Tryout",
            },
            "35254283": {
                "description": "Have you ever wanted to be the primary security for the government of the United States and protect the American people and our borders? The Specialized Government Police are hosting a Tryout! Come to the Parade Deck to attend a Tryout now!",
                "link": "https://www.roblox.com/groups/35254283/SGP-Specialized-Government-Police#!/about",
                "event": "SGP Tryout",
            },
            # Add more group settings as needed
        }

        # Required role IDs for the command (replace with your actual role IDs)
        self.required_roles = {
            1311772951300804608,  # Example Role ID 1
            1311772959622430822,  # Example Role ID 2
            1311772956334100642,  # Example Role ID 3
            1312145004679921784,  # Example Role ID 4
            1310158383000850452,  # Example Role ID 5
        }

        # Logging channel and guild IDs
        self.logging_channel_id = 1199751741114159104  # Replace with your logging channel ID
        self.logging_guild_id = 1087452557426819203    # Replace with your logging server (guild) ID

        # Announcement channel ID (where the tryout announcements will be sent)
        self.announcement_channel_id = 1288192250572177449  # Replace with your announcement channel ID

        # Bloxlink guild ID (the guild ID used by Bloxlink)
        self.bloxlink_guild_id = 1287288514186182686  # Replace with your Bloxlink guild ID

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
        # Load the Bloxlink API key from the environment variable
        bloxlink_api_key = os.getenv("BLOXLINK_TOKEN")
        if not bloxlink_api_key:
            embed = discord.Embed(
                title="Configuration Error",
                description="Bloxlink API key is not set in the environment variables.",
                color=0xFF0000,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Check if the user has the required roles
        user_roles = {role.id for role in interaction.user.roles}
        if not self.required_roles.intersection(user_roles):
            embed = discord.Embed(
                title="Permission Denied",
                description="You do not have the required roles to use this command.",
                color=0xFF0000,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)  # Defer the interaction and make it ephemeral

        # Get the logging channel
        logging_guild = self.bot.get_guild(self.logging_guild_id)
        logging_channel = logging_guild.get_channel(self.logging_channel_id) if logging_guild else None
        if logging_channel:
            command_log_embed = discord.Embed(
                title="Command Used: /tryout",
                description=(
                    f"**User:** {interaction.user} (ID: {interaction.user.id})\n"
                    f"**Co-host:** {cohost}\n"
                    f"**Lock Time:** {lock_time} minutes\n"
                    f"**Timestamp:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                ),
                color=0x0000FF,
            )
            await logging_channel.send(embed=command_log_embed)

        async with aiohttp.ClientSession() as session:
            try:
                # Fetch Roblox User ID from Bloxlink
                user_id = interaction.user.id
                bloxlink_url = f"https://api.blox.link/v4/public/guilds/{self.bloxlink_guild_id}/discord-to-roblox/{user_id}"
                headers = {"Authorization": bloxlink_api_key}

                async with session.get(bloxlink_url, headers=headers) as bloxlink_response:
                    bloxlink_data = await bloxlink_response.json()

                if bloxlink_response.status != 200 or "user" not in bloxlink_data or "robloxID" not in bloxlink_data["user"]:
                    embed = discord.Embed(
                        title="Error",
                        description="Failed to fetch Roblox User ID. Ensure Bloxlink is configured correctly.",
                        color=0xFF0000,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)

                    # Log the error
                    if logging_channel:
                        error_log_embed = discord.Embed(
                            title="Error in /tryout Command",
                            description=(
                                f"**User:** {interaction.user} (ID: {interaction.user.id})\n"
                                f"**Error:** Failed to fetch Roblox User ID.\n"
                                f"**Response:** {bloxlink_data}\n"
                                f"**Timestamp:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                            ),
                            color=0xFF0000,
                        )
                        await logging_channel.send(embed=error_log_embed)
                    return

                roblox_user_id = bloxlink_data["user"]["robloxID"]

                # Fetch Roblox Group Roles
                roblox_url = f"https://groups.roblox.com/v1/users/{roblox_user_id}/groups/roles"
                async with session.get(roblox_url) as roblox_response:
                    roblox_data = await roblox_response.json()

                if roblox_response.status != 200 or "data" not in roblox_data or not roblox_data["data"]:
                    embed = discord.Embed(
                        title="Error",
                        description="You are not in any Roblox groups.",
                        color=0xFF0000,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)

                    # Log the error
                    if logging_channel:
                        error_log_embed = discord.Embed(
                            title="Error in /tryout Command",
                            description=(
                                f"**User:** {interaction.user} (ID: {interaction.user.id})\n"
                                f"**Error:** User not in any Roblox groups.\n"
                                f"**Timestamp:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                            ),
                            color=0xFF0000,
                        )
                        await logging_channel.send(embed=error_log_embed)
                    return

                # Collect all matching groups
                matching_groups = {
                    str(group["group"]["id"]): self.group_settings[str(group["group"]["id"])]
                    for group in roblox_data["data"]
                    if str(group["group"]["id"]) in self.group_settings
                }

                if not matching_groups:
                    embed = discord.Embed(
                        title="Error",
                        description="No matching group found for this command.",
                        color=0xFF0000,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)

                    # Log the error
                    if logging_channel:
                        error_log_embed = discord.Embed(
                            title="Error in /tryout Command",
                            description=(
                                f"**User:** {interaction.user} (ID: {interaction.user.id})\n"
                                f"**Error:** No matching group found.\n"
                                f"**Timestamp:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                            ),
                            color=0xFF0000,
                        )
                        await logging_channel.send(embed=error_log_embed)
                    return

                # If multiple groups, show a dropdown for selection
                embed = discord.Embed(
                    title="Select Group",
                    description="You are in multiple groups. Please select the group for this tryout.",
                    color=0x00FF00,
                )
                view = DropdownView(
                    matching_groups,
                    interaction.user,
                    cohost,
                    lock_time,
                    self.group_settings,
                    self.announcement_channel_id,
                    self.bot,
                    self.logging_channel_id,
                    self.logging_guild_id,
                )
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)

            except Exception as e:
                error_embed = discord.Embed(
                    title="Unexpected Error",
                    description=f"An unexpected error occurred: {str(e)}",
                    color=0xFF0000,
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)

                # Log the error
                if logging_channel:
                    error_log_embed = discord.Embed(
                        title="Exception in /tryout Command",
                        description=(
                            f"**User:** {interaction.user} (ID: {interaction.user.id})\n"
                            f"**Error:** {str(e)}\n"
                            f"**Timestamp:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                        ),
                        color=0xFF0000,
                    )
                    await logging_channel.send(embed=error_log_embed)


# Setup the cog
async def setup(bot) -> None:
    await bot.add_cog(Tryout(bot))
