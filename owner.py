from datetime import datetime
import discord
from discord.ext import commands
from discord.ext.commands import Context

class OwnerCog(commands.Cog):
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