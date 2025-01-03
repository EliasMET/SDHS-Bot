import json
import logging
import os
import platform
import random
import sys
from datetime import datetime

import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context
from dotenv import load_dotenv
from database import DatabaseManager
import motor.motor_asyncio

load_dotenv()

if not os.path.isfile(f"{os.path.realpath(os.path.dirname(__file__))}/config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
else:
    with open(f"{os.path.realpath(os.path.dirname(__file__))}/config.json") as file:
        config = json.load(file)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = True

class LoggingFormatter(logging.Formatter):
    black = "\x1b[30m"
    red = "\x1b[31m"
    green = "\x1b[32m"
    yellow = "\x1b[33m"
    blue = "\x1b[34m"
    gray = "\x1b[38m"
    reset = "\x1b[0m"
    bold = "\x1b[1m"

    COLORS = {
        logging.DEBUG: gray + bold,
        logging.INFO: blue + bold,
        logging.WARNING: yellow + bold,
        logging.ERROR: red,
        logging.CRITICAL: red + bold,
    }

    def format(self, record):
        log_color = self.COLORS.get(record.levelno, self.reset)
        format = "(black){asctime}(reset) (levelcolor){levelname:<8}(reset) (green){name}(reset) {message}"
        format = format.replace("(black)", self.black + self.bold)
        format = format.replace("(reset)", self.reset)
        format = format.replace("(levelcolor)", log_color)
        format = format.replace("(green)", self.green + self.bold)
        formatter = logging.Formatter(format, "%Y-%m-%d %H:%M:%S", style="{")
        return formatter.format(record)

logger = logging.getLogger("discord_bot")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(LoggingFormatter())

file_handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")
file_handler_formatter = logging.Formatter(
    "[{asctime}] [{levelname:<8}] {name}: {message}", "%Y-%m-%d %H:%M:%S", style="{"
)
file_handler.setFormatter(file_handler_formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

class DiscordBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned_or(config["prefix"]),
            intents=intents,
            help_command=None,
        )
        self.logger = logger
        self.config = config
        self.database = None
        self.start_time = datetime.utcnow()
        self.command_count = 0
        self.message_count = 0

    async def init_db(self) -> None:
        mongo_uri = os.getenv("MONGODB_URI")
        mongo_db_name = os.getenv("MONGODB_NAME")
        if not mongo_uri or not mongo_db_name:
            self.logger.error("MongoDB configuration not found in .env")
            sys.exit("MongoDB configuration missing.")

        self.logger.info("Connecting to MongoDB...")
        mongo_client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
        mongo_db = mongo_client[mongo_db_name]

        self.database = DatabaseManager(db=mongo_db)
        await self.database.initialize_database()
        self.logger.info("MongoDB initialization complete.")

    async def load_cogs(self) -> None:
        for file in os.listdir(f"{os.path.realpath(os.path.dirname(__file__))}/cogs"):
            if file.endswith(".py"):
                extension = file[:-3]
                try:
                    await self.load_extension(f"cogs.{extension}")
                    self.logger.info(f"Loaded extension '{extension}'")
                except Exception as e:
                    exception = f"{type(e).__name__}: {e}"
                    self.logger.error(f"Failed to load extension {extension}\n{exception}")

#   @tasks.loop(minutes=1.0)
#   async def status_task(self) -> None:
#       statuses = ["with ranks"]
#       await self.change_presence(activity=discord.Game(random.choice(statuses)))
#
#    @status_task.before_loop
#    async def before_status_task(self) -> None:
#        await self.wait_until_ready()

    async def setup_hook(self) -> None:
        self.logger.info(f"Logged in as {self.user.name}")
        self.logger.info(f"discord.py API version: {discord.__version__}")
        self.logger.info(f"Python version: {platform.python_version()}")
        self.logger.info(f"Running on: {platform.system()} {platform.release()} ({os.name})")
        self.logger.info("-------------------")

        await self.init_db()

        self.logger.info("Database ready.")
        await self.load_cogs()
#        self.status_task.start()

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user or message.author.bot:
            return
        self.message_count += 1
        await self.process_commands(message)

    async def on_command_completion(self, context: Context) -> None:
        self.command_count += 1
        full_command_name = context.command.qualified_name
        split = full_command_name.split(" ")
        executed_command = str(split[0])

        # Get user roles and permissions
        roles = []
        permissions = []
        is_admin = False
        if context.guild:
            roles = [f"{role.name} ({role.id})" for role in context.author.roles]
            permissions = [perm[0] for perm, value in context.author.guild_permissions if value]
            is_admin = context.author.guild_permissions.administrator

        # Create detailed log entry
        log_data = {
            "command": executed_command,
            "full_command": context.message.content,
            "user_id": context.author.id,
            "user_name": str(context.author),
            "channel_id": context.channel.id if hasattr(context.channel, 'id') else None,
            "channel_name": context.channel.name if hasattr(context.channel, 'name') else "DM",
            "guild_id": context.guild.id if context.guild else None,
            "guild_name": context.guild.name if context.guild else "DM",
            "timestamp": datetime.utcnow().isoformat(),
            "roles": roles,
            "permissions": permissions,
            "is_admin": is_admin,
            "is_owner": await self.is_owner(context.author),
            "success": True
        }

        # Log to database
        try:
            await self.database.log_command(log_data)
        except Exception as e:
            self.logger.error(f"Failed to log command to database: {str(e)}")

        # Log to console with color formatting
        if context.guild:
            self.logger.info(
                f"Command executed: {log_data['command']} | "
                f"By: {context.author} ({context.author.id}) | "
                f"In: {context.guild.name} ({context.guild.id}) - #{context.channel.name} | "
                f"Admin: {is_admin} | "
                f"Owner: {log_data['is_owner']} | "
                f"Success: {log_data['success']}"
            )
        else:
            self.logger.info(
                f"Command executed: {log_data['command']} | "
                f"By: {context.author} ({context.author.id}) | "
                f"In: DMs | "
                f"Owner: {log_data['is_owner']} | "
                f"Success: {log_data['success']}"
            )

    async def on_command_error(self, context: Context, error) -> None:
        # Log command error
        full_command_name = context.command.qualified_name if context.command else "Unknown"
        split = full_command_name.split(" ")
        executed_command = str(split[0])

        # Get user roles and permissions
        roles = []
        permissions = []
        is_admin = False
        if context.guild:
            roles = [f"{role.name} ({role.id})" for role in context.author.roles]
            permissions = [perm[0] for perm, value in context.author.guild_permissions if value]
            is_admin = context.author.guild_permissions.administrator

        # Create error log entry
        log_data = {
            "command": executed_command,
            "full_command": context.message.content,
            "user_id": context.author.id,
            "user_name": str(context.author),
            "channel_id": context.channel.id if hasattr(context.channel, 'id') else None,
            "channel_name": context.channel.name if hasattr(context.channel, 'name') else "DM",
            "guild_id": context.guild.id if context.guild else None,
            "guild_name": context.guild.name if context.guild else "DM",
            "timestamp": datetime.utcnow().isoformat(),
            "roles": roles,
            "permissions": permissions,
            "is_admin": is_admin,
            "is_owner": await self.is_owner(context.author),
            "success": False,
            "error": str(error),
            "error_type": type(error).__name__
        }

        # Log to database
        try:
            await self.database.log_command(log_data)
        except Exception as e:
            self.logger.error(f"Failed to log command error to database: {str(e)}")

        # Log error to console
        if context.guild:
            self.logger.error(
                f"Command failed: {log_data['command']} | "
                f"By: {context.author} ({context.author.id}) | "
                f"In: {context.guild.name} ({context.guild.id}) - #{context.channel.name} | "
                f"Error: {log_data['error_type']}"
            )
        else:
            self.logger.error(
                f"Command failed: {log_data['command']} | "
                f"By: {context.author} ({context.author.id}) | "
                f"In: DMs | "
                f"Error: {log_data['error_type']}"
            )

        # Handle specific error types with embeds
        if isinstance(error, commands.CommandOnCooldown):
            minutes, seconds = divmod(error.retry_after, 60)
            hours, minutes = divmod(minutes, 60)
            hours = hours % 24
            embed = discord.Embed(
                description=f"**Please slow down** - You can use this command again in {f'{round(hours)} hours' if round(hours) > 0 else ''} {f'{round(minutes)} minutes' if round(minutes) > 0 else ''} {f'{round(seconds)} seconds' if round(seconds) > 0 else ''}.",
                color=0xE02B2B,
            )
            await context.send(embed=embed)
        elif isinstance(error, commands.NotOwner):
            embed = discord.Embed(
                description="You are not the owner of the bot!", color=0xE02B2B
            )
            await context.send(embed=embed)
        elif isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                description="You are missing the permission(s) `"
                + ", ".join(error.missing_permissions)
                + "` to execute this command!",
                color=0xE02B2B,
            )
            await context.send(embed=embed)
        elif isinstance(error, commands.BotMissingPermissions):
            embed = discord.Embed(
                description="I am missing the permission(s) `"
                + ", ".join(error.missing_permissions)
                + "` to fully perform this command!",
                color=0xE02B2B,
            )
            await context.send(embed=embed)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="Error!",
                description=str(error).capitalize(),
                color=0xE02B2B,
            )
            await context.send(embed=embed)
        else:
            raise error

bot = DiscordBot()
bot.run(os.getenv("TOKEN"))
