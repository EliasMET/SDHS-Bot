import platform

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
            if cog_name == "owner" and not (await self.bot.is_owner(context.author)):
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
        embed = discord.Embed(
            description="Made for SDHS",
            color=0xBEBEFE,
        )
        embed.set_author(name="Bot Information")
        embed.add_field(name="Owner:", value="elias_5", inline=True)
        embed.add_field(
            name="Python Version:", value=f"{platform.python_version()}", inline=True
        )
        embed.add_field(
            name="Prefix:",
            value=f"/ (Slash Commands) or {self.bot.config['prefix']} for normal commands",
            inline=False,
        )
        embed.set_footer(text=f"Requested by {context.author}")
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


async def setup(bot) -> None:
    await bot.add_cog(General(bot))
