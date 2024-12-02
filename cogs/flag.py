# cogs/flag_assign.py

import discord
from discord import app_commands
from discord.ext import commands
import logging

class FlagAssign(commands.Cog, name="flag_assign"):
    """
    Cog for the /flag command which assigns the Flag role to a specified user
    and monitors nickname changes to ensure the flag indicator remains.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.role_id = 1313192409076863018  # The ID of the Flag role
        self.flag_indicator = "[Flag] "  # The prefix to add to nicknames
        self.logger = logging.getLogger('discord')  # Assumes you have set up logging

    @app_commands.command(
        name="flag",
        description="Assign the Flag role to a specified user."
    )
    @app_commands.describe(
        member="The user to assign the Flag role to."
    )
    @app_commands.guild_only
    async def flag(self, interaction: discord.Interaction, member: discord.Member) -> None:
        """
        Assigns the Flag role to the specified member.
        """
        # Permission check: Ensure the invoking user has Manage Roles permission
        if not interaction.user.guild_permissions.manage_roles:
            embed = discord.Embed(
                title="Permission Denied",
                description="You don't have permission to use this command.",
                color=0xFF0000,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.logger.warning(f"User {interaction.user} attempted to use /flag without permissions in guild ID {interaction.guild.id}.")
            return

        try:
            guild = interaction.guild
            if guild is None:
                raise ValueError("This command can only be used within a guild.")

            role = guild.get_role(self.role_id)
            if role is None:
                embed = discord.Embed(
                    title="Role Not Found",
                    description=f"Unable to find the role with ID `{self.role_id}`. Please contact an administrator.",
                    color=0xFF0000,
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                self.logger.error(f"Role with ID {self.role_id} not found in guild ID {guild.id}.")
                return

            # Check if the bot has permission to manage roles and assign the specified role
            bot_member = guild.me
            if not guild.me.guild_permissions.manage_roles:
                embed = discord.Embed(
                    title="Permission Error",
                    description="I don't have permission to manage roles. Please check my permissions.",
                    color=0xFF0000,
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                self.logger.error(f"Bot lacks Manage Roles permission in guild ID {guild.id}.")
                return

            # Ensure the bot's top role is higher than the role to assign
            if role >= bot_member.top_role:
                embed = discord.Embed(
                    title="Role Hierarchy Error",
                    description="I cannot assign this role because it is higher than my highest role.",
                    color=0xFF0000,
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                self.logger.error(f"Cannot assign role '{role.name}' to {member} in guild ID {guild.id} due to role hierarchy.")
                return

            # Check if the member already has the role
            if role in member.roles:
                embed = discord.Embed(
                    title="Already Flagged",
                    description=f"**{member.display_name}** already has the Flag role.",
                    color=0xFFFF00,
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                self.logger.info(f"User {member} already has the Flag role in guild ID {guild.id}.")
                return

            # Assign the role to the member
            await member.add_roles(role, reason=f"Flag command invoked by {interaction.user}.")

            # Update the member's nickname to include the flag indicator
            await self.ensure_flag_in_nickname(member)

            # Confirmation embed
            embed = discord.Embed(
                title="Role Assigned",
                description=f"Successfully assigned the **{role.name}** role to **{member.display_name}**.",
                color=0x00FF00,
            )
            await interaction.response.send_message(embed=embed, ephemeral=False)  # Visible to all
            self.logger.info(f"Assigned role '{role.name}' to user {member} by {interaction.user} in guild ID {guild.id}.")

        except discord.Forbidden:
            # Bot lacks permissions to assign roles or change nicknames
            embed = discord.Embed(
                title="Permission Error",
                description="I don't have permission to assign roles or manage nicknames. Please check my permissions and role hierarchy.",
                color=0xFF0000,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.logger.error(f"Permission error: Cannot assign role ID {self.role_id} or manage nicknames in guild ID {guild.id}.")

        except Exception as e:
            # Handle unexpected errors
            self.logger.error(f"Error in /flag command: {e}")
            embed = discord.Embed(
                title="Unexpected Error",
                description="An unexpected error occurred while assigning the role.",
                color=0xFF0000,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """
        Listens for member updates and ensures that users with the Flag role have the flag indicator in their nickname.
        """
        try:
            role = after.guild.get_role(self.role_id)
            if role is None:
                self.logger.error(f"Role with ID {self.role_id} not found in guild ID {after.guild.id}.")
                return

            # Check if the member has the Flag role
            if role not in after.roles:
                return  # No action needed

            # Check if the nickname has changed
            if before.nick == after.nick:
                return  # No nickname change, no action needed

            # Determine the desired nickname
            desired_prefix = self.flag_indicator
            current_nick = after.nick if after.nick else after.name

            if not current_nick.startswith(desired_prefix):
                # Remove any existing flag indicator to prevent duplicates
                new_nick = current_nick
                if self.flag_indicator.strip() in current_nick:
                    new_nick = current_nick.replace(self.flag_indicator.strip(), "").strip()
                # Add the flag indicator
                new_nick = f"{desired_prefix}{new_nick}"
                # Ensure the nickname length does not exceed Discord's limit (32 characters)
                if len(new_nick) > 32:
                    # Truncate the nickname appropriately
                    allowed_length = 32 - len(desired_prefix)
                    new_nick = f"{desired_prefix}{new_nick[:allowed_length]}"
                # Update the nickname
                await after.edit(nick=new_nick, reason="Ensuring Flag indicator in nickname.")
                self.logger.info(f"Updated nickname for {after} to include the Flag indicator.")

        except discord.Forbidden:
            self.logger.error(f"Permission error: Cannot edit nickname for user {after}.")
        except Exception as e:
            self.logger.error(f"Error in on_member_update for user {after}: {e}")

    async def ensure_flag_in_nickname(self, member: discord.Member) -> None:
        """
        Ensures that the member's nickname includes the flag indicator.
        """
        try:
            desired_prefix = self.flag_indicator
            current_nick = member.nick if member.nick else member.name

            if not current_nick.startswith(desired_prefix):
                # Remove any existing flag indicator to prevent duplicates
                new_nick = current_nick
                if self.flag_indicator.strip() in current_nick:
                    new_nick = current_nick.replace(self.flag_indicator.strip(), "").strip()
                # Add the flag indicator
                new_nick = f"{desired_prefix}{new_nick}"
                # Ensure the nickname length does not exceed Discord's limit (32 characters)
                if len(new_nick) > 32:
                    # Truncate the nickname appropriately
                    allowed_length = 32 - len(desired_prefix)
                    new_nick = f"{desired_prefix}{new_nick[:allowed_length]}"
                # Update the nickname
                await member.edit(nick=new_nick, reason="Ensuring Flag indicator in nickname.")
                self.logger.info(f"Updated nickname for {member} to include the Flag indicator.")
        except discord.Forbidden:
            self.logger.error(f"Permission error: Cannot edit nickname for user {member}.")
        except Exception as e:
            self.logger.error(f"Error in ensure_flag_in_nickname for user {member}: {e}")

async def setup(bot: commands.Bot) -> None:
    """
    Asynchronous setup function to add the cog to the bot.
    """
    await bot.add_cog(FlagAssign(bot))