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
    AUTOPROMOTION = "autopromotion"  # New category added here

class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = None
        self.owner_id = None
        self.category_handlers = {
            SettingsCategory.AUTOMOD.value: self.handle_automod_settings,
            SettingsCategory.TRYOUT.value: self.handle_tryout_settings,
            SettingsCategory.MODERATION.value: self.handle_moderation_settings,
            SettingsCategory.AUTOPROMOTION.value: self.handle_autopromotion_settings  # integrate new handler
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
        app_commands.Choice(name="Autopromotion", value=SettingsCategory.AUTOPROMOTION.value)  # include autopromotion
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

    # ---------------------------
    # AUTOMOD SETTINGS HANDLER
    # ---------------------------
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

    # ---------------------------
    # TRYOUT SETTINGS HANDLER
    # ---------------------------
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

    # ---------------------------
    # MODERATION SETTINGS HANDLER
    # ---------------------------
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

    # ---------------------------
    # AUTOPROMOTION SETTINGS HANDLER
    # ---------------------------
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

    # ---------------------------
    # AUTOMOD EMBED CREATION
    # ---------------------------
    async def create_automod_settings_embed(self, s: dict, guild_id: int, page: int) -> discord.Embed:
        au_status = "✅ Enabled" if s.get('automod_enabled') else "❌ Disabled"
        lg_status = "✅ Enabled" if s.get('automod_logging_enabled') else "❌ Disabled"
        lg_ch = f"<#{s.get('automod_log_channel_id')}>" if s.get('automod_log_channel_id') else "Not Set"
        mute = await self.db.get_automod_mute_duration(guild_id)
        prot = await self.db.get_protected_users(guild_id)
        exempts = await self.db.get_automod_exempt_roles(guild_id)
        prot_display = ", ".join(f"<@{u}>" for u in prot) if prot else "None"
        exempts_display = ", ".join(f"<@&{r}>" for r in exempts) if exempts else "None"

        embed = discord.Embed(title="⚙️ Automod Settings", color=discord.Color.blue(), description=f"Page {page}/2")
        embed.set_footer(text="Use the buttons below to configure.")
        
        if page == 1:
            embed.add_field(name="Automod Status", value=au_status, inline=True)
            embed.add_field(name="Logging Status", value=lg_status, inline=True)
            embed.add_field(name="Log Channel", value=lg_ch, inline=False)
        else:
            embed.add_field(name="Mute Duration (seconds)", value=str(mute), inline=True)
            embed.add_field(name="Protected Users", value=prot_display, inline=False)
            embed.add_field(name="Exempt Roles", value=exempts_display, inline=False)
        return embed

    # ---------------------------
    # TRYOUT EMBED CREATION
    # ---------------------------
    async def create_tryout_settings_embed(self, guild: discord.Guild) -> discord.Embed:
        ch_id = await self.db.get_tryout_channel_id(guild.id)
        ch = f"<#{ch_id}>" if ch_id else "Not Set"
        req = await self.db.get_tryout_required_roles(guild.id)
        req_display = ", ".join(f"<@&{r}>" for r in req) if req else "Not Set"
        groups = await self.db.get_tryout_groups(guild.id)
        grp_display = "\n\n".join(
            f"**{g[2]}** (ID: {g[0]})\nDescription: {g[1]}\nRequirements:\n" + ("\n".join(f"- {r}" for r in g[3]) if g[3] else "None")
            for g in groups
        ) if groups else "No groups."
        ping = await self.db.get_ping_roles(guild.id)
        ping_display = ", ".join(f"<@&{r}>" for r in ping) if ping else "No roles set."
        allowed_vcs = await self.db.get_tryout_allowed_vcs(guild.id)
        vc_display = ", ".join(f"<#{vc}>" for vc in allowed_vcs) if allowed_vcs else "None"

        embed = discord.Embed(title="⚙️ Tryout Settings", color=discord.Color.blue())
        embed.add_field(name="Tryout Channel", value=ch, inline=False)
        embed.add_field(name="Required Roles", value=req_display, inline=False)
        embed.add_field(name="Tryout Groups", value=grp_display, inline=False)
        embed.add_field(name="Ping Roles", value=ping_display, inline=False)
        embed.add_field(name="Allowed Voice Channels", value=vc_display, inline=False)
        return embed

    # ---------------------------
    # MODERATION EMBED CREATION
    # ---------------------------
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

    # ---------------------------
    # AUTOPROMOTION EMBED CREATION
    # ---------------------------
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

class ManageTryoutGroupsModal(discord.ui.Modal):
    action = discord.ui.TextInput(label="Action", placeholder="add/edit/delete", required=True, max_length=10)
    group_id = discord.ui.TextInput(label="Group ID", placeholder="numeric Group ID", required=True, max_length=20)
    event_name = discord.ui.TextInput(label="Event Name", required=False, max_length=100)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, required=False, max_length=2000)
    requirements = discord.ui.TextInput(label="Requirements", placeholder="One requirement per line", required=False, style=discord.TextStyle.paragraph)

    def __init__(self, db, guild, update_callback, settings_cog):
        super().__init__(title="Manage Tryout Groups")
        self.db = db
        self.guild = guild
        self.update_callback = update_callback
        self.settings_cog = settings_cog

    async def on_submit(self, interaction: discord.Interaction):
        act = self.action.value.strip().lower()
        gid = self.group_id.value.strip()
        if act not in ['add','edit','delete']:
            return await interaction.response.send_message(embed=discord.Embed(title="Invalid Action", description="Use add/edit/delete.", color=0xE02B2B), ephemeral=True)
        if not gid.isdigit():
            return await interaction.response.send_message(embed=discord.Embed(title="Invalid Group ID", description="Must be numeric.", color=0xE02B2B), ephemeral=True)

        try:
            reqs = []
            if self.requirements.value and self.requirements.value.strip():
                reqs = [r.strip() for r in self.requirements.value.strip().split('\n') if r.strip()]

            if act == 'add':
                if not (self.event_name.value and self.event_name.value.strip() and 
                        self.description.value and self.description.value.strip()):
                    return await interaction.response.send_message(embed=discord.Embed(title="Missing Info", description="Provide event name and description for adding.", color=0xE02B2B), ephemeral=True)
                if await self.db.get_tryout_group(self.guild.id, gid):
                    return await interaction.response.send_message(embed=discord.Embed(title="Group Exists", description="This ID already exists.", color=0xE02B2B), ephemeral=True)
                await self.db.add_tryout_group(
                    self.guild.id, gid, 
                    self.description.value.strip(), 
                    self.event_name.value.strip(),
                    requirements=reqs
                )
                await interaction.response.send_message(
                    embed=discord.Embed(title="Group Added", description=f"Added group: {self.event_name.value.strip()} (ID: {gid})", color=discord.Color.green()),
                    ephemeral=True
                )
            elif act == 'edit':
                ex = await self.db.get_tryout_group(self.guild.id, gid)
                if not ex:
                    return await interaction.response.send_message(embed=discord.Embed(title="Not Found", description="No such group.", color=0xE02B2B), ephemeral=True)

                e_name = self.event_name.value.strip() or ex[2]
                desc = self.description.value.strip() or ex[1]
                existing_reqs = ex[3]
                final_requirements = reqs if self.requirements.value and reqs else existing_reqs

                await self.db.update_tryout_group(self.guild.id, gid, desc, e_name, final_requirements)
                await interaction.response.send_message(
                    embed=discord.Embed(title="Group Updated", description=f"Updated {e_name} (ID: {gid})", color=discord.Color.green()),
                    ephemeral=True
                )
            else:  # delete
                if not await self.db.get_tryout_group(self.guild.id, gid):
                    return await interaction.response.send_message(embed=discord.Embed(title="Not Found", description="No such group.", color=0xE02B2B), ephemeral=True)
                await self.db.delete_tryout_group(self.guild.id, gid)
                await interaction.response.send_message(
                    embed=discord.Embed(title="Group Deleted", description=f"Deleted group ID {gid}", color=discord.Color.green()),
                    ephemeral=True
                )

            await self.update_callback()
        except Exception as e:
            logger.error("Error in ManageTryoutGroupsModal on_submit:")
            traceback.print_exc()
            await interaction.response.send_message(
                embed=discord.Embed(title="Error", description=f"Try again later: {e}", color=0xE02B2B),
                ephemeral=True
            )

class AutomodMuteDurationModal(discord.ui.Modal):
    duration = discord.ui.TextInput(label="Mute Duration (seconds)", placeholder="3600", required=True, max_length=10)

    def __init__(self, db, guild, update_callback, settings_cog):
        super().__init__(title="Set Automod Mute Duration")
        self.db = db
        self.guild = guild
        self.update_callback = update_callback
        self.settings_cog = settings_cog

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
        except Exception as e:
            logger.error("Error in AutomodMuteDurationModal on_submit:")
            traceback.print_exc()
            await interaction.response.send_message(
                embed=discord.Embed(title="Error", description=f"Failed to set mute duration: {e}", color=0xE02B2B),
                ephemeral=True
            )

class AutomodProtectedUsersModal(discord.ui.Modal):
    action = discord.ui.TextInput(label="Action", placeholder="add/remove", required=True, max_length=6)
    user_ids = discord.ui.TextInput(label="User IDs", placeholder="IDs separated by spaces", required=True, style=discord.TextStyle.paragraph, max_length=2000)

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

        ids = [x for x in self.user_ids.value.strip().split() if x.strip()]
        if not ids:
            return await interaction.response.send_message(
                embed=discord.Embed(title="No User IDs", description="Provide at least one user ID.", color=0xE02B2B),
                ephemeral=True
            )

        valid, invalid = [], []
        for uid in ids:
            if uid.isdigit():
                valid.append(int(uid))
            else:
                invalid.append(uid)

        if invalid:
            return await interaction.response.send_message(
                embed=discord.Embed(title="Invalid User IDs", description=", ".join(invalid), color=0xE02B2B),
                ephemeral=True
            )

        try:
            method = self.add_method if act == 'add' else self.remove_method
            for u in valid:
                await method(self.guild.id, u)

            ud = ", ".join(f"<@{u}>" for u in valid)
            await interaction.response.send_message(
                embed=discord.Embed(title=self.success_title, description=f"Successfully {act}ed: {ud}", color=discord.Color.green()),
                ephemeral=True
            )
            await self.update_callback()
        except Exception as e:
            logger.error("Error in AutomodProtectedUsersModal on_submit:")
            traceback.print_exc()
            await interaction.response.send_message(
                embed=discord.Embed(title="Error", description=f"Failed to manage users: {e}", color=0xE02B2B),
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
            await self.db.toggle_server_setting(self.guild.id, 'automod_enabled')
            await self.async_update_view()

    @discord.ui.button(label="Toggle Logging", style=discord.ButtonStyle.primary, emoji="📝")
    async def toggle_logging_btn(self, interaction: discord.Interaction, _):
        if self.page == 1:
            await interaction.response.defer()
            await self.db.toggle_server_setting(self.guild.id, 'automod_logging_enabled')
            await self.async_update_view()

    @discord.ui.button(label="Set Log Channel", style=discord.ButtonStyle.primary, emoji="📌")
    async def set_log_channel_btn(self, interaction: discord.Interaction, _):
        if self.page == 1:
            await interaction.response.send_modal(BaseChannelModal(
                db=self.db,
                guild=self.guild,
                setting_name='automod_log_channel_id',
                update_callback=self.async_update_view,
                settings_cog=self.settings_cog,
                title="Set Automod Log Channel"
            ))

    @discord.ui.button(label="Set Mute Duration", style=discord.ButtonStyle.primary, emoji="⏱")
    async def set_mute_duration_btn(self, interaction: discord.Interaction, _):
        if self.page == 2:
            await interaction.response.send_modal(AutomodMuteDurationModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.async_update_view,
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
                update_callback=self.async_update_view,
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
                update_callback=self.async_update_view,
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
            try:
                await self.message.edit(view=self)
            except:
                pass

class ModerationSettingsView(discord.ui.View):
    def __init__(self, db, guild, settings_cog):
        super().__init__(timeout=180)
        self.db = db
        self.guild = guild
        self.settings_cog = settings_cog
        self.message = None

    @discord.ui.button(label="Set Log Channel", style=discord.ButtonStyle.primary, emoji="📌")
    async def set_log_channel_btn(self, interaction: discord.Interaction, _):
        if self.message:
            await interaction.response.send_modal(BaseChannelModal(
                db=self.db,
                guild=self.guild,
                setting_name='mod_log_channel_id',
                update_callback=self.async_update_view,
                settings_cog=self.settings_cog,
                title="Set Moderation Log Channel"
            ))

    @discord.ui.button(label="Manage Allowed Roles", style=discord.ButtonStyle.primary, emoji="👥")
    async def manage_allowed_roles_btn(self, interaction: discord.Interaction, _):
        if self.message:
            await interaction.response.send_modal(BaseRoleManagementModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.async_update_view,
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
            try:
                await self.message.edit(view=self)
            except:
                pass

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
            await interaction.response.send_modal(ManageTryoutGroupsModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.async_update_view,
                settings_cog=self.settings_cog
            ))

    @discord.ui.button(label="Manage Ping Roles", style=discord.ButtonStyle.primary, emoji="📢")
    async def manage_ping_roles_btn(self, interaction: discord.Interaction, _):
        if self.message:
            await interaction.response.send_modal(BaseRoleManagementModal(
                db=self.db,
                guild=self.guild,
                update_callback=self.async_update_view,
                add_method=self.db.add_ping_role,
                remove_method=self.db.remove_ping_role,
                success_title="Ping Roles Updated",
                settings_cog=self.settings_cog
            ))

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

# NEW Autopromotion classes
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