"""
Copyright © Krypton 2019-Present - https://github.com/kkrypt0nn (https://krypton.ninja)
Description:
🐍 A simple template to start to code your own and personalized Discord bot in Python

Version: 6.2.0
"""

import platform
import re
from datetime import datetime
import json
import io
import uuid

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context


class FeedbackForm(discord.ui.Modal, title="Feedback"):
    feedback = discord.ui.TextInput(
        label="What do you think about this bot?",
        style=discord.TextStyle.long,
        placeholder="Type your answer here...",
        required=True,
        max_length=256,
    )

    async def on_submit(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.answer = str(self.feedback)
        self.stop()


class CreateEmbedModal(discord.ui.Modal, title="Create an Embed"):
    embed_title = discord.ui.TextInput(
        label="Embed Title",
        style=discord.TextStyle.short,
        placeholder="Enter the title for the embed...",
        required=False,
        max_length=256,
    )
    embed_description = discord.ui.TextInput(
        label="Embed Description",
        style=discord.TextStyle.long,
        placeholder="Enter the description for the embed...",
        required=True,
        max_length=2048,
    )
    embed_color = discord.ui.TextInput(
        label="Embed Color (Hex)",
        style=discord.TextStyle.short,
        placeholder="#FFFFFF",
        required=False,
        max_length=7,
    )

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    def resolve_emojis(self, text: str) -> str:
        """
        Resolves custom emoji shortcodes in the format :emoji_name: to actual emojis.

        :param text: The text to process.
        :return: The text with resolved emojis.
        """
        pattern = r':(\w+):'
        emojis = self.channel.guild.emojis
        emoji_dict = {emoji.name: str(emoji) for emoji in emojis}

        def replace(match):
            name = match.group(1)
            return emoji_dict.get(name, match.group(0))  # If not found, keep as is

        return re.sub(pattern, replace, text)

    async def on_submit(self, interaction: discord.Interaction):
        title = self.embed_title.value.strip() or None
        description = self.embed_description.value.strip()
        color_input = self.embed_color.value.strip()

        # Resolve emojis in the description
        description = self.resolve_emojis(description)

        # Resolve emojis in the title if provided
        if title:
            title = self.resolve_emojis(title)

        # Validate and convert color
        color = 0xBEBEFE  # Default color
        if color_input:
            try:
                if color_input.startswith("#"):
                    color = int(color_input[1:], 16)
                else:
                    color = int(color_input, 16)
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid color format. Please provide a valid hex color code.",
                    ephemeral=True
                )
                return

        embed = discord.Embed(description=description, color=color)
        if title:
            embed.title = title

        try:
            await self.channel.send(embed=embed)
            await interaction.response.send_message(
                f"✅ Embed successfully sent to {self.channel.mention}.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ I don't have permission to send messages in {self.channel.mention}.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ Failed to send embed: {e}",
                ephemeral=True
            )


class General(commands.Cog, name="general"):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.context_menu_user = app_commands.ContextMenu(
            name="Grab ID", callback=self.grab_id
        )
        self.bot.tree.add_command(self.context_menu_user)
        self.context_menu_message = app_commands.ContextMenu(
            name="Remove spoilers", callback=self.remove_spoilers
        )
        self.bot.tree.add_command(self.context_menu_message)

    # Message context menu command
    async def remove_spoilers(
        self, interaction: discord.Interaction, message: discord.Message
    ) -> None:
        """
        Removes the spoilers from the message.

        :param interaction: The application command interaction.
        :param message: The message that is being interacted with.
        """
        spoiler_attachment = None
        for attachment in message.attachments:
            if attachment.is_spoiler():
                spoiler_attachment = attachment
                break
        embed = discord.Embed(
            title="Message without spoilers",
            description=message.content.replace("||", ""),
            color=0xBEBEFE,
        )
        if spoiler_attachment is not None:
            embed.set_image(url=attachment.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # User context menu command
    async def grab_id(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        """
        Grabs the ID of the user.

        :param interaction: The application command interaction.
        :param user: The user that is being interacted with.
        """
        embed = discord.Embed(
            description=f"The ID of {user.mention} is `{user.id}`.",
            color=0xBEBEFE,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.hybrid_command(
        name="help", description="List all commands the bot has loaded."
    )
    async def help(self, context: Context) -> None:
        prefix = self.bot.config["prefix"]
        embed = discord.Embed(
            title="Help", description="List of available commands:", color=0xBEBEFE
        )
        # Create a mapping from cog names to list of commands
        cog_commands = {}
        # Create a set to keep track of command names already included
        included_commands = set()
        # Regular commands
        for command in self.bot.commands:
            if command.name in included_commands:
                continue
            if isinstance(command, commands.HybridCommand):
                # We'll include hybrid commands as slash commands later
                continue  # Skip hybrid commands here
            cog_name = command.cog_name or "No Category"
            if cog_name not in cog_commands:
                cog_commands[cog_name] = []
            description = command.description.partition('\n')[0]
            command_entry = "{}{} - {}".format(prefix, command.name, description)
            cog_commands[cog_name].append(command_entry)
            included_commands.add(command.name)
        # Application commands
        for app_command in self.bot.tree.walk_commands():
            if app_command.name in included_commands:
                continue
            binding = app_command.binding
            if isinstance(binding, commands.Cog):
                cog_name = binding.qualified_name
            else:
                cog_name = "No Category"
            if cog_name not in cog_commands:
                cog_commands[cog_name] = []
            if isinstance(app_command, app_commands.Command):
                description = app_command.description.partition('\n')[0]
                command_entry = "/{} - {}".format(app_command.name, description)
                cog_commands[cog_name].append(command_entry)
                included_commands.add(app_command.name)
        # Now build the embed
        for cog_name, commands_list in cog_commands.items():
            if cog_name.lower() == "owner" and not (await self.bot.is_owner(context.author)):
                continue
            if commands_list:
                help_text = "\n".join(commands_list)
                # Use str.format() instead of f-string to avoid SyntaxError
                embed.add_field(
                    name=cog_name.capitalize(),
                    value="```{}```".format(help_text),
                    inline=False,
                )
        await context.send(embed=embed)

    @commands.hybrid_command(
        name="botinfo",
        description="Get some useful information about the bot.",
    )
    async def botinfo(self, context: Context) -> None:
        """
        Get some useful (or not) information about the bot.

        :param context: The hybrid command context.
        """
        # Calculate uptime
        uptime = datetime.utcnow() - self.bot.start_time
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"

        # Get total members across all guilds
        total_members = sum(guild.member_count for guild in self.bot.guilds)
        
        # Get total channels across all guilds
        total_channels = sum(len(guild.channels) for guild in self.bot.guilds)

        embed = discord.Embed(
            title="🤖 Bot Information",
            description=(
                f"A bot designed for SDHS.\n"
                f"Use `/help` to see available commands."
            ),
            color=0x3498DB,  # Discord Blue
            timestamp=datetime.utcnow()
        )

        # Bot Stats
        embed.add_field(
            name="📊 Stats",
            value=(
                f"**Servers:** {len(self.bot.guilds)}\n"
                f"**Members:** {total_members:,}\n"
                f"**Channels:** {total_channels:,}\n"
                f"**Commands Run:** {self.bot.command_count:,}\n"
                f"**Messages Seen:** {self.bot.message_count:,}"
            ),
            inline=True
        )

        # Technical Info
        embed.add_field(
            name="💻 Technical",
            value=(
                f"**Python:** {platform.python_version()}\n"
                f"**Discord.py:** {discord.__version__}\n"
                f"**Latency:** {round(self.bot.latency * 1000)}ms\n"
                f"**Uptime:** {uptime_str}\n"
                f"**Platform:** {platform.system()} {platform.release()}"
            ),
            inline=True
        )

        # Command Info
        embed.add_field(
            name="⌨️ Commands",
            value=(
                f"**Prefix:** `/` (Slash) or `{self.bot.config['prefix']}`\n"
                f"**Total Commands:** {len(set(self.bot.walk_commands()))}"
            ),
            inline=False
        )

        # Set footer
        embed.set_footer(
            text=f"Requested by {context.author}",
            icon_url=context.author.display_avatar.url
        )

        # Set thumbnail if bot has avatar
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        await context.send(embed=embed)

    @commands.hybrid_command(
        name="serverinfo",
        description="Get some useful information about the server.",
    )
    async def serverinfo(self, context: Context) -> None:
        """
        Get some useful information about the server.

        :param context: The hybrid command context.
        """
        roles = [role.name for role in context.guild.roles]
        num_roles = len(roles)
        if num_roles > 50:
            roles = roles[:50]
            roles.append(f">>>> Displaying [50/{num_roles}] Roles")
        roles = ", ".join(roles)

        embed = discord.Embed(
            title="**Server Name:**", description=f"{context.guild}", color=0xBEBEFE
        )
        if context.guild.icon is not None:
            embed.set_thumbnail(url=context.guild.icon.url)
        embed.add_field(name="Server ID", value=context.guild.id)
        embed.add_field(name="Member Count", value=context.guild.member_count)
        embed.add_field(
            name="Text/Voice Channels", value=f"{len(context.guild.channels)}"
        )
        embed.add_field(name=f"Roles ({len(context.guild.roles)})", value=roles)
        embed.set_footer(text=f"Created at: {context.guild.created_at}")
        await context.send(embed=embed)

    @commands.hybrid_command(
        name="ping",
        description="Check if the bot is alive.",
    )
    async def ping(self, context: Context) -> None:
        """
        Check if the bot is alive.

        :param context: The hybrid command context.
        """
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"The bot latency is {round(self.bot.latency * 1000)}ms.",
            color=0xBEBEFE,
        )
        await context.send(embed=embed)

    @app_commands.command(
        name="feedback", description="Submit feedback to the owners of the bot."
    )
    async def feedback(self, interaction: discord.Interaction) -> None:
        """
        Submit feedback for the owners of the bot.

        :param interaction: The command interaction.
        """
        feedback_form = FeedbackForm()
        await interaction.response.send_modal(feedback_form)

        await feedback_form.wait()
        interaction = feedback_form.interaction
        await interaction.response.send_message(
            embed=discord.Embed(
                description="Thank you for your feedback! The owners have been notified.",
                color=0xBEBEFE,
            )
        )

        app_owner = (await self.bot.application_info()).owner
        await app_owner.send(
            embed=discord.Embed(
                title="New Feedback",
                description=f"{interaction.user} (<@{interaction.user.id}>) has submitted new feedback:\n```\n{feedback_form.answer}\n```",
                color=0xBEBEFE,
            )
        )

    @app_commands.command(
        name="embed", description="Create an embed in a specified channel."
    )
    @app_commands.describe(channel="The channel where the embed will be sent.")
    @app_commands.default_permissions(manage_messages=True)
    async def embed_command(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        """
        Creates an embed in the specified channel after receiving text input.

        :param interaction: The command interaction.
        :param channel: The channel to send the embed to.
        """
        # Check if the bot has permission to send messages in the specified channel
        if not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(
                f"❌ I don't have permission to send messages in {channel.mention}.",
                ephemeral=True
            )
            return

        # Instantiate and send the modal
        embed_modal = CreateEmbedModal(channel)
        await interaction.response.send_modal(embed_modal)

    # Ensure the new command is registered with the bot
    @embed_command.error
    async def embed_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ An error occurred while processing the command.", ephemeral=True
            )

    @app_commands.command(
        name="gdpr-request",
        description="Request all data stored about yourself or any user (bot owner only)"
    )
    @app_commands.describe(user="The user to export data for (bot owner only for other users)")
    async def gdpr_request(
        self, 
        interaction: discord.Interaction,
        user: discord.Member = None
    ):
        """Request all data stored about yourself or any user (bot owner only)"""
        
        # Determine target user
        target_user = user or interaction.user
        
        # Check permissions
        is_owner = await self.bot.is_owner(interaction.user)
        if target_user.id != interaction.user.id and not is_owner:
            error_embed = discord.Embed(
                title="❌ Permission Denied",
                description="You can only export your own data unless you're the bot owner.",
                color=0xE74C3C
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return
        
        # Defer the response as this might take a moment
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get MongoDB database instance
            db = self.bot.database.db
            
            # Check for cooldown unless user is bot owner
            if not is_owner:
                has_recent_request = await self.bot.database.check_recent_gdpr_request(interaction.user.id)
                if has_recent_request:
                    cooldown_embed = discord.Embed(
                        title="⏳ Cooldown Active",
                        description="You can only make one GDPR request every 24 hours.\nPlease try again later.",
                        color=0xF1C40F
                    )
                    await interaction.followup.send(embed=cooldown_embed, ephemeral=True)
                    return
            
            # Initialize data structure
            user_data = {
                "user_id": target_user.id,
                "username": str(target_user),
                "export_date": datetime.utcnow().isoformat(),
                "data": {}
            }

            # Get all collections in the database
            collections = await db.list_collection_names()
            user_id_str = str(target_user.id)
            
            def deep_search(obj, search_value):
                """Recursively search through nested structures for a value"""
                if isinstance(obj, (str, int)):
                    return str(search_value) in str(obj)
                elif isinstance(obj, list):
                    return any(deep_search(item, search_value) for item in obj)
                elif isinstance(obj, dict):
                    return any(deep_search(value, search_value) for value in obj.values())
                return False
            
            for collection_name in collections:
                # Skip the gdpr_requests collection
                if collection_name == "gdpr_requests":
                    continue
                    
                collection = db[collection_name]
                documents = []
                
                # Look at every single document in the collection
                async for doc in collection.find({}):
                    # Deep search through the entire document
                    if deep_search(doc, user_id_str):
                        # Convert ObjectId to string for JSON serialization
                        if "_id" in doc:
                            doc["_id"] = str(doc["_id"])
                        
                        # Add guild information if available
                        if "server_id" in doc or "guild_id" in doc:
                            guild_id = doc.get("server_id") or doc.get("guild_id")
                            if guild_id is not None:  # Check if guild_id exists
                                try:
                                    guild = self.bot.get_guild(int(guild_id)) if isinstance(guild_id, (str, int)) else None
                                    if guild:
                                        doc["guild_name"] = guild.name
                                except (ValueError, TypeError):
                                    # If conversion fails, skip adding guild name
                                    pass
                        
                        # Redact private information, moderator IDs, and reasons if not owner
                        if not is_owner and doc.get("moderator_id") != str(interaction.user.id):
                            def redact_sensitive_info(obj):
                                """Recursively redact sensitive information"""
                                if isinstance(obj, dict):
                                    sensitive_fields = [
                                        "moderator_id", "reason", "message", "private_notes",
                                        "message_content", "notes", "comment", "private_comment"
                                    ]
                                    return {
                                        k: "[REDACTED]" if k in sensitive_fields else redact_sensitive_info(v)
                                        for k, v in obj.items()
                                    }
                                elif isinstance(obj, list):
                                    return [redact_sensitive_info(item) for item in obj]
                                return obj
                            
                            doc = redact_sensitive_info(doc)
                        
                        # Convert datetime objects to ISO format
                        def convert_datetime(obj):
                            """Recursively convert datetime objects to ISO format"""
                            if isinstance(obj, datetime):
                                return obj.isoformat()
                            elif isinstance(obj, dict):
                                return {k: convert_datetime(v) for k, v in obj.items()}
                            elif isinstance(obj, list):
                                return [convert_datetime(item) for item in obj]
                            return obj
                        
                        # Convert the document
                        converted_doc = convert_datetime(doc)
                        documents.append(converted_doc)
                
                # Only add collection to output if we found matching documents
                if documents:
                    user_data["data"][collection_name] = documents

            # Create a unique request ID
            request_id = str(uuid.uuid4())

            # If user is bot owner, skip the request system and send data directly
            if is_owner:
                # Create the data file
                file = discord.File(
                    io.StringIO(json.dumps(user_data, indent=2)),
                    filename=f"user_data_{target_user.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
                )
                
                # Create response embed
                embed = discord.Embed(
                    title="📊 GDPR Data Export",
                    description=(
                        f"Complete data export for {target_user.mention}\n"
                        f"Deep searched through all documents across all collections."
                    ),
                    color=0x2ECC71  # Green color
                )
                
                if user_data["data"]:
                    collection_summary = []
                    total_entries = 0
                    
                    for collection_name, documents in user_data["data"].items():
                        collection_summary.append(f"✓ {collection_name}: {len(documents)} entries")
                        total_entries += len(documents)
                    
                    embed.add_field(
                        name="📁 Data Summary",
                        value="\n".join(collection_summary),
                        inline=False
                    )
                    
                    embed.add_field(
                        name="📊 Total Entries",
                        value=f"{total_entries} documents found",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="📁 Data Summary",
                        value="No data found in any collection",
                        inline=False
                    )

                embed.set_footer(text=f"Export generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
                await interaction.followup.send(embed=embed, file=file, ephemeral=True)
                return

            # Store the request in the database
            await self.bot.database.create_gdpr_request(
                request_id,
                interaction.user.id,
                target_user.id,
                user_data
            )

            # Create summary embed for the user
            user_embed = discord.Embed(
                title="📊 GDPR Data Request Submitted",
                description=(
                    f"Your request to export data for {target_user.mention} has been submitted for review.\n"
                    f"You will be notified once an administrator has reviewed your request."
                ),
                color=0x3498DB  # Blue color
            )
            user_embed.add_field(
                name="📝 Request Details",
                value=(
                    f"**Request ID:** `{request_id}`\n"
                    f"**Submitted:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                    f"**Status:** Pending Review"
                ),
                inline=False
            )
            user_embed.set_footer(text="You will receive a notification when your request is processed.")
            
            # Send confirmation to the user
            await interaction.followup.send(embed=user_embed, ephemeral=True)

            # Create review embed for bot owner
            review_embed = discord.Embed(
                title="📊 New GDPR Data Request",
                description=(
                    f"A new GDPR data export request requires your review.\n"
                    f"Please use the buttons below to approve or deny this request."
                ),
                color=0xE67E22  # Orange color
            )
            
            review_embed.add_field(
                name="👤 Request Information",
                value=(
                    f"**Requester:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                    f"**Target User:** {target_user.mention} (`{target_user.id}`)\n"
                    f"**Request ID:** `{request_id}`\n"
                    f"**Submitted:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                ),
                inline=False
            )

            # Add data summary to review embed
            if user_data["data"]:
                collection_summary = []
                total_entries = 0
                
                for collection_name, documents in user_data["data"].items():
                    collection_summary.append(f"✓ {collection_name}: {len(documents)} entries")
                    total_entries += len(documents)
                
                review_embed.add_field(
                    name="📁 Data Summary",
                    value="\n".join(collection_summary),
                    inline=False
                )
                
                review_embed.add_field(
                    name="📊 Total Entries",
                    value=f"{total_entries} documents found",
                    inline=False
                )
            else:
                review_embed.add_field(
                    name="📁 Data Summary",
                    value="No data found in any collection",
                    inline=False
                )

            review_embed.set_footer(text="Please review the attached data file before making a decision.")

            # Send review request to bot owner
            app_info = await self.bot.application_info()
            owner = app_info.owner
            
            # Create the data file for review
            review_file = discord.File(
                io.StringIO(json.dumps(user_data, indent=2)),
                filename=f"review_data_{target_user.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            )
            
            # Send review message with buttons
            await owner.send(
                embed=review_embed,
                file=review_file,
                view=GDPRReviewButtons(request_id)
            )
            
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Error Processing Request",
                description=(
                    f"An error occurred while processing your GDPR request:\n"
                    f"```{str(e)}```"
                ),
                color=0xE74C3C  # Red color
            )
            error_embed.set_footer(text="Please try again later or contact the bot owner if the issue persists.")
            await interaction.followup.send(embed=error_embed, ephemeral=True)


class GDPRReviewButtons(discord.ui.View):
    def __init__(self, request_id: str):
        super().__init__(timeout=None)  # No timeout for admin review
        self.request_id = request_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Update request status
        await interaction.client.database.update_gdpr_request(
            self.request_id,
            "approved",
            interaction.user.id
        )

        # Get the request data
        request = await interaction.client.database.get_gdpr_request(self.request_id)
        if not request:
            error_embed = discord.Embed(
                title="❌ Request Not Found",
                description="The GDPR request could not be found in the database.",
                color=0xE74C3C
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return

        # Send data to the original requester
        try:
            requester = await interaction.client.fetch_user(int(request["requester_id"]))
            if requester:
                # Create the data file
                file = discord.File(
                    io.StringIO(json.dumps(request["data"], indent=2)),
                    filename=f"user_data_{request['target_user_id']}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
                )
                
                # Create response embed
                embed = discord.Embed(
                    title="✅ GDPR Data Request Approved",
                    description="Your data request has been approved. Please find your data attached below.",
                    color=0x2ECC71
                )
                embed.add_field(
                    name="📝 Request Details",
                    value=(
                        f"**Request ID:** `{self.request_id}`\n"
                        f"**Approved At:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    ),
                    inline=False
                )
                embed.set_footer(text="Thank you for your patience.")
                
                await requester.send(embed=embed, file=file)
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Error Sending Data",
                description=f"Failed to send data to the requester:\n```{str(e)}```",
                color=0xE74C3C
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return

        # Disable all buttons
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(view=self)
        
        success_embed = discord.Embed(
            title="✅ Request Processed",
            description="The GDPR request has been approved and the data has been sent to the user.",
            color=0x2ECC71
        )
        success_embed.set_footer(text=f"Request ID: {self.request_id}")
        await interaction.followup.send(embed=success_embed, ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, emoji="❌")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Create modal for denial reason
        modal = DenialReasonModal(self.request_id)
        await interaction.response.send_modal(modal)


class DenialReasonModal(discord.ui.Modal, title="Denial Reason"):
    def __init__(self, request_id: str):
        super().__init__()
        self.request_id = request_id

    reason = discord.ui.TextInput(
        label="Why are you denying this request?",
        style=discord.TextStyle.paragraph,
        placeholder="Enter the reason for denial...",
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Update request status with denial reason
        await interaction.client.database.update_gdpr_request(
            self.request_id,
            "denied",
            interaction.user.id,
            str(self.reason)
        )

        # Get the request data
        request = await interaction.client.database.get_gdpr_request(self.request_id)
        if not request:
            error_embed = discord.Embed(
                title="❌ Request Not Found",
                description="The GDPR request could not be found in the database.",
                color=0xE74C3C
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return

        # Notify the original requester
        try:
            requester = await interaction.client.fetch_user(int(request["requester_id"]))
            if requester:
                embed = discord.Embed(
                    title="❌ GDPR Data Request Denied",
                    description="Your data request has been denied by an administrator.",
                    color=0xE74C3C
                )
                embed.add_field(
                    name="📝 Request Details",
                    value=(
                        f"**Request ID:** `{self.request_id}`\n"
                        f"**Denied At:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                        f"**Reason:** {str(self.reason)}"
                    ),
                    inline=False
                )
                embed.set_footer(text="You may submit a new request after 24 hours.")
                await requester.send(embed=embed)
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Error Notifying User",
                description=f"Failed to notify the requester:\n```{str(e)}```",
                color=0xE74C3C
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return

        # Disable all buttons in the original message
        view = GDPRReviewButtons(self.request_id)
        for child in view.children:
            child.disabled = True

        await interaction.message.edit(view=view)
        
        success_embed = discord.Embed(
            title="✅ Request Processed",
            description="The GDPR request has been denied and the user has been notified.",
            color=0x2ECC71
        )
        success_embed.add_field(
            name="📝 Denial Details",
            value=f"**Reason:** {str(self.reason)}",
            inline=False
        )
        success_embed.set_footer(text=f"Request ID: {self.request_id}")
        await interaction.response.send_message(embed=success_embed, ephemeral=True)


async def setup(bot) -> None:
    await bot.add_cog(General(bot))
