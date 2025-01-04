import discord
from discord.ext import commands
from discord import app_commands
from enum import Enum
import logging
import traceback

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class SettingsCategory(Enum):
    AUTOMOD = "automod"
    TRYOUT = "tryout"
    MODERATION = "moderation"
    AUTOPROMOTION = "autopromotion"

class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = None
        self.owner_id = None
        self.category_handlers = {
            SettingsCategory.AUTOMOD.value: self.handle_automod_settings,
            SettingsCategory.TRYOUT.value: self.handle_tryout_settings,
            SettingsCategory.MODERATION.value: self.handle_moderation_settings,
            SettingsCategory.AUTOPROMOTION.value: self.handle_autopromotion_settings
        }

    async def cog_load(self):
        self.db = self.bot.database
        if not self.db:
            raise ValueError("DatabaseManager not initialized.")
        self.owner_id = (await self.bot.application_info()).owner.id

    async def is_admin_or_owner(self, interaction: discord.Interaction) -> bool:
        return (
            interaction.user.id == self.owner_id 
            or (interaction.guild and interaction.user.guild_permissions.administrator)
        )

    def create_error_embed(self, title: str, description: str) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=0xE02B2B)

    async def send_error_response(self, interaction: discord.Interaction, title: str, description: str):
        embed = self.create_error_embed(title, description)
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def handle_exception(self, interaction: discord.Interaction, e: Exception, context: str = "handling settings"):
        logger.error("An error occurred while %s:", context)
        traceback.print_exc()
        embed = self.create_error_embed(
            "Error",
            f"An error occurred:\n**{type(e).__name__}:** {e}"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="settings", description="Configure bot settings.")
    @app_commands.choices(category=[
        app_commands.Choice(name="Automod", value=SettingsCategory.AUTOMOD.value),
        app_commands.Choice(name="Tryout", value=SettingsCategory.TRYOUT.value),
        app_commands.Choice(name="Moderation", value=SettingsCategory.MODERATION.value),
        app_commands.Choice(name="Autopromotion", value=SettingsCategory.AUTOPROMOTION.value)
    ])
    async def settings_command(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        if not await self.is_admin_or_owner(interaction):
            return await self.send_error_response(
                interaction,
                "Missing Permissions",
                "You need Administrator permission or be the bot owner."
            )

        await interaction.response.defer(ephemeral=True)
        handler = self.category_handlers.get(category.value)
        if not handler:
            return await interaction.followup.send(
                embed=self.create_error_embed("Invalid Category", f"The category `{category.value}` is not recognized."),
                ephemeral=True
            )

        try:
            await handler(interaction)
        except Exception as e:
            await self.handle_exception(interaction, e, context=f"processing {category.value} settings")

    async def handle_automod_settings(self, interaction: discord.Interaction):
        try:
            settings = await self.db.get_server_settings(interaction.guild.id)
            if not settings:
                await self.db.initialize_server_settings(interaction.guild.id)
                settings = await self.db.get_server_settings(interaction.guild.id)

            embed = await self.create_automod_settings_embed(settings, interaction.guild.id, page=1)
            view = AutomodSettingsView(self.db, interaction.guild, self, page=1)
            view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            logger.error("Error in handle_automod_settings:")
            traceback.print_exc()
            await self.send_error_response(interaction, "Error", f"Failed to load automod settings: {e}")

    async def handle_tryout_settings(self, interaction: discord.Interaction):
        try:
            embed = await self.create_tryout_settings_embed(interaction.guild)
            view = TryoutSettingsView(self.db, interaction.guild, self)
            view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            logger.error("Error in handle_tryout_settings:")
            traceback.print_exc()
            await self.send_error_response(
                interaction,
                "Error",
                f"Failed to load tryout settings: {e}"
            )

    async def handle_moderation_settings(self, interaction: discord.Interaction):
        try:
            embed = await self.create_moderation_settings_embed(interaction.guild)
            view = ModerationSettingsView(self.db, interaction.guild, self)
            view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            logger.error("Error in handle_moderation_settings:")
            traceback.print_exc()
            await self.send_error_response(
                interaction,
                "Error",
                f"Failed to load moderation settings: {e}"
            )

    async def handle_autopromotion_settings(self, interaction: discord.Interaction):
        try:
            embed = await self.create_autopromotion_settings_embed(interaction.guild)
            view = AutopromotionSettingsView(self.db, interaction.guild, self)
            view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            logger.error("Error in handle_autopromotion_settings:")
            traceback.print_exc()
            await self.send_error_response(
                interaction,
                "Error",
                f"Failed to load autopromotion settings: {e}"
            )

    async def create_automod_settings_embed(self, s: dict, guild_id: int, page: int) -> discord.Embed:
        au_status = "✅ Enabled" if s.get('automod_enabled') else "❌ Disabled"
        lg_status = "✅ Enabled" if s.get('automod_logging_enabled') else "❌ Disabled"
        lg_ch = f"<#{s.get('automod_log_channel_id')}>" if s.get('automod_log_channel_id') else "Not Set"
        mute = await self.db.get_automod_mute_duration(guild_id)
        prot = await self.db.get_protected_users(guild_id)
        exempts = await self.db.get_automod_exempt_roles(guild_id)
        prot_display = ", ".join(f"<@{u}>" for u in prot) if prot else "None"
        exempts_display = ", ".join(f"<@&{r}>" for r in exempts) if exempts else "None"
        spam_limit = await self.db.get_automod_spam_limit(guild_id)
        spam_window = await self.db.get_automod_spam_window(guild_id)

        embed = discord.Embed(title="⚙️ Automod Settings", color=discord.Color.blue(), description=f"Page {page}/3")
        embed.set_footer(text="Use the buttons below to configure.")
        
        if page == 1:
            embed.add_field(name="Automod Status", value=au_status, inline=True)
            embed.add_field(name="Logging Status", value=lg_status, inline=True)
            embed.add_field(name="Log Channel", value=lg_ch, inline=False)
        elif page == 2:
            embed.add_field(name="Mute Duration (seconds)", value=str(mute), inline=True)
            embed.add_field(name="Protected Users", value=prot_display, inline=False)
            embed.add_field(name="Exempt Roles", value=exempts_display, inline=False)
        else:  # page 3
            embed.add_field(name="Spam Message Limit", value=str(spam_limit), inline=True)
            embed.add_field(name="Spam Time Window (seconds)", value=str(spam_window), inline=True)

        return embed

    async def create_tryout_settings_embed(self, guild: discord.Guild) -> discord.Embed:
        ch_id = await self.db.get_tryout_channel_id(guild.id)
        ch = f"<#{ch_id}>" if ch_id else "❌ Not Set"
        req = await self.db.get_tryout_required_roles(guild.id)
        req_display = ", ".join(f"<@&{r}>" for r in req) if req else "❌ Not Set"
        groups = await self.db.get_tryout_groups(guild.id)
        grp_display = "\n\n".join(
            f"**🎯 {g[2]}** (ID: `{g[0]}`)\n" +
            f"📝 Description: {g[1]}\n" +
            f"📋 Requirements:\n" + 
            ("\n".join(f"• {r}" for r in g[3]) if g[3] else "None") +
            f"\n🔔 Ping Roles: " + 
            (", ".join(f"<@&{r}>" for r in g[4]) if g[4] else "None")
            for g in groups
        ) if groups else "❌ No groups configured."
        allowed_vcs = await self.db.get_tryout_allowed_vcs(guild.id)
        vc_display = ", ".join(f"<#{vc}>" for vc in allowed_vcs) if allowed_vcs else "❌ Not Set"

        embed = discord.Embed(
            title="⚙️ Tryout Settings",
            color=discord.Color.blue(),
            description="Configure your tryout system settings below."
        )
        embed.add_field(name="📌 Tryout Channel", value=ch, inline=False)
        embed.add_field(name="👥 Required Roles", value=req_display, inline=False)
        embed.add_field(name="🎯 Tryout Groups", value=grp_display, inline=False)
        embed.add_field(name="🔊 Allowed Voice Channels", value=vc_display, inline=False)
        embed.set_footer(text="Use the buttons below to manage settings")
        return embed

    async def create_moderation_settings_embed(self, guild: discord.Guild) -> discord.Embed:
        settings = await self.db.get_server_settings(guild.id)
        ch_id = settings.get('mod_log_channel_id')
        ch = f"<#{ch_id}>" if ch_id else "Not Set"
        roles = await self.db.get_moderation_allowed_roles(guild.id)
        rd = ", ".join(f"<@&{r}>" for r in roles) if roles else "No roles set."

        embed = discord.Embed(title="⚙️ Moderation Settings", color=discord.Color.blue())
        embed.add_field(name="Moderation Log Channel", value=ch, inline=False)
        embed.add_field(name="Allowed Roles", value=rd, inline=False)
        return embed

    async def create_autopromotion_settings_embed(self, guild: discord.Guild) -> discord.Embed:
        ch_id = await self.db.get_autopromotion_channel_id(guild.id)
        ch = f"<#{ch_id}>" if ch_id else "Not Set"
        embed = discord.Embed(title="⚙️ Autopromotion Settings", color=discord.Color.blue())
        embed.add_field(name="Watch Channel", value=ch, inline=False)
        return embed

    @settings_command.error
    async def settings_error(self, interaction: discord.Interaction, error):
        logger.error("Error in settings command:")
        traceback.print_exc()
        if isinstance(error, app_commands.MissingPermissions):
            await self.send_error_response(
                interaction,
                "Missing Permissions",
                "You need Administrator permission or be the bot owner."
            )
        else:
            await self.send_error_response(
                interaction,
                "Error",
                f"An unexpected error occurred: {type(error).__name__}: {error}"
            )


class BaseChannelModal(discord.ui.Modal):
    channel_id = discord.ui.TextInput(label="Channel ID", placeholder="Enter the channel ID", required=True, max_length=20)

    def __init__(self, db, guild, setting_name, update_callback, settings_cog, title="Set Channel"):
        super().__init__(title=title)
        self.db = db
        self.guild = guild
        self.setting_name = setting_name
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    async def validate_channel(self, cid: str):
        if not cid.isdigit():
            return None, "Channel ID must be numeric."
        ch = self.guild.get_channel(int(cid))
        return (ch, None) if ch else (None, "Invalid channel ID.")

    async def on_submit(self, interaction: discord.Interaction):
        ch, err = await self.validate_channel(self.channel_id.value.strip())
        if err:
            return await interaction.response.send_message(embed=discord.Embed(title="Invalid ID", description=err, color=0xE02B2B), ephemeral=True)
        try:
            methods = {
                'tryout_channel_id': self.db.set_tryout_channel_id,
                'automod_log_channel_id': lambda g, c: self.db.update_server_setting(g, 'automod_log_channel_id', str(c)),
                'mod_log_channel_id': self.db.set_mod_log_channel
            }

            if self.setting_name in methods:
                await methods[self.setting_name](self.guild.id, ch.id)
            else:
                await self.db.update_server_setting(self.guild.id, self.setting_name, str(ch.id))

            await interaction.response.send_message(
                embed=discord.Embed(title="Channel Set", description=f"Channel set to {ch.mention}.", color=discord.Color.green()),
                ephemeral=True
            )
            await self.update_callback()
        except Exception as e:
            logger.error("Error in BaseChannelModal on_submit:")
            traceback.print_exc()
            await interaction.response.send_message(
                embed=discord.Embed(title="Error", description=f"Failed to set the channel: {e}", color=0xE02B2B),
                ephemeral=True
            )

class BaseRoleManagementModal(discord.ui.Modal):
    action = discord.ui.TextInput(label="Action", placeholder="add/remove", required=True, max_length=6)
    role_ids = discord.ui.TextInput(label="Role IDs", placeholder="IDs separated by spaces", required=True, style=discord.TextStyle.paragraph, max_length=2000)

    def __init__(self, db, guild, update_callback, add_method, remove_method, success_title, settings_cog):
        super().__init__(title=success_title)
        self.db = db
        self.guild = guild
        self.update_callback = update_callback
        self.add_method = add_method
        self.remove_method = remove_method
        self.success_title = success_title
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        act = self.action.value.strip().lower()
        if act not in ['add','remove']:
            return await interaction.response.send_message(
                embed=discord.Embed(title="Invalid Action", description="Use 'add' or 'remove'.", color=0xE02B2B),
                ephemeral=True
            )

        ids = [x.strip() for x in self.role_ids.value.strip().split() if x.strip()]
        if not ids:
            return await interaction.response.send_message(
                embed=discord.Embed(title="No IDs Provided", description="Provide at least one ID.", color=0xE02B2B),
                ephemeral=True
            )

        valid, invalid = [], []
        for rid in ids:
            if rid.isdigit():
                role = self.guild.get_role(int(rid))
                if role:
                    valid.append(role.id)
                else:
                    invalid.append(rid)
            else:
                invalid.append(rid)

        if invalid:
            return await interaction.response.send_message(
                embed=discord.Embed(title="Invalid IDs", description=", ".join(invalid), color=0xE02B2B),
                ephemeral=True
            )

        try:
            method = self.add_method if act == 'add' else self.remove_method
            for v in valid:
                await method(self.guild.id, v)

            md = ", ".join(f"<@&{v}>" for v in valid)
            await interaction.response.send_message(
                embed=discord.Embed(title=self.success_title, description=f"Successfully {act}ed: {md}", color=discord.Color.green()),
                ephemeral=True
            )
            await self.update_callback()
        except Exception as e:
            logger.error("Error in BaseRoleManagementModal on_submit:")
            traceback.print_exc()
            await interaction.response.send_message(
                embed=discord.Embed(title="Error", description=f"Failed to manage roles: {e}", color=0xE02B2B),
                ephemeral=True
            )

class BaseVCManagementModal(discord.ui.Modal):
    action = discord.ui.TextInput(label="Action", placeholder="add/remove", required=True, max_length=6)
    vc_ids = discord.ui.TextInput(label="Voice Channel IDs", placeholder="IDs separated by spaces", required=True, style=discord.TextStyle.paragraph, max_length=2000)

    def __init__(self, db, guild, update_callback, add_method, remove_method, success_title, settings_cog):
        super().__init__(title=success_title)
        self.db = db
        self.guild = guild
        self.update_callback = update_callback
        self.add_method = add_method
        self.remove_method = remove_method
        self.success_title = success_title
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        act = self.action.value.strip().lower()
        if act not in ['add','remove']:
            return await interaction.response.send_message(
                embed=discord.Embed(title="Invalid Action", description="Use 'add' or 'remove'.", color=0xE02B2B),
                ephemeral=True
            )

        ids = [x.strip() for x in self.vc_ids.value.strip().split() if x.strip()]
        if not ids:
            return await interaction.response.send_message(
                embed=discord.Embed(title="No IDs Provided", description="Provide at least one ID.", color=0xE02B2B),
                ephemeral=True
            )

        valid, invalid = [], []
        for vid in ids:
            if vid.isdigit():
                ch = self.guild.get_channel(int(vid))
                if ch and ch.type == discord.ChannelType.voice:
                    valid.append(ch.id)
                else:
                    invalid.append(vid)
            else:
                invalid.append(vid)

        if invalid:
            return await interaction.response.send_message(
                embed=discord.Embed(title="Invalid Channel IDs", description=", ".join(invalid), color=0xE02B2B),
                ephemeral=True
            )

        try:
            method = self.add_method if act == 'add' else self.remove_method
            for v in valid:
                await method(self.guild.id, v)

            md = ", ".join(f"<#{v}>" for v in valid)
            await interaction.response.send_message(
                embed=discord.Embed(title=self.success_title, description=f"Successfully {act}ed: {md}", color=discord.Color.green()),
                ephemeral=True
            )
            await self.update_callback()
        except Exception as e:
            logger.error("Error in BaseVCManagementModal on_submit:")
            traceback.print_exc()
            await interaction.response.send_message(
                embed=discord.Embed(title="Error", description=f"Failed to manage voice channels: {e}", color=0xE02B2B),
                ephemeral=True
            )

class TryoutGroupSelectView(discord.ui.View):
    def __init__(self, db, guild, settings_cog):
        super().__init__(timeout=180)
        self.db = db
        self.guild = guild
        self.settings_cog = settings_cog
        self.message = None
        self.add_group_select()

    def add_group_select(self):
        select = discord.ui.Select(
            placeholder="📋 Select a group to edit or create new",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Create New Group",
                    value="new",
                    description="Create a new tryout group",
                    emoji="➕"
                )
            ]
        )
        select.callback = self.group_select_callback
        self.add_item(select)
        self.group_select = select

    @discord.ui.button(label="Back to Settings", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def back_btn(self, interaction: discord.Interaction, _):
        view = TryoutSettingsView(self.db, self.guild, self.settings_cog)
        embed = await self.settings_cog.create_tryout_settings_embed(self.guild)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = interaction.message

    async def update_group_options(self):
        groups = await self.db.get_tryout_groups(self.guild.id)
        options = [
            discord.SelectOption(
                label=f"{g[2]}",  # event_name
                value=g[0],  # group_id
                description=f"ID: {g[0]}",
                emoji="🎯"
            )
            for g in groups
        ]
        options.insert(0, discord.SelectOption(
            label="Create New Group",
            value="new",
            description="Create a new tryout group",
            emoji="➕"
        ))
        self.group_select.options = options

    async def group_select_callback(self, interaction: discord.Interaction):
        selected_value = self.group_select.values[0]
        
        if selected_value == "new":
            # Show modal for new group creation
            modal = NewTryoutGroupModal(self.db, self.guild, self.update_view, self.settings_cog)
            await interaction.response.send_modal(modal)
        else:
            # Show management view for existing group
            group = await self.db.get_tryout_group(self.guild.id, selected_value)
            if group:
                view = GroupManagementView(self.db, self.guild, group, self.update_view, self.settings_cog)
                embed = await view.create_group_embed()
                await interaction.response.edit_message(embed=embed, view=view)
                view.message = interaction.message

    async def update_view(self):
        if self.message:
            await self.update_group_options()
            embed = await self.settings_cog.create_tryout_settings_embed(self.guild)
            await self.message.edit(embed=embed, view=self)

class NewTryoutGroupModal(discord.ui.Modal):
    group_id = discord.ui.TextInput(
        label="Group ID",
        placeholder="Enter numeric group ID (e.g., 123456789)",
        required=True,
        max_length=20
    )
    event_name = discord.ui.TextInput(
        label="Event Name",
        placeholder="Enter event name (e.g., Combat Tryouts)",
        required=True,
        max_length=100
    )
    description = discord.ui.TextInput(
        label="Description",
        placeholder="Enter a detailed description of the tryout group",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
    )

    def __init__(self, db, guild, update_callback, settings_cog):
        super().__init__(title="✨ Create New Tryout Group")
        self.db = db
        self.guild = guild
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            gid = self.group_id.value.strip()
            if not gid.isdigit():
                return await interaction.response.send_message(
                    embed=discord.Embed(title="❌ Invalid ID", description="Group ID must be numeric.", color=discord.Color.red()),
                    ephemeral=True
                )

            if await self.db.get_tryout_group(self.guild.id, gid):
                return await interaction.response.send_message(
                    embed=discord.Embed(title="❌ Group Exists", description="This ID already exists.", color=discord.Color.red()),
                    ephemeral=True
                )

            await self.db.add_tryout_group(
                self.guild.id,
                gid,
                self.description.value.strip(),
                self.event_name.value.strip(),
                requirements=[]
            )

            # Get the newly created group and show its management view
            group = await self.db.get_tryout_group(self.guild.id, gid)
            if group:
                view = GroupManagementView(self.db, self.guild, group, self.update_callback, self.settings_cog)
                embed = await view.create_group_embed()
                await interaction.response.edit_message(embed=embed, view=view)
                view.message = interaction.message

        except Exception as e:
            logger.error(f"Error creating group: {e}")
            await interaction.response.send_message(
                embed=discord.Embed(title="❌ Error", description=str(e), color=discord.Color.red()),
                ephemeral=True
            )

class GroupManagementView(discord.ui.View):
    def __init__(self, db, guild, group, update_callback, settings_cog):
        super().__init__(timeout=180)
        self.db = db
        self.guild = guild
        self.group = group
        self.update_callback = update_callback
        self.settings_cog = settings_cog
        self.message = None

    async def create_group_embed(self) -> discord.Embed:
        group_id, description, event_name, requirements, ping_roles = self.group
        
        embed = discord.Embed(
            title=f"🎯 Group Management: {event_name}",
            color=discord.Color.blue()
        )
        
        # Add a nice header with group ID
        embed.description = f"**🆔 Group ID:** `{group_id}`\n\n"
        
        # Add description with proper formatting
        embed.description += f"**📝 Description**\n{description}\n\n"
        
        # Add separator
        embed.description += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Format requirements with bullets and spacing
        if requirements:
            req_text = "\n".join(f"• {r}" for r in requirements)
            embed.add_field(
                name="📋 Requirements",
                value=req_text,
                inline=False
            )
        else:
            embed.add_field(
                name="📋 Requirements",
                value="❌ No requirements set",
                inline=False
            )
        
        # Format ping roles with better spacing and commas
        if ping_roles:
            roles_text = ", ".join(f"<@&{r}>" for r in ping_roles)
            embed.add_field(
                name="🔔 Ping Roles",
                value=roles_text,
                inline=False
            )
        else:
            embed.add_field(
                name="🔔 Ping Roles",
                value="❌ No ping roles set",
                inline=False
            )
        
        # Add helpful footer
        embed.set_footer(text="Use the buttons below to edit • Changes will update automatically")
        return embed

    @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.primary, emoji="✏️", row=0)
    async def edit_name_btn(self, interaction: discord.Interaction, _):
        modal = EditGroupNameModal(self.db, self.guild, self.group, self.update_view, self.settings_cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Description", style=discord.ButtonStyle.primary, emoji="📝", row=0)
    async def edit_description_btn(self, interaction: discord.Interaction, _):
        modal = EditGroupDescriptionModal(self.db, self.guild, self.group, self.update_view, self.settings_cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Requirements", style=discord.ButtonStyle.primary, emoji="📋", row=1)
    async def edit_requirements_btn(self, interaction: discord.Interaction, _):
        modal = EditGroupRequirementsModal(self.db, self.guild, self.group, self.update_view, self.settings_cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Ping Roles", style=discord.ButtonStyle.primary, emoji="🔔", row=1)
    async def edit_ping_roles_btn(self, interaction: discord.Interaction, _):
        modal = EditGroupPingRolesModal(self.db, self.guild, self.group, self.update_view, self.settings_cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Delete Group", style=discord.ButtonStyle.danger, emoji="🗑️", row=2)
    async def delete_group_btn(self, interaction: discord.Interaction, _):
        embed = discord.Embed(
            title="⚠️ Confirm Deletion",
            description=(
                f"Are you sure you want to delete the group **{self.group[2]}**?\n\n"
                "**This action cannot be undone!**\n"
                "All settings, requirements, and ping roles will be lost."
            ),
            color=discord.Color.yellow()
        )
        view = DeleteConfirmationView(self.db, self.guild, self.group, self.update_callback, self.settings_cog)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Back to Groups", style=discord.ButtonStyle.secondary, emoji="◀️", row=2)
    async def back_btn(self, interaction: discord.Interaction, _):
        view = TryoutGroupSelectView(self.db, self.guild, self.settings_cog)
        await view.update_group_options()
        embed = await self.settings_cog.create_tryout_settings_embed(self.guild)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = interaction.message

    async def update_view(self):
        if self.message:
            self.group = await self.db.get_tryout_group(self.guild.id, self.group[0])
            if self.group:
                embed = await self.create_group_embed()
                await self.message.edit(embed=embed, view=self)
            await self.update_callback()

class DeleteConfirmationView(discord.ui.View):
    def __init__(self, db, guild, group, update_callback, settings_cog):
        super().__init__(timeout=60)
        self.db = db
        self.guild = guild
        self.group = group
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm_btn(self, interaction: discord.Interaction, _):
        await self.db.delete_tryout_group(self.guild.id, self.group[0])
        embed = discord.Embed(
            title="✅ Group Deleted",
            description=f"Successfully deleted group: **{self.group[2]}**",
            color=discord.Color.green()
        )
        # Return to group selection
        view = TryoutGroupSelectView(self.db, self.guild, self.settings_cog)
        await view.update_group_options()
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = interaction.message
        await self.update_callback()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel_btn(self, interaction: discord.Interaction, _):
        # Return to group management
        view = GroupManagementView(self.db, self.guild, self.group, self.update_callback, self.settings_cog)
        embed = await view.create_group_embed()
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = interaction.message

class EditGroupNameModal(discord.ui.Modal):
    name = discord.ui.TextInput(
        label="Event Name",
        placeholder="Enter new event name",
        required=True,
        max_length=100
    )

    def __init__(self, db, guild, group, update_callback, settings_cog):
        super().__init__(title=f"Edit Group Name - {group[2]}")
        self.db = db
        self.guild = guild
        self.group = group
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.db.update_tryout_group(
            self.guild.id,
            self.group[0],
            self.group[1],
            self.name.value.strip(),
            self.group[3]
        )
        embed = discord.Embed(
            title="Name Updated",
            description=f"Updated group name to: {self.name.value.strip()}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await self.update_callback()

class EditGroupDescriptionModal(discord.ui.Modal):
    description = discord.ui.TextInput(
        label="Description",
        placeholder="Enter new description",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
    )

    def __init__(self, db, guild, group, update_callback, settings_cog):
        super().__init__(title=f"Edit Description - {group[2]}")
        self.db = db
        self.guild = guild
        self.group = group
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.db.update_tryout_group(
            self.guild.id,
            self.group[0],
            self.description.value.strip(),
            self.group[2],
            self.group[3]
        )
        embed = discord.Embed(
            title="Description Updated",
            description="Group description has been updated.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await self.update_callback()

class EditGroupRequirementsModal(discord.ui.Modal):
    requirements = discord.ui.TextInput(
        label="Requirements",
        placeholder="Enter requirements (one per line)",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
    )

    def __init__(self, db, guild, group, update_callback, settings_cog):
        super().__init__(title=f"Edit Requirements - {group[2]}")
        self.db = db
        self.guild = guild
        self.group = group
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        reqs = [r.strip() for r in self.requirements.value.strip().split('\n') if r.strip()]
        await self.db.update_tryout_group(
            self.guild.id,
            self.group[0],
            self.group[1],
            self.group[2],
            reqs
        )
        embed = discord.Embed(
            title="Requirements Updated",
            description=f"Updated requirements for group: {self.group[2]}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await self.update_callback()

class EditGroupPingRolesModal(discord.ui.Modal):
    roles = discord.ui.TextInput(
        label="Ping Roles",
        placeholder="Enter role IDs separated by spaces (e.g., 123456789 987654321)",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
    )

    def __init__(self, db, guild, group, update_callback, settings_cog):
        super().__init__(title=f"🔔 Edit Ping Roles - {group[2]}")
        self.db = db
        self.guild = guild
        self.group = group
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Remove existing roles
            for role_id in self.group[4]:
                await self.db.remove_group_ping_role(self.guild.id, self.group[0], int(role_id))

            # Add new roles
            valid_roles = []
            invalid_roles = []
            for role_id in self.roles.value.strip().split():
                role_id = role_id.strip()
                if role_id.isdigit():
                    role = self.guild.get_role(int(role_id))
                    if role:
                        valid_roles.append(role.id)
                        await self.db.add_group_ping_role(self.guild.id, self.group[0], role.id)
                    else:
                        invalid_roles.append(role_id)
                elif role_id:  # Only add to invalid if it's not empty
                    invalid_roles.append(role_id)

            # Get updated group data
            updated_group = await self.db.get_tryout_group(self.guild.id, self.group[0])
            if updated_group:
                # Update the group management view
                view = GroupManagementView(self.db, self.guild, updated_group, self.update_callback, self.settings_cog)
                embed = await view.create_group_embed()
                await interaction.response.edit_message(embed=embed, view=view)
                view.message = interaction.message

                # Create and send success message as followup
                success_embed = discord.Embed(
                    title="✅ Ping Roles Updated",
                    description=f"Successfully updated ping roles for **{updated_group[2]}**",
                    color=discord.Color.green()
                )
                if valid_roles:
                    success_embed.add_field(
                        name="🔔 Added Roles",
                        value=", ".join(f"<@&{rid}>" for rid in valid_roles),
                        inline=False
                    )
                if invalid_roles:
                    success_embed.add_field(
                        name="❌ Invalid IDs",
                        value=", ".join(f"`{rid}`" for rid in invalid_roles),
                        inline=False
                    )
                await interaction.followup.send(embed=success_embed, ephemeral=True)

                # Update the settings view
                await self.update_callback()

        except Exception as e:
            logger.error(f"Error updating ping roles: {e}")
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Error",
                    description=f"An error occurred: {str(e)}",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

# Update the TryoutSettingsView to use the new group management
class TryoutSettingsView(discord.ui.View):
    def __init__(self, db, guild, settings_cog):
        super().__init__(timeout=180)
        self.db = db
        self.guild = guild
        self.settings_cog = settings_cog
        self.message = None

    @discord.ui.button(label="Set Tryout Channel", style=discord.ButtonStyle.primary, emoji="📌")
    async def set_tryout_channel_btn(self, interaction: discord.Interaction, _):
        if self.message:
            await interaction.response.send_modal(BaseChannelModal(
                db=self.db,
                guild=self.guild,
                setting_name='tryout_channel_id',
                update_callback=self.async_update_view,
                settings_cog=self.settings_cog,
                title="Set Tryout Channel"
            ))

    @discord.ui.button(label="Manage Required Roles", style=discord.ButtonStyle.primary, emoji="👥")
    async def manage_required_roles_btn(self, interaction: discord.Interaction, _):
        if self.message:
            await interaction.response.send_modal(BaseRoleManagementModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.async_update_view,
                add_method=self.db.add_tryout_required_role,
                remove_method=self.db.remove_tryout_required_role,
                success_title="Required Roles Updated",
                settings_cog=self.settings_cog
            ))

    @discord.ui.button(label="Manage Tryout Groups", style=discord.ButtonStyle.primary, emoji="🔧")
    async def manage_tryout_groups_btn(self, interaction: discord.Interaction, _):
        if self.message:
            view = TryoutGroupSelectView(self.db, self.guild, self.settings_cog)
            await view.update_group_options()
            embed = await self.settings_cog.create_tryout_settings_embed(self.guild)
            await interaction.response.edit_message(embed=embed, view=view)
            view.message = interaction.message

    @discord.ui.button(label="Manage Allowed Voice Channels", style=discord.ButtonStyle.primary, emoji="🔊")
    async def manage_allowed_vcs_btn(self, interaction: discord.Interaction, _):
        if self.message:
            await interaction.response.send_modal(BaseVCManagementModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.async_update_view,
                add_method=self.db.add_tryout_allowed_vc,
                remove_method=self.db.remove_tryout_allowed_vc,
                success_title="Allowed Voice Channels Updated",
                settings_cog=self.settings_cog
            ))

    async def async_update_view(self):
        if self.message:
            e = await self.settings_cog.create_tryout_settings_embed(self.guild)
            await self.message.edit(embed=e, view=self)

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

class AutopromotionSettingsView(discord.ui.View):
    def __init__(self, db, guild, settings_cog):
        super().__init__(timeout=180)
        self.db = db
        self.guild = guild
        self.settings_cog = settings_cog
        self.message = None

    @discord.ui.button(label="Set Watch Channel", style=discord.ButtonStyle.primary, emoji="📌")
    async def set_channel_btn(self, interaction: discord.Interaction, _):
        if self.message:
            await interaction.response.send_modal(AutopromotionChannelModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.async_update_view,
                settings_cog=self.settings_cog,
                title="Set Autopromotion Watch Channel"
            ))

    async def async_update_view(self):
        if self.message:
            e = await self.settings_cog.create_autopromotion_settings_embed(self.guild)
            await self.message.edit(embed=e, view=self)

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

class AutopromotionChannelModal(discord.ui.Modal):
    channel_id = discord.ui.TextInput(label="Channel ID", placeholder="Enter the channel ID", required=True, max_length=20)
    def __init__(self, db, guild, update_callback, settings_cog, title="Set Autopromotion Watch Channel"):
        super().__init__(title=title)
        self.db = db
        self.guild = guild
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        cid = self.channel_id.value.strip()
        if not cid.isdigit():
            return await interaction.response.send_message("Channel ID must be numeric.", ephemeral=True)
        ch = self.guild.get_channel(int(cid))
        if not ch:
            return await interaction.response.send_message("Invalid channel ID.", ephemeral=True)

        await self.db.set_autopromotion_channel_id(self.guild.id, ch.id)
        await interaction.response.send_message(f"Autopromotion watch channel set to {ch.mention}.", ephemeral=True)
        await self.update_callback()

async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))