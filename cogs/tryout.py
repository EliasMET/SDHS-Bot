import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta


class GroupDropdown(discord.ui.Select):
    def __init__(self, groups, user, cohost, lock_time, group_settings, channel_id, bot):
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
        self.channel_id = channel_id
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        selected_group_id = self.values[0]
        group_info = self.group_settings[selected_group_id]

        # Calculate lock time as Unix timestamp
        lock_timestamp = datetime.now() + timedelta(minutes=self.lock_time)
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
                description=f"The tryout announcement for **{group_info['event']}** has been sent successfully!",
                color=0x00FF00,
            )
            await interaction.response.edit_message(embed=confirmation_embed, view=None)
        else:
            error_embed = discord.Embed(
                title="Error",
                description="Unable to find the specified channel.",
                color=0xFF0000,
            )
            await interaction.response.edit_message(embed=error_embed, view=None)


class DropdownView(discord.ui.View):
    def __init__(self, groups, user, cohost, lock_time, group_settings, channel_id, bot):
        super().__init__()
        self.add_item(GroupDropdown(groups, user, cohost, lock_time, group_settings, channel_id, bot))


class Tryout(commands.Cog, name="tryout"):
    def __init__(self, bot) -> None:
        self.bot = bot

        # Group-specific settings with customizable events
        self.group_settings = {
            "34995316": {
                "description": "Ever wanted to be the HQ’s Guard or Protect the Academy? Participate in dangerous missions? Well now is your Chance! The Community Emergency Response Team are hosting a Tryout! Come to the Parade Deck to attend a Tryout Now!",
                "link": "https://www.roblox.com/communities/34995316/SRT-Specialized-Response-Team#!/about",
                "event": "CERT Tryout",
            },
            "35254283": {
                "description": "Have you ever wanted to be the primary security for the government of the United States and Protect the American people and our borders? The Specialized Government Police are hosting a Tryout! Come to the Parade Deck to attend a Tryout Now!",
                "link": "https://www.roblox.com/games/135570523432203/Homeland-Security-USA",
                "event": "SGP Tryout",
            },
            "15662381": {
                "description": "Test",
                "link": "https://example.com",
                "event": "Test Event",
            },
            "5249096": {
                "description": "Test2",
                "link": "https://example2.com",
                "event": "Test Event2",
            },
        }

        # Required roles for the command
        self.required_roles = {
            1311772951300804608,
            1311772959622430822,
            1311772956334100642,
            1312145004679921784,
            1310158383000850452,
        }

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
        bloxlink_api_key = "0c2608bb-be45-480d-9a4e-7b34f2fa3b85"  # Replace with your actual Bloxlink API key
        guild_id = 1287288514186182686  # Replace with your guild ID
        channel_id = 1288192250572177449  # Replace with your desired channel ID

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

        async with aiohttp.ClientSession() as session:
            try:
                # Fetch Roblox User ID from Bloxlink
                user_id = interaction.user.id
                bloxlink_url = f"https://api.blox.link/v4/public/guilds/{guild_id}/discord-to-roblox/{user_id}"
                headers = {"Authorization": bloxlink_api_key}

                async with session.get(bloxlink_url, headers=headers) as bloxlink_response:
                    bloxlink_data = await bloxlink_response.json()

                if bloxlink_response.status != 200 or "robloxID" not in bloxlink_data:
                    embed = discord.Embed(
                        title="Error",
                        description="Failed to fetch Roblox User ID. Ensure Bloxlink is configured correctly.",
                        color=0xFF0000,
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

                roblox_user_id = bloxlink_data["robloxID"]

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
                    await interaction.response.send_message(embed=embed, ephemeral=True)
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
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

                # If multiple groups, show a dropdown for selection
                embed = discord.Embed(
                    title="Select Group",
                    description="You are in multiple groups. Please select the group for this tryout.",
                    color=0x00FF00,
                )
                view = DropdownView(matching_groups, interaction.user, cohost, lock_time, self.group_settings, channel_id, self.bot)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

            except Exception as e:
                error_embed = discord.Embed(
                    title="Unexpected Error",
                    description=f"An unexpected error occurred: {str(e)}",
                    color=0xFF0000,
                )
                await interaction.response.send_message(embed=error_embed, ephemeral=True)


# Setup the cog
async def setup(bot) -> None:
    await bot.add_cog(Tryout(bot))
