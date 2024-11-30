import discord
from discord.ext import commands
from discord import app_commands
import asyncio

# Assuming DatabaseManager is defined in database.py and handles all required database operations
# from database import DatabaseManager

class Settings(commands.Cog, name="settings"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = None  # Placeholder for the database manager instance
        self.owner_id = None  # Initialize owner_id

    async def cog_load(self):
        """
        This method is called when the cog is loaded.
        It initializes the database manager and caches the bot owner's ID.
        """
        self.db = self.bot.database  # Access DatabaseManager from the bot instance
        if not self.db:
            self.bot.logger.error("DatabaseManager is not initialized in the bot.")
            raise ValueError("DatabaseManager is not initialized in the bot.")
        # Cache the owner_id when the cog is loaded
        try:
            app_info = await self.bot.application_info()
            self.owner_id = app_info.owner.id
            self.bot.logger.debug(f"Cached owner_id: {self.owner_id}")
        except Exception as e:
            self.bot.logger.error(f"Failed to cache owner_id: {e}")
            raise

    async def cog_unload(self):
        """
        This method is called when the cog is unloaded.
        """
        self.bot.logger.debug("Settings cog unloaded.")

    # Define the permission check as a method within the cog
    async def is_admin_or_owner(self, interaction: discord.Interaction) -> bool:
        """
        Checks if the user is either the bot owner or has administrator permissions in the guild.
        """
        user = interaction.user
        if user.id == self.owner_id:
            return True
        if interaction.guild and user.guild_permissions.administrator:
            return True
        return False

    @app_commands.command(name="settings", description="Configure bot settings.")
    @app_commands.describe(category="The category of settings to configure.")
    async def settings_command(self, interaction: discord.Interaction, category: str):
        """
        Main command to configure bot settings based on the specified category.
        """
        # Perform the permission check manually
        if not await self.is_admin_or_owner(interaction):
            embed = discord.Embed(
                title="Missing Permissions",
                description="You need the `Administrator` permission or be the bot owner to use this command.",
                color=0xE02B2B,  # Dark red for errors
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.bot.logger.warning(
                f"User {interaction.user} (ID: {interaction.user.id}) attempted to access settings without sufficient permissions."
            )
            return

        await interaction.response.defer(ephemeral=True)

        category = category.lower()
        if category == "automod":
            server_settings = await self.db.get_server_settings(interaction.guild.id)
            if not server_settings:
                await self.db.initialize_server_settings(interaction.guild.id)
                server_settings = await self.db.get_server_settings(interaction.guild.id)
                self.bot.logger.info(f"Initialized automod settings for guild {interaction.guild.name} (ID: {interaction.guild.id})")
            embed = self.create_automod_settings_embed(server_settings)
            view = AutomodSettingsView(self.db, interaction.guild, settings_cog=self)
            view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            self.bot.logger.info(f"Displayed Automod settings to user {interaction.user} (ID: {interaction.user.id}) in guild {interaction.guild.name} (ID: {interaction.guild.id})")
        elif category == "tryout":
            embed = await self.create_tryout_settings_embed(interaction.guild)
            view = TryoutSettingsView(self.db, interaction.guild, settings_cog=self)
            view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            self.bot.logger.info(f"Displayed Tryout settings to user {interaction.user} (ID: {interaction.user.id}) in guild {interaction.guild.name} (ID: {interaction.guild.id})")
        elif category == "moderation":
            embed = await self.create_moderation_settings_embed(interaction.guild)
            view = ModerationSettingsView(self.db, interaction.guild, settings_cog=self)
            view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            self.bot.logger.info(f"Displayed Moderation settings to user {interaction.user} (ID: {interaction.user.id}) in guild {interaction.guild.name} (ID: {interaction.guild.id})")
        else:
            embed = discord.Embed(
                title="Invalid Category",
                description=f"The category `{category}` is not recognized.",
                color=0xE02B2B,  # Dark red for errors
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.bot.logger.warning(
                f"User {interaction.user} (ID: {interaction.user.id}) provided an invalid category '{category}' in guild {interaction.guild.name} (ID: {interaction.guild.id})."
            )

    @settings_command.autocomplete('category')
    async def settings_autocomplete(self, interaction: discord.Interaction, current: str):
        """
        Autocomplete for the 'category' parameter in the /settings command.
        """
        categories = ["automod", "tryout", "moderation"]
        return [
            app_commands.Choice(name=category.capitalize(), value=category)
            for category in categories if current.lower() in category.lower()
        ]

    def create_automod_settings_embed(self, server_settings):
        """
        Creates an embed for Automod settings.
        """
        automod_status = "✅ Enabled" if server_settings.get('automod_enabled') else "❌ Disabled"
        logging_status = "✅ Enabled" if server_settings.get('automod_logging_enabled') else "❌ Disabled"
        log_channel_id = server_settings.get('automod_log_channel_id')
        log_channel = f"<#{log_channel_id}>" if log_channel_id else "Not Set"

        embed = discord.Embed(
            title="⚙️ Automod Settings",
            color=discord.Color.blue(),
            description="Use the buttons below to configure automod settings."
        )
        embed.add_field(name="Automod Status", value=automod_status, inline=True)
        embed.add_field(name="Logging Status", value=logging_status, inline=True)
        embed.add_field(name="Log Channel", value=log_channel, inline=False)
        embed.set_footer(text="Settings will timeout after 3 minutes of inactivity.")
        return embed

    async def create_tryout_settings_embed(self, guild):
        """
        Creates an embed for Tryout settings.
        """
        # Fetch tryout settings from the database
        tryout_channel_id = await self.db.get_tryout_channel_id(guild.id)
        tryout_channel = f"<#{tryout_channel_id}>" if tryout_channel_id else "Not Set"

        required_roles = await self.db.get_tryout_required_roles(guild.id)
        if required_roles:
            role_mentions = [f"<@&{role_id}>" for role_id in required_roles]
            roles_display = ", ".join(role_mentions)
        else:
            roles_display = "Not Set"

        tryout_groups = await self.db.get_tryout_groups(guild.id)
        if tryout_groups:
            groups_display = "\n".join([f"**{group[3]}** (Group ID: {group[0]})" for group in tryout_groups])
        else:
            groups_display = "No groups configured."

        embed = discord.Embed(
            title="⚙️ Tryout Settings",
            color=discord.Color.blue(),
            description="Use the buttons below to configure tryout settings."
        )
        embed.add_field(name="Tryout Channel", value=tryout_channel, inline=False)
        embed.add_field(name="Required Roles", value=roles_display, inline=False)
        embed.add_field(name="Tryout Groups", value=groups_display, inline=False)
        embed.set_footer(text="Settings will timeout after 3 minutes of inactivity.")
        return embed

    async def create_moderation_settings_embed(self, guild):
        """
        Creates an embed for Moderation settings.
        """
        # Fetch moderation settings from the database
        server_settings = await self.db.get_server_settings(guild.id)
        mod_log_channel_id = server_settings.get('mod_log_channel_id')
        mod_log_channel = f"<#{mod_log_channel_id}>" if mod_log_channel_id else "Not Set"

        allowed_roles = await self.db.get_moderation_allowed_roles(guild.id)
        if allowed_roles:
            role_mentions = [f"<@&{role_id}>" for role_id in allowed_roles]
            roles_display = ", ".join(role_mentions)
        else:
            roles_display = "No roles set."

        embed = discord.Embed(
            title="⚙️ Moderation Settings",
            color=discord.Color.blue(),
            description="Use the buttons below to configure moderation settings."
        )
        embed.add_field(name="Moderation Log Channel", value=mod_log_channel, inline=False)
        embed.add_field(name="Allowed Roles", value=roles_display, inline=False)
        embed.set_footer(text="Settings will timeout after 3 minutes of inactivity.")
        return embed

    @settings_command.error
    async def settings_error(self, interaction: discord.Interaction, error):
        """
        Handles errors for the /settings command.
        """
        embed_color = 0xE02B2B  # Dark red for errors
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="Missing Permissions",
                description="You need the `Administrator` permission or be the bot owner to use this command.",
                color=embed_color,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.bot.logger.warning(
                f"User {interaction.user} (ID: {interaction.user.id}) lacked permissions to execute /settings."
            )
        elif isinstance(error, discord.app_commands.errors.MissingArgument):
            embed = discord.Embed(
                title="Missing Argument",
                description="Please provide a category. Example: `/settings category:automod`",
                color=embed_color
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.bot.logger.warning(
                f"User {interaction.user} (ID: {interaction.user.id}) did not provide a required argument for /settings."
            )
        else:
            self.bot.logger.error(f"Error in /settings command: {error}")
            embed = discord.Embed(
                title="Error",
                description="An unexpected error occurred.",
                color=embed_color,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

# Base Modal for Channel Input
class BaseChannelModal(discord.ui.Modal):
    channel_id = discord.ui.TextInput(
        label="Channel ID",
        placeholder="Enter the ID of the channel",
        required=True,
        max_length=20
    )

    def __init__(self, db, guild, setting_name, update_callback, title="Set Channel"):
        super().__init__(title=title)
        self.db = db
        self.guild = guild
        self.setting_name = setting_name
        self.update_callback = update_callback

    async def validate_channel(self, channel_id_str):
        """
        Validates the provided channel ID.
        """
        if not channel_id_str.isdigit():
            return None, "Please ensure the Channel ID is numeric."
        channel_id = int(channel_id_str)
        channel = self.guild.get_channel(channel_id)
        if not channel:
            return None, "Please ensure the Channel ID is correct and try again."
        return channel, None

    async def on_submit(self, interaction: discord.Interaction):
        """
        Handles the submission of the channel ID.
        """
        channel_id_str = self.channel_id.value.strip()
        channel, error = await self.validate_channel(channel_id_str)
        if error:
            embed = discord.Embed(
                title="Invalid Channel ID",
                description=error,
                color=0xE02B2B,  # Dark red for errors
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            interaction.client.logger.warning(
                f"Invalid channel ID '{channel_id_str}' provided by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
            )
            return

        try:
            # Map setting names to database methods
            setting_methods = {
                'tryout_channel_id': self.db.set_tryout_channel_id,
                'automod_log_channel_id': lambda guild_id, cid: self.db.update_server_setting(guild_id, 'automod_log_channel_id', str(cid)),
                'mod_log_channel_id': self.db.set_mod_log_channel
            }

            if self.setting_name in setting_methods:
                await setting_methods[self.setting_name](self.guild.id, channel.id)
            else:
                await self.db.update_server_setting(self.guild.id, self.setting_name, str(channel.id))

            embed = discord.Embed(
                title="Channel Set",
                description=f"Channel set to {channel.mention}.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            interaction.client.logger.info(
                f"Channel '{channel.name}' (ID: {channel.id}) set for '{self.setting_name}' by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
            )
            await self.update_callback()

        except Exception as e:
            interaction.client.logger.error(f"Error setting channel '{self.setting_name}' in guild {self.guild.id}: {e}")
            embed = discord.Embed(
                title="Error",
                description="Failed to set the channel. Please try again later.",
                color=0xE02B2B,  # Dark red for errors
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

# Base Modal for Role Management
class BaseRoleManagementModal(discord.ui.Modal):
    action = discord.ui.TextInput(
        label="Action",
        placeholder="Enter 'add' or 'remove'",
        required=True,
        max_length=6
    )
    role_ids = discord.ui.TextInput(
        label="Role IDs",
        placeholder="Enter Role IDs separated by spaces",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
    )

    def __init__(self, db, guild, update_callback, add_method, remove_method, success_title):
        super().__init__(title="Manage Roles")
        self.db = db
        self.guild = guild
        self.update_callback = update_callback
        self.add_method = add_method
        self.remove_method = remove_method
        self.success_title = success_title

    async def on_submit(self, interaction: discord.Interaction):
        """
        Handles the submission of role management actions.
        """
        action_input = self.action.value.strip().lower()
        role_ids_str = self.role_ids.value.strip()
        role_id_list = [rid.strip() for rid in role_ids_str.split() if rid.strip()]
        
        if action_input not in ['add', 'remove']:
            embed = discord.Embed(
                title="Invalid Action",
                description="Please enter 'add' or 'remove' as the action.",
                color=0xE02B2B,  # Dark red for errors
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            interaction.client.logger.warning(
                f"Invalid action '{action_input}' provided by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
            )
            return

        if not role_id_list:
            embed = discord.Embed(
                title="No Role IDs Provided",
                description="Please enter at least one Role ID.",
                color=0xE02B2B,  # Dark red for errors
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            interaction.client.logger.warning(
                f"No Role IDs provided by user {interaction.user} (ID: {interaction.user.id}) for action '{action_input}' in guild {self.guild.name} (ID: {self.guild.id})."
            )
            return

        valid_role_ids = []
        invalid_role_ids = []
        for rid in role_id_list:
            if not rid.isdigit():
                invalid_role_ids.append(rid)
                continue
            role = self.guild.get_role(int(rid))
            if role:
                valid_role_ids.append(role.id)
            else:
                invalid_role_ids.append(rid)

        if invalid_role_ids:
            embed = discord.Embed(
                title="Invalid Role IDs",
                description=f"The following Role IDs are invalid or not found: {', '.join(invalid_role_ids)}",
                color=0xE02B2B,  # Dark red for errors
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            interaction.client.logger.warning(
                f"Invalid Role IDs '{invalid_role_ids}' provided by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
            )
            return

        try:
            if action_input == 'add':
                for role_id in valid_role_ids:
                    await self.add_method(self.guild.id, role_id)
                action_done = "added"
            elif action_input == 'remove':
                for role_id in valid_role_ids:
                    await self.remove_method(self.guild.id, role_id)
                action_done = "removed"

            role_mentions = [f"<@&{rid}>" for rid in valid_role_ids]
            roles_display = ", ".join(role_mentions)
            embed = discord.Embed(
                title=self.success_title,
                description=f"Roles successfully {action_done}: {roles_display}",
                color=discord.Color.green()
            )
            interaction.client.logger.info(
                f"Roles {action_done}: {role_mentions} by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            await self.update_callback()

        except Exception as e:
            interaction.client.logger.error(f"Error managing roles in guild {self.guild.id}: {e}")
            embed = discord.Embed(
                title="Error",
                description="Failed to manage roles. Please try again later.",
                color=0xE02B2B,  # Dark red for errors
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

# Modal to manage tryout groups (unique fields, kept as is)
class ManageTryoutGroupsModal(discord.ui.Modal, title="Manage Tryout Groups"):
    action = discord.ui.TextInput(
        label="Action",
        placeholder="Enter 'add', 'edit', or 'delete'",
        required=True,
        max_length=10
    )
    group_id = discord.ui.TextInput(
        label="Group ID",
        placeholder="Enter the Group ID",
        required=True,
        max_length=20
    )
    event_name = discord.ui.TextInput(
        label="Event Name",
        placeholder="Enter the Event Name (for 'add' or 'edit')",
        required=False,
        max_length=100
    )
    description = discord.ui.TextInput(
        label="Description",
        placeholder="Enter the Description (for 'add' or 'edit')",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=2000
    )
    link = discord.ui.TextInput(
        label="Link",
        placeholder="Enter the Link (for 'add' or 'edit')",
        required=False,
        max_length=200
    )

    def __init__(self, db, guild, update_callback):
        super().__init__()
        self.db = db
        self.guild = guild
        self.update_callback = update_callback

    async def on_submit(self, interaction: discord.Interaction):
        """
        Handles the submission for managing tryout groups.
        """
        action = self.action.value.strip().lower()
        group_id = self.group_id.value.strip()

        if action not in ['add', 'edit', 'delete']:
            embed = discord.Embed(
                title="Invalid Action",
                description="Please enter 'add', 'edit', or 'delete' as the action.",
                color=0xE02B2B,  # Dark red for errors
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            interaction.client.logger.warning(
                f"Invalid action '{action}' provided by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
            )
            return

        if not group_id.isdigit():
            embed = discord.Embed(
                title="Invalid Group ID",
                description="Please ensure the Group ID is numeric.",
                color=0xE02B2B,  # Dark red for errors
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            interaction.client.logger.warning(
                f"Invalid Group ID '{group_id}' provided by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
            )
            return

        try:
            if action == 'add':
                # Ensure all fields are provided
                if not self.event_name.value.strip() or not self.description.value.strip() or not self.link.value.strip():
                    embed = discord.Embed(
                        title="Missing Information",
                        description="For adding a group, please provide Event Name, Description, and Link.",
                        color=0xE02B2B,  # Dark red for errors
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    interaction.client.logger.warning(
                        f"Missing information for adding tryout group by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
                    )
                    return
                # Check if group already exists
                existing_group = await self.db.get_tryout_group(self.guild.id, group_id)
                if existing_group:
                    embed = discord.Embed(
                        title="Group Already Exists",
                        description="A group with this ID already exists.",
                        color=0xE02B2B,  # Dark red for errors
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    interaction.client.logger.warning(
                        f"Attempt to add existing tryout group ID '{group_id}' by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
                    )
                    return
                await self.db.add_tryout_group(
                    self.guild.id,
                    group_id,
                    self.description.value.strip(),
                    self.link.value.strip(),
                    self.event_name.value.strip()
                )
                interaction.client.logger.info(
                    f"Added new tryout group: ID {group_id}, Event Name '{self.event_name.value.strip()}' by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
                )
                embed = discord.Embed(
                    title="Group Added",
                    description=f"Group added successfully: **{self.event_name.value.strip()}** (ID: {group_id})",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

            elif action == 'edit':
                # Ensure the group exists
                existing_group = await self.db.get_tryout_group(self.guild.id, group_id)
                if not existing_group:
                    embed = discord.Embed(
                        title="Group Not Found",
                        description="Group not found. Please ensure the Group ID is correct.",
                        color=0xE02B2B,  # Dark red for errors
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    interaction.client.logger.warning(
                        f"Attempt to edit non-existent tryout group ID '{group_id}' by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
                    )
                    return
                # Update only provided fields
                event_name = self.event_name.value.strip() if self.event_name.value.strip() else existing_group[3]
                description = self.description.value.strip() if self.description.value.strip() else existing_group[1]
                link = self.link.value.strip() if self.link.value.strip() else existing_group[2]
                await self.db.update_tryout_group(
                    self.guild.id,
                    group_id,
                    description,
                    link,
                    event_name
                )
                interaction.client.logger.info(
                    f"Updated tryout group: ID {group_id}, Event Name '{event_name}' by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
                )
                embed = discord.Embed(
                    title="Group Updated",
                    description=f"Group updated successfully: **{event_name}** (ID: {group_id})",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

            elif action == 'delete':
                # Ensure the group exists
                existing_group = await self.db.get_tryout_group(self.guild.id, group_id)
                if not existing_group:
                    embed = discord.Embed(
                        title="Group Not Found",
                        description="Group not found. Please ensure the Group ID is correct.",
                        color=0xE02B2B,  # Dark red for errors
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    interaction.client.logger.warning(
                        f"Attempt to delete non-existent tryout group ID '{group_id}' by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
                    )
                    return
                await self.db.delete_tryout_group(self.guild.id, group_id)
                interaction.client.logger.info(
                    f"Deleted tryout group: ID {group_id} by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
                )
                embed = discord.Embed(
                    title="Group Deleted",
                    description=f"Group deleted successfully: ID {group_id}",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

            await self.update_callback()

        except Exception as e:
            interaction.client.logger.error(f"Error managing tryout group '{group_id}' in guild {self.guild.id}: {e}")
            embed = discord.Embed(
                title="Error",
                description="Failed to manage tryout group. Please try again later.",
                color=0xE02B2B,  # Dark red for errors
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

# Define the AutomodSettingsView using BaseChannelModal
class AutomodSettingsView(discord.ui.View):
    def __init__(self, db, guild, settings_cog):
        super().__init__(timeout=180)
        self.db = db
        self.guild = guild
        self.settings_cog = settings_cog
        self.message = None

    @discord.ui.button(label="Toggle Automod", style=discord.ButtonStyle.primary, emoji="🔄")
    async def toggle_automod(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Toggles the Automod feature on or off.
        """
        await interaction.response.defer()
        try:
            await self.db.toggle_server_setting(self.guild.id, 'automod_enabled')
            await self.update_settings_message()
            server_settings = await self.db.get_server_settings(self.guild.id)
            status = "enabled" if server_settings.get('automod_enabled') else "disabled"
            self.settings_cog.bot.logger.info(
                f"Automod {status} by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
            )
        except Exception as e:
            self.settings_cog.bot.logger.error(f"Error toggling Automod in guild {self.guild.id}: {e}")
            embed = discord.Embed(
                title="Error",
                description="Failed to toggle Automod. Please try again later.",
                color=0xE02B2B,  # Dark red for errors
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Toggle Logging", style=discord.ButtonStyle.primary, emoji="📝")
    async def toggle_logging(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Toggles the Automod logging feature on or off.
        """
        await interaction.response.defer()
        try:
            await self.db.toggle_server_setting(self.guild.id, 'automod_logging_enabled')
            await self.update_settings_message()
            server_settings = await self.db.get_server_settings(self.guild.id)
            status = "enabled" if server_settings.get('automod_logging_enabled') else "disabled"
            self.settings_cog.bot.logger.info(
                f"Automod logging {status} by user {interaction.user} (ID: {interaction.user.id}) in guild {self.guild.name} (ID: {self.guild.id})."
            )
        except Exception as e:
            self.settings_cog.bot.logger.error(f"Error toggling Automod logging in guild {self.guild.id}: {e}")
            embed = discord.Embed(
                title="Error",
                description="Failed to toggle Logging. Please try again later.",
                color=0xE02B2B,  # Dark red for errors
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Set Log Channel", style=discord.ButtonStyle.primary, emoji="📌")
    async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Opens a modal to set the Automod log channel.
        """
        await interaction.response.send_modal(
            BaseChannelModal(
                db=self.db,
                guild=self.guild,
                setting_name='automod_log_channel_id',
                update_callback=self.update_settings_message,
                title="Set Automod Log Channel"
            )
        )

    async def update_settings_message(self):
        """
        Updates the embed message to reflect the current Automod settings.
        """
        try:
            server_settings = await self.db.get_server_settings(self.guild.id)
            embed = self.settings_cog.create_automod_settings_embed(server_settings)
            await self.message.edit(embed=embed, view=self)
            self.settings_cog.bot.logger.debug(f"Updated Automod settings message in guild {self.guild.id}.")
        except Exception as e:
            self.settings_cog.bot.logger.error(f"Error updating Automod settings message in guild {self.guild.id}: {e}")

    async def on_timeout(self):
        """
        Disables all buttons when the view times out.
        """
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)
        self.settings_cog.bot.logger.debug(f"AutomodSettingsView timed out in guild {self.guild.id}.")

# Define the ModerationSettingsView using BaseChannelModal and BaseRoleManagementModal
class ModerationSettingsView(discord.ui.View):
    def __init__(self, db, guild, settings_cog):
        super().__init__(timeout=180)
        self.db = db
        self.guild = guild
        self.settings_cog = settings_cog
        self.message = None

    @discord.ui.button(label="Set Log Channel", style=discord.ButtonStyle.primary, emoji="📌")
    async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Opens a modal to set the Moderation log channel.
        """
        await interaction.response.send_modal(
            BaseChannelModal(
                db=self.db,
                guild=self.guild,
                setting_name='mod_log_channel_id',
                update_callback=self.update_settings_message,
                title="Set Moderation Log Channel"
            )
        )

    @discord.ui.button(label="Manage Allowed Roles", style=discord.ButtonStyle.primary, emoji="👥")
    async def manage_allowed_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Opens a modal to manage allowed roles for moderation.
        """
        await interaction.response.send_modal(
            BaseRoleManagementModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.update_settings_message,
                add_method=self.db.add_moderation_allowed_role,
                remove_method=self.db.remove_moderation_allowed_role,
                success_title="Allowed Roles Updated"
            )
        )

    async def update_settings_message(self):
        """
        Updates the embed message to reflect the current Moderation settings.
        """
        try:
            embed = await self.settings_cog.create_moderation_settings_embed(self.guild)
            await self.message.edit(embed=embed, view=self)
            self.settings_cog.bot.logger.debug(f"Updated Moderation settings message in guild {self.guild.id}.")
        except Exception as e:
            self.settings_cog.bot.logger.error(f"Error updating Moderation settings message in guild {self.guild.id}: {e}")

    async def on_timeout(self):
        """
        Disables all buttons when the view times out.
        """
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)
        self.settings_cog.bot.logger.debug(f"ModerationSettingsView timed out in guild {self.guild.id}.")

# Define the TryoutSettingsView using BaseChannelModal and other modals
class TryoutSettingsView(discord.ui.View):
    def __init__(self, db, guild, settings_cog):
        super().__init__(timeout=180)
        self.db = db
        self.guild = guild
        self.settings_cog = settings_cog
        self.message = None

    @discord.ui.button(label="Set Tryout Channel", style=discord.ButtonStyle.primary, emoji="📌")
    async def set_tryout_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Opens a modal to set the Tryout channel.
        """
        await interaction.response.send_modal(
            BaseChannelModal(
                db=self.db,
                guild=self.guild,
                setting_name='tryout_channel_id',
                update_callback=self.update_settings_message,
                title="Set Tryout Channel"
            )
        )

    @discord.ui.button(label="Manage Required Roles", style=discord.ButtonStyle.primary, emoji="👥")
    async def manage_required_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Opens a modal to manage required roles for tryouts.
        """
        await interaction.response.send_modal(
            BaseRoleManagementModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.update_settings_message,
                add_method=self.db.add_tryout_required_role,
                remove_method=self.db.remove_tryout_required_role,
                success_title="Required Roles Updated"
            )
        )

    @discord.ui.button(label="Manage Tryout Groups", style=discord.ButtonStyle.primary, emoji="🔧")
    async def manage_tryout_groups(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Opens a modal to manage tryout groups.
        """
        await interaction.response.send_modal(
            ManageTryoutGroupsModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.update_settings_message
            )
        )

    async def update_settings_message(self):
        """
        Updates the embed message to reflect the current Tryout settings.
        """
        try:
            embed = await self.settings_cog.create_tryout_settings_embed(self.guild)
            await self.message.edit(embed=embed, view=self)
            self.settings_cog.bot.logger.debug(f"Updated Tryout settings message in guild {self.guild.id}.")
        except Exception as e:
            self.settings_cog.bot.logger.error(f"Error updating Tryout settings message in guild {self.guild.id}: {e}")

    async def on_timeout(self):
        """
        Disables all buttons when the view times out.
        """
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)
        self.settings_cog.bot.logger.debug(f"TryoutSettingsView timed out in guild {self.guild.id}.")

# Setup function to add the cog
async def setup(bot):
    await bot.add_cog(Settings(bot))

