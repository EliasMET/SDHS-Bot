"""
Copyright © Krypton 2019-Present - https://github.com/kkrypt0nn (https://krypton.ninja)
Description:
🐍 A simple template to start to code your own and personalized Discord bot in Python

Version: 6.2.0
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context
from datetime import datetime


class Owner(commands.Cog, name="owner"):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.command(
        name="sync",
        description="Synchronizes the slash commands.",
    )
    @app_commands.describe(scope="The scope of the sync. Can be `global` or `guild`")
    @commands.is_owner()
    async def sync(self, context: Context, scope: str) -> None:
        """
        Synchronizes the slash commands.

        :param context: The command context.
        :param scope: The scope of the sync. Can be `global` or `guild`.
        """

        if scope == "global":
            await context.bot.tree.sync()
            embed = discord.Embed(
                description="Slash commands have been globally synchronized.",
                color=0xBEBEFE,
            )
            await context.send(embed=embed)
            return
        elif scope == "guild":
            context.bot.tree.copy_global_to(guild=context.guild)
            await context.bot.tree.sync(guild=context.guild)
            embed = discord.Embed(
                description="Slash commands have been synchronized in this guild.",
                color=0xBEBEFE,
            )
            await context.send(embed=embed)
            return
        embed = discord.Embed(
            description="The scope must be `global` or `guild`.", color=0xE02B2B
        )
        await context.send(embed=embed)

    @commands.command(
        name="unsync",
        description="Unsynchronizes the slash commands.",
    )
    @app_commands.describe(
        scope="The scope of the sync. Can be `global`, `current_guild` or `guild`"
    )
    @commands.is_owner()
    async def unsync(self, context: Context, scope: str) -> None:
        """
        Unsynchronizes the slash commands.

        :param context: The command context.
        :param scope: The scope of the sync. Can be `global`, `current_guild` or `guild`.
        """

        if scope == "global":
            context.bot.tree.clear_commands(guild=None)
            await context.bot.tree.sync()
            embed = discord.Embed(
                description="Slash commands have been globally unsynchronized.",
                color=0xBEBEFE,
            )
            await context.send(embed=embed)
            return
        elif scope == "guild":
            context.bot.tree.clear_commands(guild=context.guild)
            await context.bot.tree.sync(guild=context.guild)
            embed = discord.Embed(
                description="Slash commands have been unsynchronized in this guild.",
                color=0xBEBEFE,
            )
            await context.send(embed=embed)
            return
        embed = discord.Embed(
            description="The scope must be `global` or `guild`.", color=0xE02B2B
        )
        await context.send(embed=embed)

    @commands.hybrid_command(
        name="load",
        description="Load a cog",
    )
    @app_commands.describe(cog="The name of the cog to load")
    @commands.is_owner()
    async def load(self, context: Context, cog: str) -> None:
        """
        The bot will load the given cog.

        :param context: The hybrid command context.
        :param cog: The name of the cog to load.
        """
        try:
            await self.bot.load_extension(f"cogs.{cog}")
        except Exception as e:
            embed = discord.Embed(
                description=f"Could not load the `{cog}` cog.\nError: {e}",
                color=0xE02B2B,
            )
            await context.send(embed=embed)
            return
        embed = discord.Embed(
            description=f"Successfully loaded the `{cog}` cog.",
            color=0xBEBEFE,
        )
        await context.send(embed=embed)

    @commands.hybrid_command(
        name="unload",
        description="Unloads a cog.",
    )
    @app_commands.describe(cog="The name of the cog to unload")
    @commands.is_owner()
    async def unload(self, context: Context, cog: str) -> None:
        """
        The bot will unload the given cog.

        :param context: The hybrid command context.
        :param cog: The name of the cog to unload.
        """
        try:
            await self.bot.unload_extension(f"cogs.{cog}")
        except Exception as e:
            embed = discord.Embed(
                description=f"Could not unload the `{cog}` cog.\nError: {e}",
                color=0xE02B2B,
            )
            await context.send(embed=embed)
            return
        embed = discord.Embed(
            description=f"Successfully unloaded the `{cog}` cog.",
            color=0xBEBEFE,
        )
        await context.send(embed=embed)

    @commands.hybrid_command(
        name="reload",
        description="Reloads a cog.",
    )
    @app_commands.describe(cog="The name of the cog to reload")
    @commands.is_owner()
    async def reload(self, context: Context, cog: str) -> None:
        """
        The bot will reload the given cog.

        :param context: The hybrid command context.
        :param cog: The name of the cog to reload.
        """
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
        except Exception as e:
            embed = discord.Embed(
                description=f"Could not reload the `{cog}` cog.\nError: {e}",
                color=0xE02B2B,
            )
            await context.send(embed=embed)
            return
        embed = discord.Embed(
            description=f"Successfully reloaded the `{cog}` cog.",
            color=0xBEBEFE,
        )
        await context.send(embed=embed)

    @commands.hybrid_command(
        name="shutdown",
        description="Make the bot shutdown.",
    )
    @commands.is_owner()
    async def shutdown(self, context: Context) -> None:
        """
        Shuts down the bot.

        :param context: The hybrid command context.
        """
        embed = discord.Embed(description="Shutting down. Bye! :wave:", color=0xBEBEFE)
        await context.send(embed=embed)
        await self.bot.close()

    @commands.hybrid_command(
        name="say",
        description="The bot will say anything you want.",
    )
    @app_commands.describe(message="The message that should be repeated by the bot")
    @commands.is_owner()
    async def say(self, context: Context, *, message: str) -> None:
        """
        The bot will say anything you want.

        :param context: The hybrid command context.
        :param message: The message that should be repeated by the bot.
        """
        await context.send(message)

    @commands.hybrid_command(
        name="action",
        description="Look up details of a tryout or moderation action"
    )
    @commands.is_owner()
    async def action(self, context: Context, action_id: str) -> None:
        """
        Look up details of a tryout session or moderation action.
        Only available to the bot owner.

        :param context: The hybrid command context.
        :param action_id: The ID of the action to look up.
        """
        try:
            from bson import ObjectId
            try:
                # Validate ObjectId format
                ObjectId(action_id)
            except Exception:
                embed = discord.Embed(
                    title="❌ Error",
                    description="Invalid action ID format.",
                    color=0xE02B2B
                )
                await context.send(embed=embed)
                return

            # Get the session using the string ID
            session = await self.bot.database.get_tryout_session(action_id)
            if not session:
                embed = discord.Embed(
                    title="❌ Error",
                    description="Action not found.",
                    color=0xE02B2B
                )
                await context.send(embed=embed)
                return

            # Create embed with session details
            embed = discord.Embed(
                title=f"🎯 Action Details",
                description=f"Action ID: `{action_id}`",
                color=0xBEBEFE
            )

            # Get host info
            host = context.guild.get_member(int(session["host_id"]))
            host_name = host.mention if host else "Unknown Host"

            # Format timestamps - ensure UTC
            created_at = datetime.fromisoformat(session["created_at"])
            lock_time = datetime.fromisoformat(session["lock_timestamp"])
            
            # Add fields
            embed.add_field(
                name="📋 Basic Info",
                value=(
                    f"**Group:** {session['group_name']}\n"
                    f"**Host:** {host_name}\n"
                    f"**Status:** {'🟢 Active' if session['status'] == 'active' else '🔴 Ended'}\n"
                    f"**Created:** <t:{int(created_at.timestamp())}:F>\n"
                    f"**Locks:** <t:{int(lock_time.timestamp())}:F>"
                ),
                inline=False
            )

            if session.get("description"):
                embed.add_field(
                    name="📄 Description",
                    value=session["description"],
                    inline=False
                )

            if session.get("requirements"):
                embed.add_field(
                    name="📝 Requirements",
                    value="\n".join(f"• {req}" for req in session["requirements"]) or "None",
                    inline=False
                )

            # Add voice channel info if available
            if session.get("voice_channel_id"):
                embed.add_field(
                    name="🔊 Voice Channel",
                    value=f"<#{session['voice_channel_id']}>",
                    inline=False
                )
                if session.get("voice_invite"):
                    embed.add_field(
                        name="🔗 Voice Invite",
                        value=session["voice_invite"],
                        inline=False
                    )

            # Add end info if session is ended
            if session.get("ended_at"):
                ended_at = datetime.fromisoformat(session["ended_at"])
                embed.add_field(
                    name="🏁 End Info",
                    value=(
                        f"**Ended:** <t:{int(ended_at.timestamp())}:F>\n"
                        f"**Reason:** {session.get('end_reason', 'Not specified')}"
                    ),
                    inline=False
                )

            await context.send(embed=embed)

        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred while looking up the action: {str(e)}",
                color=0xE02B2B
            )
            await context.send(embed=embed)


async def setup(bot) -> None:
    await bot.add_cog(Owner(bot))
