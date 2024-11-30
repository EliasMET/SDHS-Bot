import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
from math import ceil

# Logger setup
logger = logging.getLogger("SettingsCog")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
logger.addHandler(handler)

# Define the check function outside the class
async def is_admin_or_owner(interaction: discord.Interaction) -> bool:
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

class Settings(commands.Cog):
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
    async def settings(self, interaction: discord.Interaction, category: str):
        await interaction.response.defer(ephemeral=True)

        if category.lower() == "automod":
            server_settings = await self.db.get_server_settings(interaction.guild.id)
            if not server_settings:
                await self.db.initialize_server_settings(interaction.guild.id)
                server_settings = await self.db.get_server_settings(interaction.guild.id)
            embed = self.create_automod_settings_embed(server_settings)
            view = AutomodSettingsView(self.db, interaction.guild, settings_cog=self)
            view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        elif category.lower() == "tryout":
            embed = await self.create_tryout_settings_embed(interaction.guild)
            view = TryoutSettingsView(self.db, interaction.guild, settings_cog=self)
            view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            embed = discord.Embed(
                title="Invalid Category",
                description=f"The category `{category}` is not recognized.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @settings.autocomplete('category')
    async def settings_autocomplete(self, interaction: discord.Interaction, current: str):
        categories = ["automod", "tryout"]
        return [
            app_commands.Choice(name=category, value=category)
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

    @settings.error
    async def settings_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="Missing Permissions",
                description="You need the `Administrator` permission to use this command.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        elif isinstance(error, app_commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="Missing Argument",
                description="You need to specify a category. Example: `/settings category:automod`",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            logger.error(f"Error in /settings command: {error}")
            await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)

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
            await interaction.response.send_message("Invalid Channel ID. Please ensure it's a numeric ID.", ephemeral=True)
            return
        channel_id = int(channel_id_str)
        channel = self.guild.get_channel(channel_id)
        if not channel:
            await interaction.response.send_message("Channel not found. Please ensure the ID is correct and try again.", ephemeral=True)
            return
        try:
            if self.setting_name == 'tryout_channel_id':
                await self.db.set_tryout_channel_id(self.guild.id, channel_id)
            else:
                await self.db.update_server_setting(self.guild.id, self.setting_name, str(channel_id))
            await interaction.response.send_message(f"Channel set to {channel.mention}.", ephemeral=True)
            await self.update_callback()
        except Exception as e:
            logger.error(f"Error setting channel: {e}")
            await interaction.response.send_message("Failed to set the channel. Please try again later.", ephemeral=True)

# Modal to manage required roles by IDs separated by spaces
class ManageRolesModal(discord.ui.Modal, title="Manage Required Roles by IDs"):
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
        role_ids_str = self.role_ids.value.strip()
        role_id_list = [rid.strip() for rid in role_ids_str.split(' ') if rid.strip()]
        if not role_id_list:
            await interaction.response.send_message("No Role IDs provided. Please enter at least one Role ID.", ephemeral=True)
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
            await interaction.response.send_message(
                f"The following Role IDs are invalid or not found: {', '.join(invalid_role_ids)}",
                ephemeral=True
            )
            return

        try:
            # Clear existing roles
            existing_roles = await self.db.get_tryout_required_roles(self.guild.id)
            for role_id in existing_roles:
                await self.db.remove_tryout_required_role(self.guild.id, role_id)

            # Add new roles
            for role_id in valid_role_ids:
                await self.db.add_tryout_required_role(self.guild.id, role_id)

            role_mentions = [f"<@&{rid}>" for rid in valid_role_ids]
            roles_display = ", ".join(role_mentions)
            await interaction.response.send_message(f"Required roles updated successfully: {roles_display}", ephemeral=True)
            await self.update_callback()
        except Exception as e:
            logger.error(f"Error managing roles: {e}")
            await interaction.response.send_message("Failed to update required roles. Please try again later.", ephemeral=True)

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
            await interaction.response.send_message("Invalid action. Please enter 'add', 'edit', or 'delete'.", ephemeral=True)
            return

        if not group_id.isdigit():
            await interaction.response.send_message("Invalid Group ID. Please ensure it's a numeric ID.", ephemeral=True)
            return

        try:
            if action == 'add':
                # Ensure all fields are provided
                if not self.event_name.value.strip() or not self.description.value.strip() or not self.link.value.strip():
                    await interaction.response.send_message("For adding a group, please provide Event Name, Description, and Link.", ephemeral=True)
                    return
                # Check if group already exists
                existing_group = await self.db.get_tryout_group(self.guild.id, group_id)
                if existing_group:
                    await interaction.response.send_message("A group with this ID already exists.", ephemeral=True)
                    return
                await self.db.add_tryout_group(
                    self.guild.id,
                    group_id,
                    self.description.value.strip(),
                    self.link.value.strip(),
                    self.event_name.value.strip()
                )
                logger.debug(f"Added new tryout group: {group_id} - {self.event_name.value.strip()}")
                await interaction.response.send_message(f"Group added successfully: **{self.event_name.value.strip()}** (ID: {group_id})", ephemeral=True)

            elif action == 'edit':
                # Ensure the group exists
                existing_group = await self.db.get_tryout_group(self.guild.id, group_id)
                if not existing_group:
                    await interaction.response.send_message("Group not found. Please ensure the Group ID is correct.", ephemeral=True)
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
                await interaction.response.send_message(f"Group updated successfully: **{event_name}** (ID: {group_id})", ephemeral=True)

            elif action == 'delete':
                # Ensure the group exists
                existing_group = await self.db.get_tryout_group(self.guild.id, group_id)
                if not existing_group:
                    await interaction.response.send_message("Group not found. Please ensure the Group ID is correct.", ephemeral=True)
                    return
                await self.db.delete_tryout_group(self.guild.id, group_id)
                logger.debug(f"Deleted tryout group: {group_id}")
                await interaction.response.send_message(f"Group deleted successfully: ID {group_id}", ephemeral=True)

            await self.update_callback()

        except Exception as e:
            logger.error(f"Error managing tryout group: {e}")
            await interaction.response.send_message("Failed to manage tryout group. Please try again later.", ephemeral=True)

# Setup function
async def setup(bot):
    await bot.add_cog(Settings(bot))
