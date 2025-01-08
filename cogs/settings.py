import discord
from discord.ext import commands
from discord import app_commands
from enum import Enum
import traceback
import logging

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
        self.logger = bot.logger
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
        """Send an error response with better interaction handling"""
        try:
            embed = self.create_error_embed(title, description)
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                try:
                    await interaction.followup.send(embed=embed, ephemeral=True)
                except discord.HTTPException as e:
                    self.logger.error(f"Failed to send error followup: {e}")
        except Exception as e:
            self.logger.error(f"Failed to send error response: {e}")

    async def handle_exception(self, interaction: discord.Interaction, e: Exception, context: str = "handling settings"):
        self.logger.error("An error occurred while %s:", context)
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
        try:
            if not await self.is_admin_or_owner(interaction):
                return await self.send_error_response(
                    interaction,
                    "Missing Permissions",
                    "You need Administrator permission or be the bot owner."
                )

            try:
                await interaction.response.defer(ephemeral=True)
            except discord.NotFound:
                self.logger.error(f"Interaction not found when deferring response for category {category.value}")
                return
            except discord.HTTPException as e:
                self.logger.error(f"HTTP error when deferring response for category {category.value}: {e}")
                return

            handler = self.category_handlers.get(category.value)
            if not handler:
                return await interaction.followup.send(
                    embed=self.create_error_embed("Invalid Category", f"The category `{category.value}` is not recognized."),
                    ephemeral=True
                )

            try:
                await handler(interaction)
            except Exception as e:
                self.logger.error(f"Error in category handler for {category.value}:")
                traceback.print_exc()
                await self.handle_exception(interaction, e, context=f"processing {category.value} settings")

        except Exception as e:
            self.logger.error("Unexpected error in settings command:")
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        embed=self.create_error_embed("Error", f"An unexpected error occurred: {str(e)}"),
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        embed=self.create_error_embed("Error", f"An unexpected error occurred: {str(e)}"),
                        ephemeral=True
                    )
            except Exception as e2:
                self.logger.error(f"Failed to send error message: {e2}")

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
            self.logger.error("Error in handle_automod_settings:")
            traceback.print_exc()
            await self.send_error_response(interaction, "Error", f"Failed to load automod settings: {e}")

    async def handle_tryout_settings(self, interaction: discord.Interaction):
        try:
            embed = await self.create_tryout_settings_embed(interaction.guild)
            view = TryoutSettingsView(self.db, interaction.guild, self)
            view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            self.logger.error("Error in handle_tryout_settings:")
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
            self.logger.error("Error in handle_moderation_settings:")
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
            self.logger.error("Error in handle_autopromotion_settings:")
            traceback.print_exc()
            await self.send_error_response(
                interaction,
                "Error",
                f"Failed to load autopromotion settings: {e}"
            )

    def truncate_text(self, text: str, max_length: int = 1000) -> str:
        """Helper method to truncate text with ellipsis if too long"""
        return f"{text[:max_length-3]}..." if len(text) > max_length else text

    def chunk_list(self, items: list, chunk_size: int = 15) -> list:
        """Helper method to split a list into chunks"""
        return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]

    def format_role_list(self, roles: list, max_roles: int = 10) -> str:
        """Helper method to format a list of role mentions"""
        if not roles:
            return "❌ None set"
        
        roles_display = [f"<@&{r}>" for r in roles[:max_roles]]
        if len(roles) > max_roles:
            roles_display.append(f"and {len(roles) - max_roles} more...")
        return ", ".join(roles_display)

    def format_channel_list(self, channels: list, max_channels: int = 10) -> str:
        """Helper method to format a list of channel mentions"""
        if not channels:
            return "❌ None set"
        
        channels_display = [f"<#{c}>" for c in channels[:max_channels]]
        if len(channels) > max_channels:
            channels_display.append(f"and {len(channels) - max_channels} more...")
        return ", ".join(channels_display)

    async def create_moderation_settings_embed(self, guild: discord.Guild, page: int = 1) -> discord.Embed:
        settings = await self.db.get_server_settings(guild.id)
        
        embed = discord.Embed(
            title="⚙️ Moderation Settings",
            color=discord.Color.blue(),
            description=f"Page {page}/2 • Configure moderation settings below."
        )

        if page == 1:
            ch_id = settings.get('mod_log_channel_id')
            ch = f"<#{ch_id}>" if ch_id else "❌ Not Set"
            roles = await self.db.get_moderation_allowed_roles(guild.id)
            rd = self.format_role_list(roles)
            embed.add_field(name="📝 Log Channel", value=ch, inline=False)
            embed.add_field(name="👥 Allowed Roles", value=rd, inline=False)
        else:
            global_bans_enabled = settings.get('global_bans_enabled', True)
            status = "✅ Enabled" if global_bans_enabled else "❌ Disabled"
            embed.add_field(name="🌐 Global Ban System", value=status, inline=False)

        embed.set_footer(text="Use the buttons below to manage settings")
        return embed

    async def create_autopromotion_settings_embed(self, guild: discord.Guild) -> discord.Embed:
        ch_id = await self.db.get_autopromotion_channel_id(guild.id)
        ch = f"<#{ch_id}>" if ch_id else "❌ Not Set"
        embed = discord.Embed(
            title="⚙️ Autopromotion Settings",
            color=discord.Color.blue(),
            description="Configure autopromotion settings below."
        )
        embed.add_field(name="📝 Watch Channel", value=ch, inline=False)
        embed.set_footer(text="Use the buttons below to manage settings")
        return embed

    async def create_automod_settings_embed(self, s: dict, guild_id: int, page: int) -> discord.Embed:
        au_status = "✅ Enabled" if s.get('automod_enabled') else "❌ Disabled"
        lg_status = "✅ Enabled" if s.get('automod_logging_enabled') else "❌ Disabled"
        lg_ch = f"<#{s.get('automod_log_channel_id')}>" if s.get('automod_log_channel_id') else "❌ Not Set"
        mute = await self.db.get_automod_mute_duration(guild_id)
        prot = await self.db.get_protected_users(guild_id)
        exempts = await self.db.get_automod_exempt_roles(guild_id)
        # Fix the protected users formatting by using proper user mentions
        prot_display = "❌ None set" if not prot else ", ".join(f"<@{u}>" for u in prot)
        exempts_display = self.format_role_list(exempts)
        spam_limit = await self.db.get_automod_spam_limit(guild_id)
        spam_window = await self.db.get_automod_spam_window(guild_id)

        embed = discord.Embed(
            title="⚙️ Automod Settings",
            color=discord.Color.blue(),
            description=f"Page {page}/3 • Configure automod settings below."
        )
        
        if page == 1:
            embed.add_field(name="🤖 Automod Status", value=au_status, inline=True)
            embed.add_field(name="📝 Logging Status", value=lg_status, inline=True)
            embed.add_field(name="📌 Log Channel", value=lg_ch, inline=False)
        elif page == 2:
            embed.add_field(name="⏲️ Mute Duration", value=f"{mute} seconds", inline=True)
            embed.add_field(name="🛡️ Protected Users", value=prot_display, inline=False)
            embed.add_field(name="👥 Exempt Roles", value=exempts_display, inline=False)
        else:  # page 3
            embed.add_field(name="🔢 Spam Message Limit", value=str(spam_limit), inline=True)
            embed.add_field(name="⌛ Spam Time Window", value=f"{spam_window} seconds", inline=True)

        embed.set_footer(text="Use the buttons below to configure • Some lists may be truncated")
        return embed

    async def create_tryout_settings_embed(self, guild: discord.Guild) -> discord.Embed:
        ch_id = await self.db.get_tryout_channel_id(guild.id)
        ch = f"<#{ch_id}>" if ch_id else "❌ Not Set"
        req = await self.db.get_tryout_required_roles(guild.id)
        req_display = self.format_role_list(req)
        groups = await self.db.get_tryout_groups(guild.id)
        
        embed = discord.Embed(
            title="⚙️ Tryout Settings",
            color=discord.Color.blue(),
            description="Configure your tryout system settings below."
        )
        embed.add_field(name="📌 Tryout Channel", value=ch, inline=False)
        embed.add_field(name="👥 Required Roles", value=req_display, inline=False)
        
        if groups:
            # Split groups into chunks if needed
            group_chunks = []
            current_chunk = []
            current_length = 0
            
            for g in groups:
                # Format requirements with proper handling
                req_text = "None"
                if g[3]:
                    req_lines = [f"• {r}" for r in g[3][:3]]
                    if len(g[3]) > 3:
                        req_lines.append(f"• ... and {len(g[3]) - 3} more")
                    req_text = "\n".join(req_lines)

                # Format ping roles with proper handling
                roles_text = self.format_role_list(g[4], max_roles=5)

                # Create the group text with truncated description
                group_text = (
                    f"**🎯 {g[2]}** (ID: `{g[0]}`)\n"
                    f"📝 Description: {self.truncate_text(g[1], 100)}\n"
                    f"📋 Requirements:\n{req_text}\n"
                    f"🔔 Ping Roles: {roles_text}"
                )
                
                # Check if adding this group would exceed the limit
                if current_length + len(group_text) + 2 > 900:  # Leave more margin
                    group_chunks.append("\n\n".join(current_chunk))
                    current_chunk = [group_text]
                    current_length = len(group_text)
                else:
                    current_chunk.append(group_text)
                    current_length += len(group_text) + 2
            
            if current_chunk:
                group_chunks.append("\n\n".join(current_chunk))
            
            # Add group fields with proper chunking
            for i, chunk in enumerate(group_chunks):
                field_name = "🎯 Tryout Groups" if i == 0 else f"🎯 Tryout Groups (Part {i+1})"
                embed.add_field(name=field_name, value=chunk, inline=False)
        else:
            embed.add_field(name="🎯 Tryout Groups", value="❌ No groups configured.", inline=False)
        
        allowed_vcs = await self.db.get_tryout_allowed_vcs(guild.id)
        vc_display = self.format_channel_list(allowed_vcs)
        embed.add_field(name="🔊 Allowed Voice Channels", value=vc_display, inline=False)
        
        embed.set_footer(text="Use the buttons below to manage settings • Some content may be truncated")
        return embed

    @settings_command.error
    async def settings_error(self, interaction: discord.Interaction, error):
        """Enhanced error handling for settings command"""
        self.logger.error("Error in settings command:")
        traceback.print_exc()
        
        try:
            if isinstance(error, app_commands.MissingPermissions):
                await self.send_error_response(
                    interaction,
                    "Missing Permissions",
                    "You need Administrator permission or be the bot owner."
                )
            elif isinstance(error, discord.NotFound):
                self.logger.error(f"Interaction not found: {error}")
                # Don't try to respond as the interaction is invalid
                return
            elif isinstance(error, discord.HTTPException):
                self.logger.error(f"HTTP error in settings command: {error}")
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        embed=self.create_error_embed("Error", "Failed to process your request. Please try again."),
                        ephemeral=True
                    )
            else:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        embed=self.create_error_embed(
                            "Error",
                            f"An unexpected error occurred: {type(error).__name__}: {error}"
                        ),
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        embed=self.create_error_embed(
                            "Error",
                            f"An unexpected error occurred: {type(error).__name__}: {error}"
                        ),
                        ephemeral=True
                    )
        except Exception as e:
            self.logger.error(f"Failed to handle settings error: {e}")
            traceback.print_exc()


class BaseChannelModal(discord.ui.Modal):
    channel_id = discord.ui.TextInput(label="Channel ID", placeholder="Enter the channel ID", required=True, max_length=20)

    def __init__(self, db, guild, setting_name, update_callback, settings_cog, title="Set Channel"):
        # Ensure title doesn't exceed 45 chars
        title = title[:45] if len(title) > 45 else title
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
            self.logger.error("Error in BaseChannelModal on_submit:")
            traceback.print_exc()
            await interaction.response.send_message(
                embed=discord.Embed(title="Error", description=f"Failed to set the channel: {e}", color=0xE02B2B),
                ephemeral=True
            )

class BaseRoleManagementModal(discord.ui.Modal):
    action = discord.ui.TextInput(
        label="Action",
        placeholder="add/remove",
        required=True,
        max_length=6
    )
    role_ids = discord.ui.TextInput(
        label="Role IDs",
        placeholder="IDs separated by spaces",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
    )

    def __init__(self, db, guild, update_callback, add_method, remove_method, success_title, settings_cog):
        # Ensure title doesn't exceed 45 chars
        title = success_title[:45] if len(success_title) > 45 else success_title
        super().__init__(title=title)
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
            self.logger.error("Error in BaseRoleManagementModal on_submit:")
            traceback.print_exc()
            await interaction.response.send_message(
                embed=discord.Embed(title="Error", description=f"Failed to manage roles: {e}", color=0xE02B2B),
                ephemeral=True
            )

class BaseVCManagementModal(discord.ui.Modal):
    action = discord.ui.TextInput(
        label="Action",
        placeholder="add/remove",
        required=True,
        max_length=6
    )
    vc_ids = discord.ui.TextInput(
        label="Voice Channel IDs",
        placeholder="IDs separated by spaces",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
    )

    def __init__(self, db, guild, update_callback, add_method, remove_method, success_title, settings_cog):
        # Ensure title doesn't exceed 45 chars
        title = success_title[:45] if len(success_title) > 45 else success_title
        super().__init__(title=title)
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
            self.logger.error("Error in BaseVCManagementModal on_submit:")
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
        self.logger = logging.getLogger('discord_bot')
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
        try:
            selected_value = self.group_select.values[0]
            self.logger.debug(f"Group selection callback triggered with value: {selected_value}")
            
            try:
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
                    else:
                        self.logger.warning(f"Selected group {selected_value} not found in database")
                        await interaction.response.send_message(
                            embed=discord.Embed(
                                title="❌ Error",
                                description="The selected group could not be found. It may have been deleted.",
                                color=discord.Color.red()
                            ),
                            ephemeral=True
                        )
            except discord.NotFound:
                self.logger.error(f"Interaction not found when handling group selection: {selected_value}")
                return
            except discord.HTTPException as e:
                self.logger.error(f"HTTP error when handling group selection: {e}")
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="Failed to process your selection. Please try again.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
        except Exception as e:
            self.logger.error(f"Error in group selection callback: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ Error",
                        description=f"An unexpected error occurred: {str(e)}",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
            except Exception as e2:
                self.logger.error(f"Failed to send error message: {e2}")

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
            self.logger.error(f"Error creating group: {e}")
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
            try:
                self.group = await self.db.get_tryout_group(self.guild.id, self.group[0])
                if self.group:
                    embed = await self.settings_cog.create_tryout_settings_embed(self.guild)
                    try:
                        await self.message.edit(embed=embed, view=self)
                    except discord.NotFound:
                        # Message no longer exists, silently ignore
                        self.logger.debug("Could not update view: Message not found")
                    except discord.HTTPException as e:
                        self.logger.debug(f"Could not update view: {e}")
                await self.update_callback()
            except Exception as e:
                self.logger.debug(f"Error in update_view: {e}")

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
        try:
            # Try to delete the group
            try:
                await self.db.delete_tryout_group(self.guild.id, self.group[0])
                self.logger.debug(f"Successfully deleted group {self.group[0]} from database")
            except Exception as e:
                self.logger.error(f"Error deleting group {self.group[0]} from database: {e}")
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="Failed to delete the group. Please try again.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
                return

            # Create success embed
            embed = discord.Embed(
                title="✅ Group Deleted",
                description=f"Successfully deleted group: **{self.group[2]}**",
                color=discord.Color.green()
            )

            # Return to group selection with proper error handling
            try:
                view = TryoutGroupSelectView(self.db, self.guild, self.settings_cog)
                await view.update_group_options()
                await interaction.response.edit_message(embed=embed, view=view)
                view.message = interaction.message
                
                # Update callback with error handling
                try:
                    await self.update_callback()
                except Exception as e:
                    self.logger.debug(f"Error in update callback after group deletion: {e}")
                    # Don't raise the error since the deletion was successful
            
            except discord.NotFound:
                self.logger.debug("Could not edit original message after group deletion - message not found")
                # Try to send a new message instead
                try:
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            title="✅ Group Deleted",
                            description="The group was deleted successfully. Please reopen the settings to see the changes.",
                            color=discord.Color.green()
                        ),
                        ephemeral=True
                    )
                except discord.InteractionResponded:
                    try:
                        await interaction.followup.send(
                            embed=discord.Embed(
                                title="✅ Group Deleted",
                                description="The group was deleted successfully. Please reopen the settings to see the changes.",
                                color=discord.Color.green()
                            ),
                            ephemeral=True
                        )
                    except Exception as e:
                        self.logger.debug(f"Could not send followup message after group deletion: {e}")
            
            except Exception as e:
                self.logger.error(f"Error updating view after group deletion: {e}")
                # Try to send an error message
                try:
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            title="⚠️ Partial Success",
                            description="The group was deleted but there was an error updating the view. Please reopen the settings.",
                            color=discord.Color.yellow()
                        ),
                        ephemeral=True
                    )
                except discord.InteractionResponded:
                    try:
                        await interaction.followup.send(
                            embed=discord.Embed(
                                title="⚠️ Partial Success",
                                description="The group was deleted but there was an error updating the view. Please reopen the settings.",
                                color=discord.Color.yellow()
                            ),
                            ephemeral=True
                        )
                    except Exception as e:
                        self.logger.debug(f"Could not send error message after group deletion: {e}")

        except Exception as e:
            self.logger.error(f"Unexpected error in delete confirmation: {e}")
            # Try to send an error message
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="An unexpected error occurred. Please try again.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
            except discord.InteractionResponded:
                try:
                    await interaction.followup.send(
                        embed=discord.Embed(
                            title="❌ Error",
                            description="An unexpected error occurred. Please try again.",
                            color=discord.Color.red()
                        ),
                        ephemeral=True
                    )
                except Exception as e:
                    self.logger.debug(f"Could not send error message: {e}")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel_btn(self, interaction: discord.Interaction, _):
        try:
            # Return to group management with error handling
            view = GroupManagementView(self.db, self.guild, self.group, self.update_callback, self.settings_cog)
            embed = await view.create_group_embed()
            
            try:
                await interaction.response.edit_message(embed=embed, view=view)
                view.message = interaction.message
            except discord.NotFound:
                self.logger.debug("Could not edit original message when canceling deletion - message not found")
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⚠️ Navigation Error",
                        description="Could not return to the previous view. Please reopen the settings.",
                        color=discord.Color.yellow()
                    ),
                    ephemeral=True
                )
            except Exception as e:
                self.logger.error(f"Error returning to group management view: {e}")
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⚠️ Navigation Error",
                        description="Could not return to the previous view. Please reopen the settings.",
                        color=discord.Color.yellow()
                    ),
                    ephemeral=True
                )
        
        except Exception as e:
            self.logger.error(f"Unexpected error in cancel button: {e}")
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="An unexpected error occurred. Please reopen the settings.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
            except discord.InteractionResponded:
                try:
                    await interaction.followup.send(
                        embed=discord.Embed(
                            title="❌ Error",
                            description="An unexpected error occurred. Please reopen the settings.",
                            color=discord.Color.red()
                        ),
                        ephemeral=True
                    )
                except Exception as e:
                    self.logger.debug(f"Could not send error message: {e}")

    async def on_timeout(self):
        try:
            for child in self.children:
                child.disabled = True
            
            # Try to update the view with disabled buttons
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                self.logger.debug("Could not disable buttons on timeout - message not found")
            except Exception as e:
                self.logger.debug(f"Error disabling buttons on timeout: {e}")
        except Exception as e:
            self.logger.debug(f"Unexpected error in timeout handler: {e}")

class EditGroupNameModal(discord.ui.Modal):
    name = discord.ui.TextInput(
        label="Event Name",
        placeholder="Enter new event name",
        required=True,
        max_length=100
    )

    def __init__(self, db, guild, group, update_callback, settings_cog):
        # Truncate group name to ensure title doesn't exceed 45 chars
        group_name = group[2][:20] + "..." if len(group[2]) > 20 else group[2]
        super().__init__(title=f"Edit Group Name - {group_name}")
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
        # Truncate group name to ensure title doesn't exceed 45 chars
        group_name = group[2][:20] + "..." if len(group[2]) > 20 else group[2]
        super().__init__(title=f"Edit Description - {group_name}")
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
        # Truncate group name to ensure title doesn't exceed 45 chars
        group_name = group[2][:20] + "..." if len(group[2]) > 20 else group[2]
        super().__init__(title=f"Edit Requirements - {group_name}")
        self.db = db
        self.guild = guild
        self.group = group
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            reqs = [r.strip() for r in self.requirements.value.strip().split('\n') if r.strip()]
            await self.db.update_tryout_group(
                self.guild.id,
                self.group[0],
                self.group[1],
                self.group[2],
                reqs
            )

            try:
                # Try to update the view first
                updated_group = await self.db.get_tryout_group(self.guild.id, self.group[0])
                if updated_group:
                    view = GroupManagementView(self.db, self.guild, updated_group, self.update_callback, self.settings_cog)
                    embed = await view.create_group_embed()
                    await interaction.response.edit_message(embed=embed, view=view)
                    view.message = interaction.message

                    # Send success message as followup
                    await interaction.followup.send(
                        embed=discord.Embed(
                            title="✅ Requirements Updated",
                            description=f"Successfully updated requirements for **{updated_group[2]}**",
                            color=discord.Color.green()
                        ),
                        ephemeral=True
                    )
                    
                    # Update the settings view
                    await self.update_callback()

            except discord.NotFound:
                # If the original message is gone, send a new response
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="✅ Requirements Updated",
                        description="The requirements were updated, but the view could not be refreshed. Please reopen the settings.",
                        color=discord.Color.yellow()
                    ),
                    ephemeral=True
                )
            except discord.InteractionResponded:
                # If we've already responded, try to send a followup
                try:
                    await interaction.followup.send(
                        embed=discord.Embed(
                            title="✅ Requirements Updated",
                            description="The requirements were updated successfully.",
                            color=discord.Color.green()
                        ),
                        ephemeral=True
                    )
                except Exception as e:
                    self.logger.debug(f"Could not send followup: {e}")

        except Exception as e:
            self.logger.debug(f"Error in requirements modal: {e}")
            # Try to send an error message if we haven't responded yet
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="An error occurred while updating the requirements. Please try again.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
            except discord.InteractionResponded:
                try:
                    await interaction.followup.send(
                        embed=discord.Embed(
                            title="❌ Error",
                            description="An error occurred while updating the requirements. Please try again.",
                            color=discord.Color.red()
                        ),
                        ephemeral=True
                    )
                except Exception as e:
                    self.logger.debug(f"Could not send error message: {e}")

class EditGroupPingRolesModal(discord.ui.Modal):
    roles = discord.ui.TextInput(
        label="Ping Roles",
        placeholder="Enter role IDs separated by spaces",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
    )

    def __init__(self, db, guild, group, update_callback, settings_cog):
        # Truncate group name to ensure title doesn't exceed 45 chars
        group_name = group[2][:20] + "..." if len(group[2]) > 20 else group[2]
        super().__init__(title=f"Edit Ping Roles - {group_name}")
        self.db = db
        self.guild = guild
        self.group = group
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Remove existing roles
            for role_id in self.group[4]:
                try:
                    await self.db.remove_group_ping_role(self.guild.id, self.group[0], int(role_id))
                except Exception as e:
                    self.logger.debug(f"Error removing role {role_id}: {e}")

            # Add new roles
            valid_roles = []
            invalid_roles = []
            for role_id in self.roles.value.strip().split():
                role_id = role_id.strip()
                if role_id.isdigit():
                    role = self.guild.get_role(int(role_id))
                    if role:
                        try:
                            await self.db.add_group_ping_role(self.guild.id, self.group[0], role.id)
                            valid_roles.append(role.id)
                        except Exception as e:
                            self.logger.debug(f"Error adding role {role_id}: {e}")
                            invalid_roles.append(role_id)
                    else:
                        invalid_roles.append(role_id)
                elif role_id:  # Only add to invalid if it's not empty
                    invalid_roles.append(role_id)

            if invalid_roles:
                return await interaction.response.send_message(
                    f"Invalid role IDs: {', '.join(invalid_roles)}",
                    ephemeral=True
                )

            try:
                # Get updated group data
                updated_group = await self.db.get_tryout_group(self.guild.id, self.group[0])
                if updated_group:
                    # Update the group management view
                    view = GroupManagementView(self.db, self.guild, updated_group, self.update_callback, self.settings_cog)
                    embed = await view.create_group_embed()
                    
                    try:
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
                    except discord.NotFound:
                        # If the original message is gone, send a new response
                        await interaction.response.send_message(
                            embed=discord.Embed(
                                title="✅ Roles Updated",
                                description="The roles were updated, but the view could not be refreshed. Please reopen the settings.",
                                color=discord.Color.yellow()
                            ),
                            ephemeral=True
                        )
                    except discord.InteractionResponded:
                        # If we've already responded, try to send a followup
                        try:
                            await interaction.followup.send(
                                embed=discord.Embed(
                                    title="✅ Roles Updated",
                                    description="The roles were updated successfully.",
                                    color=discord.Color.green()
                                ),
                                ephemeral=True
                            )
                        except Exception as e:
                            self.logger.debug(f"Could not send followup: {e}")

            except Exception as e:
                self.logger.debug(f"Error updating view after role changes: {e}")
                # Try to send an error message if we haven't responded yet
                try:
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            title="⚠️ Partial Update",
                            description="The roles were updated but there was an error refreshing the view. Please reopen the settings.",
                            color=discord.Color.yellow()
                        ),
                        ephemeral=True
                    )
                except discord.InteractionResponded:
                    try:
                        await interaction.followup.send(
                            embed=discord.Embed(
                                title="⚠️ Partial Update",
                                description="The roles were updated but there was an error refreshing the view. Please reopen the settings.",
                                color=discord.Color.yellow()
                            ),
                            ephemeral=True
                        )
                    except Exception as e:
                        self.logger.debug(f"Could not send error message: {e}")

        except Exception as e:
            self.logger.debug(f"Error in ping roles modal: {e}")
            # Try to send an error message if we haven't responded yet
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="An error occurred while updating the roles. Please try again.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
            except discord.InteractionResponded:
                try:
                    await interaction.followup.send(
                        embed=discord.Embed(
                            title="❌ Error",
                            description="An error occurred while updating the roles. Please try again.",
                            color=discord.Color.red()
                        ),
                        ephemeral=True
                    )
                except Exception as e:
                    self.logger.debug(f"Could not send error message: {e}")

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
            try:
                self.group = await self.db.get_tryout_group(self.guild.id, self.group[0])
                if self.group:
                    embed = await self.settings_cog.create_tryout_settings_embed(self.guild)
                    try:
                        await self.message.edit(embed=embed, view=self)
                    except discord.NotFound:
                        # Message no longer exists, silently ignore
                        self.logger.debug("Could not update view: Message not found")
                    except discord.HTTPException as e:
                        self.logger.debug(f"Could not update view: {e}")
                await self.update_callback()
            except Exception as e:
                self.logger.debug(f"Error in update_view: {e}")

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
        # Ensure title doesn't exceed 45 chars
        title = title[:45] if len(title) > 45 else title
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

class ModerationSettingsView(discord.ui.View):
    def __init__(self, db, guild, settings_cog):
        super().__init__(timeout=180)
        self.db = db
        self.guild = guild
        self.settings_cog = settings_cog
        self.bot = settings_cog.bot  # Add bot reference
        self.logger = settings_cog.logger  # Add logger reference
        self.message = None
        self.page = 1
        self.setup_buttons()

    def setup_buttons(self):
        self.clear_items()
        
        if self.page == 1:
            # General Settings
            set_log = discord.ui.Button(label="Set Log Channel", style=discord.ButtonStyle.primary, emoji="📌", row=0)
            set_log.callback = self.set_log_channel_btn
            self.add_item(set_log)

            manage_roles = discord.ui.Button(label="Manage Allowed Roles", style=discord.ButtonStyle.primary, emoji="👥", row=0)
            manage_roles.callback = self.manage_allowed_roles_btn
            self.add_item(manage_roles)
        
        elif self.page == 2:
            # Global Ban Settings
            toggle_global = discord.ui.Button(label="Toggle Global Bans", style=discord.ButtonStyle.primary, emoji="🌐", row=0)
            toggle_global.callback = self.toggle_global_bans_btn
            self.add_item(toggle_global)

        # Navigation
        prev_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary, emoji="◀️", row=1, disabled=(self.page <= 1))
        prev_button.callback = self.prev_page_btn
        self.add_item(prev_button)

        next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary, emoji="▶️", row=1, disabled=(self.page >= 2))
        next_button.callback = self.next_page_btn
        self.add_item(next_button)

    async def set_log_channel_btn(self, interaction: discord.Interaction):
        if self.message:
            await interaction.response.send_modal(BaseChannelModal(
                db=self.db,
                guild=self.guild,
                setting_name='mod_log_channel_id',
                update_callback=self.async_update_view,
                settings_cog=self.settings_cog,
                title="Set Moderation Log Channel"
            ))

    async def manage_allowed_roles_btn(self, interaction: discord.Interaction):
        if self.message:
            await interaction.response.send_modal(BaseRoleManagementModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.async_update_view,
                add_method=self.db.add_moderation_allowed_role,
                remove_method=self.db.remove_moderation_allowed_role,
                success_title="Moderation Roles Updated",
                settings_cog=self.settings_cog
            ))

    async def toggle_global_bans_btn(self, interaction: discord.Interaction):
        """Toggle global bans and sync if enabled"""
        try:
            settings = await self.db.get_server_settings(self.guild.id)
            current = settings.get('global_bans_enabled', False)
            await self.db.update_server_setting(self.guild.id, 'global_bans_enabled', not current)
            
            # If enabling global bans, sync existing bans
            if not current:  # If it was disabled and now being enabled
                await interaction.response.defer(thinking=True, ephemeral=True)
                moderation_cog = self.bot.get_cog('moderation')  # Note: lowercase 'moderation'
                if moderation_cog:
                    await moderation_cog.sync_global_bans_for_guild(self.guild)
                    await self.async_update_view()
                    await interaction.followup.send("✅ Global bans enabled and synchronized", ephemeral=True)
                else:
                    await interaction.followup.send("❌ Could not sync global bans: Moderation module not loaded", ephemeral=True)
            else:
                await interaction.response.defer(ephemeral=True)
                await self.async_update_view()
                await interaction.followup.send("✅ Global bans disabled", ephemeral=True)
                
        except Exception as e:
            error_msg = f"Error toggling global bans: {str(e)}"
            self.logger.error(error_msg)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ " + error_msg, ephemeral=True)
                else:
                    await interaction.followup.send("❌ " + error_msg, ephemeral=True)
            except Exception as e2:
                self.logger.error(f"Failed to send error message: {e2}")

    async def prev_page_btn(self, interaction: discord.Interaction):
        if self.page > 1:
            self.page -= 1
            self.setup_buttons()
            await self.async_update_view()
            await interaction.response.defer()

    async def next_page_btn(self, interaction: discord.Interaction):
        if self.page < 2:
            self.page += 1
            self.setup_buttons()
            await self.async_update_view()
            await interaction.response.defer()

    async def async_update_view(self):
        if self.message:
            try:
                embed = await self.settings_cog.create_moderation_settings_embed(self.guild, self.page)
                try:
                    await self.message.edit(embed=embed, view=self)
                except discord.NotFound:
                    self.logger.debug("Could not update view: Message not found")
                except discord.HTTPException as e:
                    self.logger.debug(f"Could not update view: {e}")
            except Exception as e:
                self.logger.debug(f"Error in update_view: {e}")

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

class AutomodSettingsView(discord.ui.View):
    def __init__(self, db, guild, settings_cog, page=1):
        super().__init__(timeout=180)
        self.db = db
        self.guild = guild
        self.settings_cog = settings_cog
        self.page = page
        self.message = None
        self.setup_buttons()

    def setup_buttons(self):
        # Page 1 buttons - General Settings
        if self.page == 1:
            toggle_automod = discord.ui.Button(label="Toggle Automod", style=discord.ButtonStyle.primary, emoji="🔄", row=0)
            toggle_automod.callback = self.toggle_automod_btn
            self.add_item(toggle_automod)

            toggle_logging = discord.ui.Button(label="Toggle Logging", style=discord.ButtonStyle.primary, emoji="📝", row=0)
            toggle_logging.callback = self.toggle_logging_btn
            self.add_item(toggle_logging)

            set_log_channel = discord.ui.Button(label="Set Log Channel", style=discord.ButtonStyle.primary, emoji="📌", row=0)
            set_log_channel.callback = self.set_log_channel_btn
            self.add_item(set_log_channel)

        # Page 2 buttons - User Management
        elif self.page == 2:
            mute_duration = discord.ui.Button(label="Set Mute Duration", style=discord.ButtonStyle.primary, emoji="⏲️", row=0)
            mute_duration.callback = self.set_mute_duration_btn
            self.add_item(mute_duration)

            protected_users = discord.ui.Button(label="Manage Protected Users", style=discord.ButtonStyle.primary, emoji="🛡️", row=0)
            protected_users.callback = self.manage_protected_users_btn
            self.add_item(protected_users)

            exempt_roles = discord.ui.Button(label="Manage Exempt Roles", style=discord.ButtonStyle.primary, emoji="👥", row=0)
            exempt_roles.callback = self.manage_exempt_roles_btn
            self.add_item(exempt_roles)

        # Page 3 buttons - Spam Settings
        elif self.page == 3:
            spam_limit = discord.ui.Button(label="Set Spam Limit", style=discord.ButtonStyle.primary, emoji="🔢", row=0)
            spam_limit.callback = self.set_spam_limit_btn
            self.add_item(spam_limit)

            spam_window = discord.ui.Button(label="Set Spam Window", style=discord.ButtonStyle.primary, emoji="⌛", row=0)
            spam_window.callback = self.set_spam_window_btn
            self.add_item(spam_window)

        # Navigation buttons (always show)
        prev_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary, emoji="◀️", row=1, disabled=(self.page <= 1))
        prev_button.callback = self.prev_page_btn
        self.add_item(prev_button)

        next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary, emoji="▶️", row=1, disabled=(self.page >= 3))
        next_button.callback = self.next_page_btn
        self.add_item(next_button)

    async def toggle_automod_btn(self, interaction: discord.Interaction):
        if self.message:
            settings = await self.db.get_server_settings(self.guild.id)
            current = settings.get('automod_enabled', False)
            await self.db.update_server_setting(self.guild.id, 'automod_enabled', not current)
            await self.async_update_view()
            await interaction.response.send_message(
                f"Automod {'disabled' if current else 'enabled'}.",
                ephemeral=True
            )

    async def toggle_logging_btn(self, interaction: discord.Interaction):
        if self.message:
            settings = await self.db.get_server_settings(self.guild.id)
            current = settings.get('automod_logging_enabled', False)
            await self.db.update_server_setting(self.guild.id, 'automod_logging_enabled', not current)
            await self.async_update_view()
            await interaction.response.send_message(
                f"Automod logging {'disabled' if current else 'enabled'}.",
                ephemeral=True
            )

    async def set_log_channel_btn(self, interaction: discord.Interaction):
        if self.message:
            await interaction.response.send_modal(BaseChannelModal(
                db=self.db,
                guild=self.guild,
                setting_name='automod_log_channel_id',
                update_callback=self.async_update_view,
                settings_cog=self.settings_cog,
                title="Set Automod Log Channel"
            ))

    async def set_mute_duration_btn(self, interaction: discord.Interaction):
        if self.message:
            await interaction.response.send_modal(AutomodMuteDurationModal(
                self.db,
                self.guild,
                self.async_update_view,
                self.settings_cog
            ))

    async def manage_protected_users_btn(self, interaction: discord.Interaction):
        if self.message:
            await interaction.response.send_modal(AutomodProtectedUsersModal(
                self.db,
                self.guild,
                self.async_update_view,
                self.settings_cog
            ))

    async def manage_exempt_roles_btn(self, interaction: discord.Interaction):
        if self.message:
            await interaction.response.send_modal(BaseRoleManagementModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.async_update_view,
                add_method=self.db.add_automod_exempt_role,
                remove_method=self.db.remove_automod_exempt_role,
                success_title="Exempt Roles Updated",
                settings_cog=self.settings_cog
            ))

    async def set_spam_limit_btn(self, interaction: discord.Interaction):
        if self.message:
            await interaction.response.send_modal(AutomodSpamLimitModal(
                self.db,
                self.guild,
                self.async_update_view,
                self.settings_cog
            ))

    async def set_spam_window_btn(self, interaction: discord.Interaction):
        if self.message:
            await interaction.response.send_modal(AutomodSpamWindowModal(
                self.db,
                self.guild,
                self.async_update_view,
                self.settings_cog
            ))

    async def prev_page_btn(self, interaction: discord.Interaction):
        if self.page > 1:
            self.page -= 1
            self.clear_items()  # Remove all current buttons
            self.setup_buttons()  # Add buttons for the new page
            await self.async_update_view()
            await interaction.response.defer()

    async def next_page_btn(self, interaction: discord.Interaction):
        if self.page < 3:
            self.page += 1
            self.clear_items()  # Remove all current buttons
            self.setup_buttons()  # Add buttons for the new page
            await self.async_update_view()
            await interaction.response.defer()

    async def async_update_view(self):
        if self.message:
            try:
                settings = await self.db.get_server_settings(self.guild.id)
                embed = await self.settings_cog.create_automod_settings_embed(settings, self.guild.id, self.page)
                
                try:
                    await self.message.edit(embed=embed, view=self)
                except discord.NotFound:
                    self.logger.debug("Could not update view: Message not found")
                except discord.HTTPException as e:
                    self.logger.debug(f"Could not update view: {e}")
            except Exception as e:
                self.logger.debug(f"Error in update_view: {e}")

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

class AutomodMuteDurationModal(discord.ui.Modal):
    duration = discord.ui.TextInput(
        label="Mute Duration (seconds)",
        placeholder="Enter duration in seconds (e.g., 300)",
        required=True,
        max_length=10
    )

    def __init__(self, db, guild, update_callback, settings_cog):
        super().__init__(title="Set Automod Mute Duration")
        self.db = db
        self.guild = guild
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            duration = int(self.duration.value.strip())
            if duration < 0:
                raise ValueError("Duration must be positive")
            
            await self.db.set_automod_mute_duration(self.guild.id, duration)
            await interaction.response.send_message(
                f"Mute duration set to {duration} seconds.",
                ephemeral=True
            )
            await self.update_callback()
        except ValueError as e:
            await interaction.response.send_message(
                f"Invalid duration: {str(e)}",
                ephemeral=True
            )

class AutomodProtectedUsersModal(discord.ui.Modal):
    action = discord.ui.TextInput(
        label="Action",
        placeholder="add/remove",
        required=True,
        max_length=6
    )
    user_ids = discord.ui.TextInput(
        label="User IDs",
        placeholder="Enter user IDs separated by spaces",
        required=True,
        style=discord.TextStyle.paragraph
    )

    def __init__(self, db, guild, update_callback, settings_cog):
        super().__init__(title="Manage Protected Users")
        self.db = db
        self.guild = guild
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        action = self.action.value.strip().lower()
        if action not in ['add', 'remove']:
            return await interaction.response.send_message(
                "Invalid action. Use 'add' or 'remove'.",
                ephemeral=True
            )

        user_ids = [x.strip() for x in self.user_ids.value.split() if x.strip()]
        if not user_ids:
            return await interaction.response.send_message(
                "No user IDs provided.",
                ephemeral=True
            )

        valid_ids = []
        invalid_ids = []
        for uid in user_ids:
            if uid.isdigit():
                try:
                    user = await self.guild.fetch_member(int(uid))
                    if user:
                        valid_ids.append(int(uid))
                    else:
                        invalid_ids.append(uid)
                except:
                    invalid_ids.append(uid)
            else:
                invalid_ids.append(uid)

        if invalid_ids:
            return await interaction.response.send_message(
                f"Invalid user IDs: {', '.join(invalid_ids)}",
                ephemeral=True
            )

        try:
            for uid in valid_ids:
                if action == 'add':
                    await self.db.add_protected_user(self.guild.id, uid)
                else:
                    await self.db.remove_protected_user(self.guild.id, uid)

            users_str = ", ".join(f"<@{uid}>" for uid in valid_ids)
            await interaction.response.send_message(
                f"Successfully {action}ed users: {users_str}",
                ephemeral=True
            )
            await self.update_callback()
        except Exception as e:
            await interaction.response.send_message(
                f"Error managing protected users: {str(e)}",
                ephemeral=True
            )

class AutomodSpamLimitModal(discord.ui.Modal):
    limit = discord.ui.TextInput(
        label="Message Limit",
        placeholder="Enter max messages allowed (e.g., 5)",
        required=True,
        max_length=5
    )

    def __init__(self, db, guild, update_callback, settings_cog):
        super().__init__(title="Set Spam Message Limit")
        self.db = db
        self.guild = guild
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = int(self.limit.value.strip())
            if limit < 1:
                raise ValueError("Limit must be at least 1")
            
            await self.db.set_automod_spam_limit(self.guild.id, limit)
            await interaction.response.send_message(
                f"Spam message limit set to {limit}.",
                ephemeral=True
            )
            await self.update_callback()
        except ValueError as e:
            await interaction.response.send_message(
                f"Invalid limit: {str(e)}",
                ephemeral=True
            )

class AutomodSpamWindowModal(discord.ui.Modal):
    window = discord.ui.TextInput(
        label="Time Window (seconds)",
        placeholder="Enter time window in seconds (e.g., 10)",
        required=True,
        max_length=5
    )

    def __init__(self, db, guild, update_callback, settings_cog):
        super().__init__(title="Set Spam Time Window")
        self.db = db
        self.guild = guild
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            window = int(self.window.value.strip())
            if window < 1:
                raise ValueError("Window must be at least 1 second")
            
            await self.db.set_automod_spam_window(self.guild.id, window)
            await interaction.response.send_message(
                f"Spam time window set to {window} seconds.",
                ephemeral=True
            )
            await self.update_callback()
        except ValueError as e:
            await interaction.response.send_message(
                f"Invalid window: {str(e)}",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))