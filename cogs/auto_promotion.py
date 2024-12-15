import discord
from discord.ext import commands
import aiohttp
import os
import asyncio
import logging

# Configure logging to display only errors
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

class AutoPromotion(commands.Cog, name="AutoPromotion"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = None
        self.promote_api_url = os.getenv("PROMOTE_API_URL", "http://37.60.250.231:3002/promote")
        self.promote_api_token = os.getenv("PROMOTE_API_TOKEN")
        self.api_key = os.getenv("API_KEY")  # Ensure API_KEY is fetched here
        self.roblox_user_lookup_endpoint = "https://users.roblox.com/v1/usernames/users"

    async def cog_load(self):
        self.db = getattr(self.bot, 'database', None)
        if self.db is None:
            logger.error("Database connection not found. AutoPromotion cog will not function properly.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore messages from bots, DMs, or if database is not initialized
        if message.author.bot or not message.guild or not self.db:
            return

        try:
            channel_id = await self.db.get_autopromotion_channel_id(message.guild.id)
        except Exception as e:
            logger.error(f"Error fetching autopromotion channel ID: {e}")
            return

        if channel_id is None or message.channel.id != channel_id:
            return

        # Find "Passed:" line
        passed_line = None
        for line in message.content.split('\n'):
            if line.strip().lower().startswith("passed:"):
                passed_line = line.strip()
                break

        if not passed_line:
            return

        passed_part = passed_line.split(":", 1)[1].strip() if ":" in passed_line else ""
        if not passed_part:
            return
        passed_usernames = [u.strip() for u in passed_part.split(",") if u.strip()]

        if not passed_usernames:
            return

        # Prompt for confirmation
        passed_embed = discord.Embed(
            title="Passed Users",
            description="The following users have passed:\n" + "\n".join(passed_usernames),
            color=discord.Color.blue()
        )
        passed_embed.set_footer(text="React with ✅ to confirm promotions.")

        try:
            reply_msg = await message.reply(embed=passed_embed)
        except discord.DiscordException as e:
            logger.error(f"Error sending confirmation embed: {e}")
            return

        try:
            await reply_msg.add_reaction("✅")
        except discord.DiscordException as e:
            logger.error(f"Error adding reaction: {e}")
            return

        def check(reaction: discord.Reaction, user: discord.User):
            return (
                reaction.message.id == reply_msg.id and
                str(reaction.emoji) == "✅" and
                not user.bot
            )

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=180.0, check=check)
        except asyncio.TimeoutError:
            timeout_embed = discord.Embed(
                title="No Confirmation",
                description="No confirmation received. Promotion process timed out.",
                color=discord.Color.red()
            )
            try:
                await reply_msg.reply(embed=timeout_embed)
            except discord.DiscordException as e:
                logger.error(f"Error sending timeout embed: {e}")
            return
        except discord.DiscordException as e:
            logger.error(f"Error waiting for reaction: {e}")
            return

        # Delete only the confirmation embed message (reply_msg)
        try:
            await reply_msg.delete()
        except discord.DiscordException as e:
            logger.error(f"Error deleting confirmation message: {e}")

        # Proceed with promotions
        try:
            processing_embed = discord.Embed(
                title="Processing Promotions",
                description="Attempting to promote all passed users...",
                color=discord.Color.yellow()
            )
            processing_msg = await message.channel.send(embed=processing_embed)
        except discord.DiscordException as e:
            logger.error(f"Error sending processing embed: {e}")
            return

        results = []
        if not self.promote_api_token:
            logger.error("Promote API token not configured.")
            results = [(uname, False, "No API token configured") for uname in passed_usernames]
        else:
            try:
                async with aiohttp.ClientSession() as session:
                    # Fetch Roblox IDs
                    roblox_ids_map = await self.fetch_roblox_ids_bulk(session, passed_usernames)
                    
                    for uname in passed_usernames:
                        roblox_id = roblox_ids_map.get(uname.lower())
                        if roblox_id is None:
                            results.append((uname, False, "Roblox user not found"))
                            continue

                        success, msg = await self.promote_user(session, roblox_id)

                        if success:
                            results.append((uname, True, "Promoted"))
                        else:
                            results.append((uname, False, f"Failed: {msg}"))
            except Exception as e:
                logger.error(f"Unexpected error during promotion: {e}")
                if not results:
                    results = [(uname, False, "Unexpected error during promotion") for uname in passed_usernames]

        success_count = sum(1 for r in results if r[1])
        fail_count = len(results) - success_count
        results_lines = [f"{uname}: {msg} {'✅' if success else '❌'}" for uname, success, msg in results]

        final_color = discord.Color.green() if fail_count == 0 else discord.Color.red()
        results_embed = discord.Embed(
            title="Promotion Results",
            description="\n".join(results_lines),
            color=final_color
        )
        results_embed.add_field(name="Summary", value=f"Success: {success_count}\nFailed: {fail_count}", inline=False)

        try:
            await processing_msg.edit(embed=results_embed)
        except discord.DiscordException as e:
            logger.error(f"Error editing processing embed with results: {e}")

    async def fetch_roblox_ids_bulk(self, session: aiohttp.ClientSession, usernames: list):
        url = self.roblox_user_lookup_endpoint
        payload = {
            "usernames": usernames,
            "excludeBannedUsers": True
        }
        ids_map = {}
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for user_data in data.get("data", []):
                        uname = user_data.get("requestedUsername", "").lower()
                        uid = user_data.get("id")
                        if uid is not None:
                            ids_map[uname] = uid
                else:
                    logger.error(f"Failed to fetch Roblox IDs. HTTP Status: {resp.status}")
        except aiohttp.ClientError as e:
            logger.error(f"HTTP request error while fetching Roblox IDs: {e}")
        except Exception as e:
            logger.error(f"Unexpected error while fetching Roblox IDs: {e}")
        return ids_map

    async def promote_user(self, session: aiohttp.ClientSession, roblox_id: int):
        if not self.api_key:
            logger.error("API_KEY is not set. Cannot promote user.")
            return False, "API key not configured"

        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key  # Direct API key without 'Bearer' prefix
        }
        payload = {"id": str(roblox_id)}

        try:
            async with session.post(self.promote_api_url, headers=headers, json=payload) as resp:
                try:
                    data = await resp.json()
                    response_msg = data.get("msg") or data.get("error") or ""
                except aiohttp.ContentTypeError:
                    # Response is not JSON
                    response_msg = await resp.text()

                if resp.status == 200:
                    return True, "Promoted"
                else:
                    fail_reason = response_msg.strip() or f"HTTP {resp.status}"
                    logger.error(f"Promotion failed for Roblox ID {roblox_id}: {fail_reason}")
                    return False, fail_reason
        except aiohttp.ClientError as e:
            logger.error(f"HTTP request error while promoting Roblox ID {roblox_id}: {e}")
            return False, "Request Exception"
        except Exception as e:
            logger.error(f"Unexpected error while promoting Roblox ID {roblox_id}: {e}")
            return False, "Unexpected Error"

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoPromotion(bot))