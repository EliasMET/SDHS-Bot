import discord
from discord.ext import commands
from discord import app_commands
from enum import Enum

class SettingsCategory(Enum):
    AUTOMOD = "automod"
    TRYOUT = "tryout"
    MODERATION = "moderation"

class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = None
        self.owner_id = None
        self.category_handlers = {
            SettingsCategory.AUTOMOD.value: self.handle_automod_settings,
            SettingsCategory.TRYOUT.value: self.handle_tryout_settings,
            SettingsCategory.MODERATION.value: self.handle_moderation_settings
        }

    async def cog_load(self):
        self.db = self.bot.database
        if not self.db:
            raise ValueError("DatabaseManager is not initialized.")
        self.owner_id = (await self.bot.application_info()).owner.id

    async def is_admin_or_owner(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id or (interaction.guild and interaction.user.guild_permissions.administrator)

    @app_commands.command(name="settings", description="Configure bot settings.")
    @app_commands.choices(category=[
        app_commands.Choice(name="Automod", value=SettingsCategory.AUTOMOD.value),
        app_commands.Choice(name="Tryout", value=SettingsCategory.TRYOUT.value),
        app_commands.Choice(name="Moderation", value=SettingsCategory.MODERATION.value)
    ])
    async def settings_command(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        if not await self.is_admin_or_owner(interaction):
            return await interaction.response.send_message(
                embed=discord.Embed(
                    title="Missing Permissions",
                    description="You need Administrator permission or be the bot owner.",
                    color=0xE02B2B
                ),
                ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        handler = self.category_handlers.get(category.value)
        if handler:
            await handler(interaction)
        else:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Invalid Category",
                    description=f"The category `{category.value}` is not recognized.",
                    color=0xE02B2B
                ),
                ephemeral=True
            )

    async def handle_automod_settings(self, interaction: discord.Interaction):
        settings = await self.db.get_server_settings(interaction.guild.id)
        if not settings:
            await self.db.initialize_server_settings(interaction.guild.id)
            settings = await self.db.get_server_settings(interaction.guild.id)
        embed = await self.create_automod_settings_embed(settings, interaction.guild.id, page=1)
        view = AutomodSettingsView(self.db, interaction.guild, self, page=1)
        view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def handle_tryout_settings(self, interaction: discord.Interaction):
        embed = await self.create_tryout_settings_embed(interaction.guild)
        view = TryoutSettingsView(self.db, interaction.guild, self)
        view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def handle_moderation_settings(self, interaction: discord.Interaction):
        embed = await self.create_moderation_settings_embed(interaction.guild)
        view = ModerationSettingsView(self.db, interaction.guild, self)
        view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def create_automod_settings_embed(self, s, gid: int, page: int):
        au_status = "✅ Enabled" if s.get('automod_enabled') else "❌ Disabled"
        lg_status = "✅ Enabled" if s.get('automod_logging_enabled') else "❌ Disabled"
        lg_ch = f"<#{s.get('automod_log_channel_id')}>" if s.get('automod_log_channel_id') else "Not Set"
        mute = await self.db.get_automod_mute_duration(gid)
        prot = await self.db.get_protected_users(gid)
        exempts = await self.db.get_exempt_roles(gid)
        prot_display = ", ".join(f"<@{u}>" for u in prot) if prot else "None"
        exempts_display = ", ".join(f"<@&{r}>" for r in exempts) if exempts else "None"
        e = discord.Embed(title="⚙️ Automod Settings", color=discord.Color.blue(), description=f"Page {page}/2")
        e.set_footer(text="Use the buttons below to configure settings or navigate.")
        if page == 1:
            e.add_field(name="Automod Status", value=au_status, inline=True)
            e.add_field(name="Logging Status", value=lg_status, inline=True)
            e.add_field(name="Log Channel", value=lg_ch, inline=False)
        else:
            e.add_field(name="Mute Duration (seconds)", value=str(mute), inline=True)
            e.add_field(name="Protected Users", value=prot_display, inline=False)
            e.add_field(name="Exempt Roles", value=exempts_display, inline=False)
        return e

    async def create_tryout_settings_embed(self, guild):
        ch_id = await self.db.get_tryout_channel_id(guild.id)
        ch = f"<#{ch_id}>" if ch_id else "Not Set"
        req = await self.db.get_tryout_required_roles(guild.id)
        req_display = ", ".join(f"<@&{r}>" for r in req) if req else "Not Set"
        groups = await self.db.get_tryout_groups(guild.id)
        grp_display = "\n".join(f"**{g[3]}** (ID: {g[0]})" for g in groups) if groups else "No groups."
        ping = await self.db.get_ping_roles(guild.id)
        ping_display = ", ".join(f"<@&{r}>" for r in ping) if ping else "No roles set."
        e = discord.Embed(title="⚙️ Tryout Settings", color=discord.Color.blue())
        e.add_field(name="Tryout Channel", value=ch, inline=False)
        e.add_field(name="Required Roles", value=req_display, inline=False)
        e.add_field(name="Tryout Groups", value=grp_display, inline=False)
        e.add_field(name="Ping Roles", value=ping_display, inline=False)
        return e

    async def create_moderation_settings_embed(self, guild):
        s = await self.db.get_server_settings(guild.id)
        ch_id = s.get('mod_log_channel_id')
        ch = f"<#{ch_id}>" if ch_id else "Not Set"
        roles = await self.db.get_moderation_allowed_roles(guild.id)
        rd = ", ".join(f"<@&{r}>" for r in roles) if roles else "No roles set."
        e = discord.Embed(title="⚙️ Moderation Settings", color=discord.Color.blue())
        e.add_field(name="Moderation Log Channel", value=ch, inline=False)
        e.add_field(name="Allowed Roles", value=rd, inline=False)
        return e

    @settings_command.error
    async def settings_error(self, interaction: discord.Interaction, error):
        e = discord.Embed(color=0xE02B2B)
        if isinstance(error, app_commands.MissingPermissions):
            e.title = "Missing Permissions"
            e.description = "You need Administrator permission or be the bot owner."
        else:
            e.title = "Error"
            e.description = "An unexpected error occurred."
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=e, ephemeral=True)
        else:
            await interaction.followup.send(embed=e, ephemeral=True)

class BaseChannelModal(discord.ui.Modal):
    channel_id = discord.ui.TextInput(label="Channel ID", placeholder="Enter the channel ID", required=True, max_length=20)
    def __init__(self, db, guild, setting_name, update_callback, settings_cog, title="Set Channel"):
        super().__init__(title=title)
        self.db, self.guild, self.setting_name = db, guild, setting_name
        self.update_callback, self.settings_cog = update_callback, settings_cog

    async def validate_channel(self, cid):
        if not cid.isdigit():
            return None, "Channel ID must be numeric."
        ch = self.guild.get_channel(int(cid))
        return (ch, None) if ch else (None, "Invalid channel ID.")

    async def on_submit(self, interaction: discord.Interaction):
        ch, err = await self.validate_channel(self.channel_id.value.strip())
        if err:
            return await interaction.response.send_message(
                embed=discord.Embed(title="Invalid Channel ID", description=err, color=0xE02B2B),
                ephemeral=True
            )
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
        except:
            await interaction.response.send_message(
                embed=discord.Embed(title="Error", description="Failed to set the channel.", color=0xE02B2B),
                ephemeral=True
            )

class BaseRoleManagementModal(discord.ui.Modal):
    action = discord.ui.TextInput(label="Action", placeholder="add/remove", required=True, max_length=6)
    role_ids = discord.ui.TextInput(label="Role/User IDs", placeholder="IDs separated by spaces", required=True, style=discord.TextStyle.paragraph, max_length=2000)
    def __init__(self, db, guild, update_callback, add_method, remove_method, success_title, settings_cog):
        super().__init__(title=success_title)
        self.db, self.guild = db, guild
        self.update_callback, self.add_method, self.remove_method = update_callback, add_method, remove_method
        self.success_title, self.settings_cog = success_title, settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        act = self.action.value.strip().lower()
        if act not in ['add','remove']:
            return await interaction.response.send_message(
                embed=discord.Embed(title="Invalid Action", description="Use 'add' or 'remove'.", color=0xE02B2B),
                ephemeral=True
            )
        ids = [x for x in self.role_ids.value.strip().split() if x.strip()]
        if not ids:
            return await interaction.response.send_message(
                embed=discord.Embed(title="No IDs Provided", description="Provide at least one ID.", color=0xE02B2B),
                ephemeral=True
            )
        valid, invalid = [], []
        for rid in ids:
            if rid.isdigit():
                r = self.guild.get_role(int(rid))
                valid.append(r.id if r else invalid.append(rid))
            else:
                invalid.append(rid)
        if invalid:
            return await interaction.response.send_message(
                embed=discord.Embed(title="Invalid IDs", description=", ".join(invalid), color=0xE02B2B),
                ephemeral=True
            )
        try:
            m = self.add_method if act=='add' else self.remove_method
            for v in valid:
                await m(self.guild.id, v)
            md = ", ".join(f"<@&{v}>" for v in valid)
            await interaction.response.send_message(
                embed=discord.Embed(title=self.success_title, description=f"Successfully {act}ed: {md}", color=discord.Color.green()),
                ephemeral=True
            )
            await self.update_callback()
        except:
            await interaction.response.send_message(
                embed=discord.Embed(title="Error", description="Failed to manage roles.", color=0xE02B2B),
                ephemeral=True
            )

class ManageTryoutGroupsModal(discord.ui.Modal):
    action = discord.ui.TextInput(label="Action", placeholder="add/edit/delete", required=True, max_length=10)
    group_id = discord.ui.TextInput(label="Group ID", placeholder="numeric Group ID", required=True, max_length=20)
    event_name = discord.ui.TextInput(label="Event Name", required=False, max_length=100)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, required=False, max_length=2000)
    link = discord.ui.TextInput(label="Link", required=False, max_length=200)
    def __init__(self, db, guild, update_callback, settings_cog):
        super().__init__(title="Manage Tryout Groups")
        self.db, self.guild, self.update_callback, self.settings_cog = db, guild, update_callback, settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        act, gid = self.action.value.strip().lower(), self.group_id.value.strip()
        if act not in ['add','edit','delete']:
            return await interaction.response.send_message(
                embed=discord.Embed(title="Invalid Action", description="Use add/edit/delete.", color=0xE02B2B),
                ephemeral=True
            )
        if not gid.isdigit():
            return await interaction.response.send_message(
                embed=discord.Embed(title="Invalid Group ID", description="Must be numeric.", color=0xE02B2B),
                ephemeral=True
            )
        try:
            if act == 'add':
                if not (self.event_name.value.strip() and self.description.value.strip() and self.link.value.strip()):
                    return await interaction.response.send_message(
                        embed=discord.Embed(title="Missing Info", description="Provide all fields for adding.", color=0xE02B2B),
                        ephemeral=True
                    )
                if await self.db.get_tryout_group(self.guild.id, gid):
                    return await interaction.response.send_message(
                        embed=discord.Embed(title="Group Exists", description="This ID already exists.", color=0xE02B2B),
                        ephemeral=True
                    )
                await self.db.add_tryout_group(self.guild.id, gid, self.description.value.strip(), self.link.value.strip(), self.event_name.value.strip())
                await interaction.response.send_message(
                    embed=discord.Embed(title="Group Added", description=f"Added group: {self.event_name.value.strip()} (ID: {gid})", color=discord.Color.green()),
                    ephemeral=True
                )
            elif act == 'edit':
                ex = await self.db.get_tryout_group(self.guild.id, gid)
                if not ex:
                    return await interaction.response.send_message(
                        embed=discord.Embed(title="Not Found", description="No such group.", color=0xE02B2B),
                        ephemeral=True
                    )
                e_name = self.event_name.value.strip() or ex[3]
                desc = self.description.value.strip() or ex[1]
                lnk = self.link.value.strip() or ex[2]
                await self.db.update_tryout_group(self.guild.id, gid, desc, lnk, e_name)
                await interaction.response.send_message(
                    embed=discord.Embed(title="Group Updated", description=f"Updated {e_name} (ID: {gid})", color=discord.Color.green()),
                    ephemeral=True
                )
            else:  # delete
                if not await self.db.get_tryout_group(self.guild.id, gid):
                    return await interaction.response.send_message(
                        embed=discord.Embed(title="Not Found", description="No such group.", color=0xE02B2B),
                        ephemeral=True
                    )
                await self.db.delete_tryout_group(self.guild.id, gid)
                await interaction.response.send_message(
                    embed=discord.Embed(title="Group Deleted", description=f"Deleted group ID {gid}", color=discord.Color.green()),
                    ephemeral=True
                )
            await self.update_callback()
        except:
            await interaction.response.send_message(
                embed=discord.Embed(title="Error", description="Try again later.", color=0xE02B2B),
                ephemeral=True
            )

class AutomodMuteDurationModal(discord.ui.Modal):
    duration = discord.ui.TextInput(label="Mute Duration (seconds)", placeholder="3600", required=True, max_length=10)
    def __init__(self, db, guild, update_callback, settings_cog):
        super().__init__(title="Set Automod Mute Duration")
        self.db, self.guild, self.update_callback, self.settings_cog = db, guild, update_callback, settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        d = self.duration.value.strip()
        if not d.isdigit() or int(d) <= 0:
            return await interaction.response.send_message(
                embed=discord.Embed(title="Invalid Duration", description="Enter a positive number.", color=0xE02B2B),
                ephemeral=True
            )
        try:
            await self.db.set_automod_mute_duration(self.guild.id, int(d))
            await interaction.response.send_message(
                embed=discord.Embed(title="Mute Duration Set", description=f"Set to {d} seconds.", color=discord.Color.green()),
                ephemeral=True
            )
            await self.update_callback()
        except:
            await interaction.response.send_message(
                embed=discord.Embed(title="Error", description="Failed to set.", color=0xE02B2B),
                ephemeral=True
            )

class AutomodProtectedUsersModal(BaseRoleManagementModal):
    async def on_submit(self, interaction: discord.Interaction):
        act = self.action.value.strip().lower()
        if act not in ['add','remove']:
            return await interaction.response.send_message(
                embed=discord.Embed(title="Invalid Action", description="Use 'add' or 'remove'.", color=0xE02B2B),
                ephemeral=True
            )
        ids = [x for x in self.role_ids.value.strip().split() if x.strip()]
        if not ids:
            return await interaction.response.send_message(
                embed=discord.Embed(title="No User IDs", description="Provide at least one user ID.", color=0xE02B2B),
                ephemeral=True
            )
        valid, invalid = [], []
        for uid in ids:
            valid.append(int(uid)) if uid.isdigit() else invalid.append(uid)
        if invalid:
            return await interaction.response.send_message(
                embed=discord.Embed(title="Invalid User IDs", description=", ".join(invalid), color=0xE02B2B),
                ephemeral=True
            )
        try:
            m = self.add_method if act == 'add' else self.remove_method
            for u in valid:
                await m(self.guild.id, u)
            ud = ", ".join(f"<@{u}>" for u in valid)
            await interaction.response.send_message(
                embed=discord.Embed(title=self.success_title, description=f"Successfully {act}ed: {ud}", color=discord.Color.green()),
                ephemeral=True
            )
            await self.update_callback()
        except:
            await interaction.response.send_message(
                embed=discord.Embed(title="Error", description="Failed to manage users.", color=0xE02B2B),
                ephemeral=True
            )

class AutomodSettingsView(discord.ui.View):
    def __init__(self, db, guild, settings_cog, page=1):
        super().__init__(timeout=180)
        self.db = db
        self.guild = guild
        self.settings_cog = settings_cog
        self.page = page
        self.message = None

    @discord.ui.button(label="Previous Page", style=discord.ButtonStyle.secondary)
    async def previous_page_btn(self, interaction: discord.Interaction, _):
        if self.page == 2:
            await interaction.response.defer()
            self.page = 1
            await self.async_update_view()

    @discord.ui.button(label="Next Page", style=discord.ButtonStyle.secondary)
    async def next_page_btn(self, interaction: discord.Interaction, _):
        if self.page == 1:
            await interaction.response.defer()
            self.page = 2
            await self.async_update_view()

    @discord.ui.button(label="Toggle Automod", style=discord.ButtonStyle.primary, emoji="🔄")
    async def toggle_automod_btn(self, interaction: discord.Interaction, _):
        if self.page == 1:
            await interaction.response.defer()
            try:
                await self.db.toggle_server_setting(self.guild.id, 'automod_enabled')
                await self.async_update_view()
            except Exception as e:
                embed = discord.Embed(title="Error", description=f"Failed to toggle Automod: {e}", color=0xE02B2B)
                await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Toggle Logging", style=discord.ButtonStyle.primary, emoji="📝")
    async def toggle_logging_btn(self, interaction: discord.Interaction, _):
        if self.page == 1:
            await interaction.response.defer()
            try:
                await self.db.toggle_server_setting(self.guild.id, 'automod_logging_enabled')
                await self.async_update_view()
            except Exception as e:
                embed = discord.Embed(title="Error", description=f"Failed to toggle Logging: {e}", color=0xE02B2B)
                await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Set Log Channel", style=discord.ButtonStyle.primary, emoji="📌")
    async def set_log_channel_btn(self, interaction: discord.Interaction, _):
        if self.page == 1:
            # Direct response with modal
            await interaction.response.send_modal(BaseChannelModal(
                db=self.db,
                guild=self.guild,
                setting_name='automod_log_channel_id',
                update_callback=lambda: self.async_update_view(),
                settings_cog=self.settings_cog,
                title="Set Automod Log Channel"
            ))

    @discord.ui.button(label="Set Mute Duration", style=discord.ButtonStyle.primary, emoji="⏱")
    async def set_mute_duration_btn(self, interaction: discord.Interaction, _):
        if self.page == 2:
            await interaction.response.send_modal(AutomodMuteDurationModal(
                db=self.db,
                guild=self.guild,
                update_callback=lambda: self.async_update_view(),
                settings_cog=self.settings_cog
            ))
        else:
            embed = discord.Embed(title="Info", description="This setting is on the second page.", color=discord.Color.blue())
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Manage Protected Users", style=discord.ButtonStyle.primary, emoji="👤")
    async def manage_protected_users_btn(self, interaction: discord.Interaction, _):
        if self.page == 2:
            await interaction.response.send_modal(AutomodProtectedUsersModal(
                db=self.db,
                guild=self.guild,
                update_callback=lambda: self.async_update_view(),
                add_method=self.db.add_protected_user,
                remove_method=self.db.remove_protected_user,
                success_title="Protected Users Updated",
                settings_cog=self.settings_cog
            ))
        else:
            embed = discord.Embed(title="Info", description="Protected Users management is on the second page.", color=discord.Color.blue())
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Manage Exempt Roles", style=discord.ButtonStyle.primary, emoji="🛡")
    async def manage_exempt_roles_btn(self, interaction: discord.Interaction, _):
        if self.page == 2:
            await interaction.response.send_modal(BaseRoleManagementModal(
                db=self.db,
                guild=self.guild,
                update_callback=lambda: self.async_update_view(),
                add_method=self.db.add_exempt_role,
                remove_method=self.db.remove_exempt_role,
                success_title="Exempt Roles Updated",
                settings_cog=self.settings_cog
            ))
        else:
            embed = discord.Embed(title="Info", description="Exempt Roles management is on the second page.", color=discord.Color.blue())
            await interaction.response.send_message(embed=embed, ephemeral=True)

    async def async_update_view(self):
        if self.message:
            s = await self.db.get_server_settings(self.guild.id)
            e = await self.settings_cog.create_automod_settings_embed(s, self.guild.id, self.page)
            await self.message.edit(embed=e, view=self)

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        if self.message:
            await self.message.edit(view=self)

class ModerationSettingsView(discord.ui.View):
    def __init__(self, db, guild, settings_cog):
        super().__init__(timeout=180)
        self.db, self.guild, self.settings_cog = db, guild, settings_cog
        self.message = None

    @discord.ui.button(label="Set Log Channel", style=discord.ButtonStyle.primary, emoji="📌")
    async def set_log_channel_btn(self, interaction: discord.Interaction, _):
        if self.message:
            await interaction.response.send_modal(BaseChannelModal(
                db=self.db,
                guild=self.guild,
                setting_name='mod_log_channel_id',
                update_callback=lambda: self.async_update_view(),
                settings_cog=self.settings_cog,
                title="Set Moderation Log Channel"
            ))

    @discord.ui.button(label="Manage Allowed Roles", style=discord.ButtonStyle.primary, emoji="👥")
    async def manage_allowed_roles_btn(self, interaction: discord.Interaction, _):
        if self.message:
            await interaction.response.send_modal(BaseRoleManagementModal(
                db=self.db,
                guild=self.guild,
                update_callback=lambda: self.async_update_view(),
                add_method=self.db.add_moderation_allowed_role,
                remove_method=self.db.remove_moderation_allowed_role,
                success_title="Allowed Roles Updated",
                settings_cog=self.settings_cog
            ))

    async def async_update_view(self):
        if self.message:
            e = await self.settings_cog.create_moderation_settings_embed(self.guild)
            await self.message.edit(embed=e, view=self)

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        if self.message:
            await self.message.edit(view=self)

class TryoutSettingsView(discord.ui.View):
    def __init__(self, db, guild, settings_cog):
        super().__init__(timeout=180)
        self.db, self.guild, self.settings_cog = db, guild, settings_cog
        self.message = None

    @discord.ui.button(label="Set Tryout Channel", style=discord.ButtonStyle.primary, emoji="📌")
    async def set_tryout_channel_btn(self, interaction: discord.Interaction, _):
        if self.message:
            await interaction.response.send_modal(BaseChannelModal(
                db=self.db,
                guild=self.guild,
                setting_name='tryout_channel_id',
                update_callback=lambda: self.async_update_view(),
                settings_cog=self.settings_cog,
                title="Set Tryout Channel"
            ))

    @discord.ui.button(label="Manage Required Roles", style=discord.ButtonStyle.primary, emoji="👥")
    async def manage_required_roles_btn(self, interaction: discord.Interaction, _):
        if self.message:
            await interaction.response.send_modal(BaseRoleManagementModal(
                db=self.db,
                guild=self.guild,
                update_callback=lambda: self.async_update_view(),
                add_method=self.db.add_tryout_required_role,
                remove_method=self.db.remove_tryout_required_role,
                success_title="Required Roles Updated",
                settings_cog=self.settings_cog
            ))

    @discord.ui.button(label="Manage Tryout Groups", style=discord.ButtonStyle.primary, emoji="🔧")
    async def manage_tryout_groups_btn(self, interaction: discord.Interaction, _):
        if self.message:
            await interaction.response.send_modal(ManageTryoutGroupsModal(
                db=self.db,
                guild=self.guild,
                update_callback=lambda: self.async_update_view(),
                settings_cog=self.settings_cog
            ))

    @discord.ui.button(label="Manage Ping Roles", style=discord.ButtonStyle.primary, emoji="📢")
    async def manage_ping_roles_btn(self, interaction: discord.Interaction, _):
        if self.message:
            await interaction.response.send_modal(BaseRoleManagementModal(
                db=self.db,
                guild=self.guild,
                update_callback=lambda: self.async_update_view(),
                add_method=self.db.add_ping_role,
                remove_method=self.db.remove_ping_role,
                success_title="Ping Roles Updated",
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
            await self.message.edit(view=self)

async def setup(bot):
    await bot.add_cog(Settings(bot))
