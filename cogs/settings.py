import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging

# Logger setup
logger = logging.getLogger("SettingsCog")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
logger.addHandler(handler)

# Define the check function outside the class
async def is_admin_or_owner(interaction: discord.Interaction) -> bool:
    bot = interaction.client
    # Cache owner_id if not already cached
    if not hasattr(bot, 'owner_id'):
        app_info = await bot.application_info()
        bot.owner_id = app_info.owner.id
    bot_owner_id = bot.owner_id
    if interaction.user.id == bot_owner_id:
        return True
    if interaction.user.guild_permissions.administrator:
        return True
    raise app_commands.MissingPermissions(['administrator'])

class Settings(commands.Cog, name="settings"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = None  # Placeholder for the database manager instance

    async def cog_load(self):
        self.db = self.bot.database  # Access DatabaseManager from the bot instance
        if not self.db:
            raise ValueError("DatabaseManager is not initialized in the bot.")

    @app_commands.command(name="settings", description="Configure bot settings.")
    @app_commands.check(is_admin_or_owner)
    @app_commands.describe(category="The category of settings to configure.")
    async def settings_command(self, interaction: discord.Interaction, category: str):
        await interaction.response.defer(ephemeral=True)

        category = category.lower()
        if category == "automod":
            server_settings = await self.db.get_server_settings(interaction.guild.id)
            if not server_settings:
                await self.db.initialize_server_settings(interaction.guild.id)
                server_settings = await self.db.get_server_settings(interaction.guild.id)
            embed = self.create_automod_settings_embed(server_settings)
            view = AutomodSettingsView(self.db, interaction.guild, settings_cog=self)
            view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        elif category == "tryout":
            embed = await self.create_tryout_settings_embed(interaction.guild)
            view = TryoutSettingsView(self.db, interaction.guild, settings_cog=self)
            view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        elif category == "moderation":
            embed = await self.create_moderation_settings_embed(interaction.guild)
            view = ModerationSettingsView(self.db, interaction.guild, settings_cog=self)
            view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            embed = discord.Embed(
                title="Invalid Category",
                description=f"The category `{category}` is not recognized.",
                color=discord.Color.red(),  # Consistent error color
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @settings_command.autocomplete('category')
    async def settings_autocomplete(self, interaction: discord.Interaction, current: str):
        categories = ["automod", "tryout", "moderation"]
        return [
            app_commands.Choice(name=category.capitalize(), value=category)
            for category in categories if current.lower() in category.lower()
        ]

    def create_automod_settings_embed(self, server_settings):
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
        embed_color = discord.Color.red()  # Consistent error color
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="Missing Permissions",
                description="You need the `Administrator` permission or the bot owner to use this command.",
                color=embed_color,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        elif isinstance(error, discord.app_commands.errors.MissingArgument):
            embed = discord.Embed(
                title="Missing Argument",
                description="Please provide a category. Example: `/settings category:automod`",
                color=embed_color
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            logger.error(f"Error in /settings command: {error}")
            embed = discord.Embed(
                title="Error",
                description="An unexpected error occurred.",
                color=embed_color,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

# Define the AutomodSettingsView
class AutomodSettingsView(discord.ui.View):
    def __init__(self, db, guild, settings_cog):
        super().__init__(timeout=180)
        self.db = db
        self.guild = guild
        self.settings_cog = settings_cog
        self.message = None

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
        await interaction.response.send_modal(
            SetChannelModal(
                db=self.db,
                guild=self.guild,
                setting_name='automod_log_channel_id',
                update_callback=self.update_settings_message
            )
        )

    async def update_settings_message(self):
        server_settings = await self.db.get_server_settings(self.guild.id)
        embed = self.settings_cog.create_automod_settings_embed(server_settings)
        await self.message.edit(embed=embed, view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)

# Modal to set a channel by ID
class SetChannelModal(discord.ui.Modal, title="Set Channel by ID"):
    channel_id = discord.ui.TextInput(
        label="Channel ID",
        placeholder="Enter the ID of the channel",
        required=True,
        max_length=20
    )

    def __init__(self, db, guild, setting_name, update_callback):
        super().__init__()
        self.db = db
        self.guild = guild
        self.setting_name = setting_name
        self.update_callback = update_callback

    async def on_submit(self, interaction: discord.Interaction):
        channel_id_str = self.channel_id.value.strip()
        if not channel_id_str.isdigit():
            embed = discord.Embed(
                title="Invalid Channel ID",
                description="Please ensure the Channel ID is numeric.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        channel_id = int(channel_id_str)
        channel = self.guild.get_channel(channel_id)
        if not channel:
            embed = discord.Embed(
                title="Channel Not Found",
                description="Please ensure the Channel ID is correct and try again.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        try:
            if self.setting_name == 'tryout_channel_id':
                await self.db.set_tryout_channel_id(self.guild.id, channel_id)
            elif self.setting_name == 'automod_log_channel_id':
                await self.db.update_server_setting(self.guild.id, self.setting_name, str(channel_id))
            elif self.setting_name == 'mod_log_channel_id':
                await self.db.set_mod_log_channel(self.guild.id, channel_id)
            else:
                await self.db.update_server_setting(self.guild.id, self.setting_name, str(channel_id))
            embed = discord.Embed(
                title="Channel Set",
                description=f"Channel set to {channel.mention}.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            await self.update_callback()
        except Exception as e:
            logger.error(f"Error setting channel: {e}")
            embed = discord.Embed(
                title="Error",
                description="Failed to set the channel. Please try again later.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

# Define the ModerationSettingsView
class ModerationSettingsView(discord.ui.View):
    def __init__(self, db, guild, settings_cog):
        super().__init__(timeout=180)
        self.db = db
        self.guild = guild
        self.settings_cog = settings_cog
        self.message = None

    @discord.ui.button(label="Set Log Channel", style=discord.ButtonStyle.primary, emoji="📌")
    async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            SetModerationLogChannelModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.update_settings_message
            )
        )

    @discord.ui.button(label="Manage Allowed Roles", style=discord.ButtonStyle.primary, emoji="👥")
    async def manage_allowed_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            ManageModerationAllowedRolesModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.update_settings_message
            )
        )

    async def update_settings_message(self):
        embed = await self.settings_cog.create_moderation_settings_embed(self.guild)
        await self.message.edit(embed=embed, view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)

# Modal to set the moderation log channel
class SetModerationLogChannelModal(discord.ui.Modal, title="Set Moderation Log Channel"):
    channel_id = discord.ui.TextInput(
        label="Channel ID",
        placeholder="Enter the ID of the log channel",
        required=True,
        max_length=20
    )

    def __init__(self, db, guild, update_callback):
        super().__init__()
        self.db = db
        self.guild = guild
        self.update_callback = update_callback

    async def on_submit(self, interaction: discord.Interaction):
        channel_id_str = self.channel_id.value.strip()
        if not channel_id_str.isdigit():
            embed = discord.Embed(
                title="Invalid Channel ID",
                description="Please ensure the Channel ID is numeric.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        channel_id = int(channel_id_str)
        channel = self.guild.get_channel(channel_id)
        if not channel:
            embed = discord.Embed(
                title="Channel Not Found",
                description="Please ensure the Channel ID is correct and try again.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        try:
            await self.db.set_mod_log_channel(self.guild.id, channel_id)
            embed = discord.Embed(
                title="Moderation Log Channel Set",
                description=f"Moderation log channel set to {channel.mention}.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            await self.update_callback()
        except Exception as e:
            logger.error(f"Error setting moderation log channel: {e}")
            embed = discord.Embed(
                title="Error",
                description="Failed to set the log channel. Please try again later.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

# Modal to manage moderation allowed roles
class ManageModerationAllowedRolesModal(discord.ui.Modal, title="Manage Allowed Roles"):
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

    def __init__(self, db, guild, update_callback):
        super().__init__()
        self.db = db
        self.guild = guild
        self.update_callback = update_callback

    async def on_submit(self, interaction: discord.Interaction):
        action_input = self.action.value.strip().lower()
        role_ids_str = self.role_ids.value.strip()
        role_id_list = [rid.strip() for rid in role_ids_str.split(' ') if rid.strip()]
        
        if action_input not in ['add', 'remove']:
            embed = discord.Embed(
                title="Invalid Action",
                description="Please enter 'add' or 'remove' as the action.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not role_id_list:
            embed = discord.Embed(
                title="No Role IDs Provided",
                description="Please enter at least one Role ID.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
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
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            if action_input == 'add':
                for role_id in valid_role_ids:
                    await self.db.add_moderation_allowed_role(self.guild.id, role_id)
                role_mentions = [f"<@&{rid}>" for rid in valid_role_ids]
                roles_display = ", ".join(role_mentions)
                embed = discord.Embed(
                    title="Roles Added",
                    description=f"Roles added successfully: {roles_display}",
                    color=discord.Color.green()
                )
                logger.debug(f"Added moderation allowed roles: {roles_display}")
            elif action_input == 'remove':
                for role_id in valid_role_ids:
                    await self.db.remove_moderation_allowed_role(self.guild.id, role_id)
                role_mentions = [f"<@&{rid}>" for rid in valid_role_ids]
                roles_display = ", ".join(role_mentions)
                embed = discord.Embed(
                    title="Roles Removed",
                    description=f"Roles removed successfully: {roles_display}",
                    color=discord.Color.green()
                )
                logger.debug(f"Removed moderation allowed roles: {roles_display}")

            await interaction.response.send_message(embed=embed, ephemeral=True)
            await self.update_callback()

        except Exception as e:
            logger.error(f"Error managing moderation allowed roles: {e}")
            embed = discord.Embed(
                title="Error",
                description="Failed to manage allowed roles. Please try again later.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

# Modal to manage tryout required roles
class ManageRolesModal(discord.ui.Modal, title="Manage Required Roles"):
    role_ids = discord.ui.TextInput(
        label="Role IDs",
        placeholder="Enter Role IDs separated by spaces",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
    )

    action = discord.ui.TextInput(
        label="Action",
        placeholder="Enter 'add' or 'remove'",
        required=True,
        max_length=6
    )

    def __init__(self, db, guild, update_callback):
        super().__init__()
        self.db = db
        self.guild = guild
        self.update_callback = update_callback

    async def on_submit(self, interaction: discord.Interaction):
        action_input = self.action.value.strip().lower()
        role_ids_str = self.role_ids.value.strip()
        role_id_list = [rid.strip() for rid in role_ids_str.split(' ') if rid.strip()]
        
        if action_input not in ['add', 'remove']:
            embed = discord.Embed(
                title="Invalid Action",
                description="Please enter 'add' or 'remove' as the action.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not role_id_list:
            embed = discord.Embed(
                title="No Role IDs Provided",
                description="Please enter at least one Role ID.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
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
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            if action_input == 'add':
                for role_id in valid_role_ids:
                    await self.db.add_tryout_required_role(self.guild.id, role_id)
                role_mentions = [f"<@&{rid}>" for rid in valid_role_ids]
                roles_display = ", ".join(role_mentions)
                embed = discord.Embed(
                    title="Roles Added",
                    description=f"Roles added successfully: {roles_display}",
                    color=discord.Color.green()
                )
                logger.debug(f"Added tryout required roles: {roles_display}")
            elif action_input == 'remove':
                for role_id in valid_role_ids:
                    await self.db.remove_tryout_required_role(self.guild.id, role_id)
                role_mentions = [f"<@&{rid}>" for rid in valid_role_ids]
                roles_display = ", ".join(role_mentions)
                embed = discord.Embed(
                    title="Roles Removed",
                    description=f"Roles removed successfully: {roles_display}",
                    color=discord.Color.green()
                )
                logger.debug(f"Removed tryout required roles: {roles_display}")

            await interaction.response.send_message(embed=embed, ephemeral=True)
            await self.update_callback()

        except Exception as e:
            logger.error(f"Error managing tryout required roles: {e}")
            embed = discord.Embed(
                title="Error",
                description="Failed to manage required roles. Please try again later.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

# Modal to manage tryout groups
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
        action = self.action.value.strip().lower()
        group_id = self.group_id.value.strip()

        if action not in ['add', 'edit', 'delete']:
            embed = discord.Embed(
                title="Invalid Action",
                description="Please enter 'add', 'edit', or 'delete' as the action.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not group_id.isdigit():
            embed = discord.Embed(
                title="Invalid Group ID",
                description="Please ensure the Group ID is numeric.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            if action == 'add':
                # Ensure all fields are provided
                if not self.event_name.value.strip() or not self.description.value.strip() or not self.link.value.strip():
                    embed = discord.Embed(
                        title="Missing Information",
                        description="For adding a group, please provide Event Name, Description, and Link.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                # Check if group already exists
                existing_group = await self.db.get_tryout_group(self.guild.id, group_id)
                if existing_group:
                    embed = discord.Embed(
                        title="Group Already Exists",
                        description="A group with this ID already exists.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await self.db.add_tryout_group(
                    self.guild.id,
                    group_id,
                    self.description.value.strip(),
                    self.link.value.strip(),
                    self.event_name.value.strip()
                )
                logger.debug(f"Added new tryout group: {group_id} - {self.event_name.value.strip()}")
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
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
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
                logger.debug(f"Updated tryout group: {group_id} - {event_name}")
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
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await self.db.delete_tryout_group(self.guild.id, group_id)
                logger.debug(f"Deleted tryout group: {group_id}")
                embed = discord.Embed(
                    title="Group Deleted",
                    description=f"Group deleted successfully: ID {group_id}",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

            await self.update_callback()

        except Exception as e:
            logger.error(f"Error managing tryout group: {e}")
            embed = discord.Embed(
                title="Error",
                description="Failed to manage tryout group. Please try again later.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

# Define the TryoutSettingsView
class TryoutSettingsView(discord.ui.View):
    def __init__(self, db, guild, settings_cog):
        super().__init__(timeout=180)
        self.db = db
        self.guild = guild
        self.settings_cog = settings_cog
        self.message = None

    @discord.ui.button(label="Set Tryout Channel", style=discord.ButtonStyle.primary, emoji="📌")
    async def set_tryout_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            SetChannelModal(
                db=self.db,
                guild=self.guild,
                setting_name='tryout_channel_id',
                update_callback=self.update_settings_message
            )
        )

    @discord.ui.button(label="Manage Required Roles", style=discord.ButtonStyle.primary, emoji="👥")
    async def manage_required_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            ManageRolesModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.update_settings_message
            )
        )

    @discord.ui.button(label="Manage Tryout Groups", style=discord.ButtonStyle.primary, emoji="🔧")
    async def manage_tryout_groups(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            ManageTryoutGroupsModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.update_settings_message
            )
        )

    async def update_settings_message(self):
        embed = await self.settings_cog.create_tryout_settings_embed(self.guild)
        await self.message.edit(embed=embed, view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)

# Modal to manage tryout groups
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
        action = self.action.value.strip().lower()
        group_id = self.group_id.value.strip()

        if action not in ['add', 'edit', 'delete']:
            embed = discord.Embed(
                title="Invalid Action",
                description="Please enter 'add', 'edit', or 'delete' as the action.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not group_id.isdigit():
            embed = discord.Embed(
                title="Invalid Group ID",
                description="Please ensure the Group ID is numeric.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            if action == 'add':
                # Ensure all fields are provided
                if not self.event_name.value.strip() or not self.description.value.strip() or not self.link.value.strip():
                    embed = discord.Embed(
                        title="Missing Information",
                        description="For adding a group, please provide Event Name, Description, and Link.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                # Check if group already exists
                existing_group = await self.db.get_tryout_group(self.guild.id, group_id)
                if existing_group:
                    embed = discord.Embed(
                        title="Group Already Exists",
                        description="A group with this ID already exists.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await self.db.add_tryout_group(
                    self.guild.id,
                    group_id,
                    self.description.value.strip(),
                    self.link.value.strip(),
                    self.event_name.value.strip()
                )
                logger.debug(f"Added new tryout group: {group_id} - {self.event_name.value.strip()}")
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
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
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
                logger.debug(f"Updated tryout group: {group_id} - {event_name}")
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
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await self.db.delete_tryout_group(self.guild.id, group_id)
                logger.debug(f"Deleted tryout group: {group_id}")
                embed = discord.Embed(
                    title="Group Deleted",
                    description=f"Group deleted successfully: ID {group_id}",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

            await self.update_callback()

        except Exception as e:
            logger.error(f"Error managing tryout group: {e}")
            embed = discord.Embed(
                title="Error",
                description="Failed to manage tryout group. Please try again later.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

# Setup function
async def setup(bot):
    await bot.add_cog(Settings(bot))
