import logging
import random
import string
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError
from typing import Optional

class DatabaseManager:
    def __init__(self, *, db: AsyncIOMotorDatabase) -> None:
        self.db = db
        self.logger = logging.getLogger('DatabaseManager')

    async def initialize_database(self):
        """Initialize database with optimized collections and indexes"""
        try:
            # Create indexes for tryout tracking
            await self.db["tryout_sessions"].create_index([("guild_id", 1)])
            await self.db["tryout_sessions"].create_index([("host_id", 1)])
            await self.db["tryout_sessions"].create_index([("group_id", 1)])
            await self.db["tryout_sessions"].create_index([("status", 1)])
            await self.db["tryout_sessions"].create_index([("created_at", -1)])
            await self.db["tryout_sessions"].create_index([("lock_timestamp", 1)])
            await self.db["tryout_sessions"].create_index([
                ("guild_id", 1),
                ("created_at", -1)
            ])

            # Original indexes
            await self.db["warns"].create_index([("user_id", 1), ("server_id", 1)])
            await self.db["server_data"].create_index([("server_id", 1)], unique=True)
            await self.db["cases"].create_index(
                [("server_id", 1), ("case_id", 1)],
                unique=True
            )
            await self.db["gdpr_requests"].create_index([("request_id", 1)], unique=True)
            await self.db["gdpr_requests"].create_index([("requester_id", 1)])
            await self.db["gdpr_requests"].create_index([("target_user_id", 1)])
            await self.db["command_logs"].create_index([("timestamp", -1)])
            await self.db["command_logs"].create_index([("user_id", 1)])
            await self.db["command_logs"].create_index([("guild_id", 1)])
            await self.db["command_logs"].create_index([("command", 1)])
            await self.db["command_logs"].create_index([("success", 1)])

            self.logger.info("Database initialized with all collections and indexes.")
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise

    #
    # ------------- WARN SYSTEM -------------
    #
    async def add_warn(self, user_id: int, server_id: int, moderator_id: int, reason: str) -> int:
        last_warn = await self.db["warns"].find({
            "user_id": str(user_id),
            "server_id": str(server_id)
        }).sort("id", -1).limit(1).to_list(1)

        warn_id = (last_warn[0]["id"] if last_warn else 0) + 1
        doc = {
            "id": warn_id,
            "user_id": str(user_id),
            "server_id": str(server_id),
            "moderator_id": str(moderator_id),
            "reason": reason,
            "created_at": datetime.utcnow().isoformat()
        }
        await self.db["warns"].insert_one(doc)
        return warn_id

    async def remove_warn(self, warn_id: int, user_id: int, server_id: int) -> bool:
        result = await self.db["warns"].delete_one({
            "id": warn_id,
            "user_id": str(user_id),
            "server_id": str(server_id)
        })
        return result.deleted_count > 0

    async def get_all_warnings(self) -> list:
        warnings = await self.db["warns"].find({}).to_list(None)
        for w in warnings:
            w["created_at"] = str(int(datetime.fromisoformat(w["created_at"]).timestamp()))
        return [
            (w["user_id"], w["server_id"], w["moderator_id"], w["reason"], w["created_at"], w["id"])
            for w in warnings
        ]

    async def get_warnings(self, user_id: int, server_id: int) -> list:
        warnings = await self.db["warns"].find({
            "user_id": str(user_id),
            "server_id": str(server_id)
        }).to_list(None)
        for w in warnings:
            w["created_at"] = str(int(datetime.fromisoformat(w["created_at"]).timestamp()))
        return [
            (w["user_id"], w["server_id"], w["moderator_id"], w["reason"], w["created_at"], w["id"])
            for w in warnings
        ]

    async def clear_all_warnings(self, user_id: int, server_id: int) -> int:
        result = await self.db["warns"].delete_many({
            "user_id": str(user_id),
            "server_id": str(server_id)
        })
        return result.deleted_count

    async def count_warnings(self, user_id: int, server_id: int) -> int:
        return await self.db["warns"].count_documents({
            "user_id": str(user_id),
            "server_id": str(server_id)
        })

    async def remove_expired_warnings(self, expiration_timestamp: int) -> int:
        all_warnings = await self.db["warns"].find({}).to_list(None)
        to_remove_ids = []
        for w in all_warnings:
            ts = int(datetime.fromisoformat(w["created_at"]).timestamp())
            if ts < expiration_timestamp:
                to_remove_ids.append(w["_id"])
        removed = 0
        if to_remove_ids:
            result = await self.db["warns"].delete_many({"_id": {"$in": to_remove_ids}})
            removed = result.deleted_count
        return removed

    #
    # ------------- SERVER DATA -------------
    #
    async def _get_server_data(self, server_id: int) -> dict:
        data = await self.db["server_data"].find_one({"server_id": str(server_id)})
        if not data:
            # Initialize defaults
            data = {
                "server_id": str(server_id),
                "settings": {
                    "automod_enabled": True,
                    "automod_logging_enabled": False,
                    "automod_log_channel_id": None,
                    "tryout_channel_id": None,
                    "tryout_log_channel_id": None,
                    "mod_log_channel_id": None,
                    "automod_mute_duration": 3600,
                    "automod_spam_limit": 5,
                    "automod_spam_window": 5
                },
                "tryout_groups": [],
                "tryout_required_roles": [],
                "moderation_allowed_roles": [],
                "locked_channels": [],
                "automod_exempt_roles": [],
                "protected_users": [],
                "tryout_allowed_vcs": [],
                "autopromotion_channel_id": None
            }
            await self.db["server_data"].insert_one(data)
        else:
            # Ensure any newly introduced fields exist
            changed = False
            if "automod_spam_limit" not in data["settings"]:
                data["settings"]["automod_spam_limit"] = 5
                changed = True
            if "automod_spam_window" not in data["settings"]:
                data["settings"]["automod_spam_window"] = 5
                changed = True
            if "tryout_allowed_vcs" not in data:
                data["tryout_allowed_vcs"] = []
                changed = True
            if "autopromotion_channel_id" not in data:
                data["autopromotion_channel_id"] = None
                changed = True
            if "automod_exempt_roles" not in data:
                data["automod_exempt_roles"] = []
                changed = True
            # Remove old ping_roles field if it exists
            if "ping_roles" in data:
                del data["ping_roles"]
                changed = True
            # Add global_bans_enabled if it doesn't exist
            if "global_bans_enabled" not in data["settings"]:
                data["settings"]["global_bans_enabled"] = False
                changed = True
            if changed:
                await self._update_server_data(server_id, data)
        return data

    async def _update_server_data(self, server_id: int, update: dict):
        await self.db["server_data"].update_one(
            {"server_id": str(server_id)},
            {"$set": update},
            upsert=True
        )

    async def initialize_server_settings(self, server_id: int):
        await self._get_server_data(server_id)

    async def get_server_settings(self, server_id: int) -> dict:
        data = await self._get_server_data(server_id)
        s = data["settings"]
        return {
            'automod_enabled': bool(s.get('automod_enabled', True)),
            'automod_logging_enabled': bool(s.get('automod_logging_enabled', False)),
            'automod_log_channel_id': int(s['automod_log_channel_id']) if s.get('automod_log_channel_id') else None,
            'tryout_channel_id': int(s['tryout_channel_id']) if s.get('tryout_channel_id') else None,
            'mod_log_channel_id': int(s['mod_log_channel_id']) if s.get('mod_log_channel_id') else None,
            'automod_mute_duration': int(s.get('automod_mute_duration', 3600)),
            'automod_spam_limit': int(s.get('automod_spam_limit', 5)),
            'automod_spam_window': int(s.get('automod_spam_window', 5)),
            'global_bans_enabled': bool(s.get('global_bans_enabled', True))
        }

    async def update_server_setting(self, server_id: int, setting_name: str, value):
        data = await self._get_server_data(server_id)
        data["settings"][setting_name] = value
        await self._update_server_data(server_id, {"settings": data["settings"]})

    async def toggle_server_setting(self, server_id: int, setting_name: str):
        current_settings = await self.get_server_settings(server_id)
        current_value = current_settings.get(setting_name)
        if isinstance(current_value, bool):
            new_value = not current_value
        elif isinstance(current_value, (int, float)):
            new_value = 0 if current_value else 1
        else:
            new_value = True
        await self.update_server_setting(server_id, setting_name, new_value)

    async def get_automod_mute_duration(self, server_id: int) -> int:
        settings = await self.get_server_settings(server_id)
        return settings.get('automod_mute_duration', 3600)

    async def set_automod_mute_duration(self, server_id: int, duration: int):
        await self.update_server_setting(server_id, "automod_mute_duration", duration)

    async def get_automod_spam_limit(self, server_id: int) -> int:
        settings = await self.get_server_settings(server_id)
        return settings.get('automod_spam_limit', 5)

    async def set_automod_spam_limit(self, server_id: int, limit: int):
        await self.update_server_setting(server_id, "automod_spam_limit", limit)

    async def get_automod_spam_window(self, server_id: int) -> int:
        settings = await self.get_server_settings(server_id)
        return settings.get('automod_spam_window', 5)

    async def set_automod_spam_window(self, server_id: int, window: int):
        await self.update_server_setting(server_id, "automod_spam_window", window)

    async def get_protected_users(self, server_id: int) -> list:
        data = await self._get_server_data(server_id)
        return [int(u) for u in data["protected_users"]]

    async def add_protected_user(self, server_id: int, user_id: int):
        data = await self._get_server_data(server_id)
        if str(user_id) not in data["protected_users"]:
            data["protected_users"].append(str(user_id))
            await self._update_server_data(server_id, {"protected_users": data["protected_users"]})

    async def remove_protected_user(self, server_id: int, user_id: int):
        data = await self._get_server_data(server_id)
        if str(user_id) in data["protected_users"]:
            data["protected_users"].remove(str(user_id))
            await self._update_server_data(server_id, {"protected_users": data["protected_users"]})

    async def get_automod_exempt_roles(self, server_id: int) -> list:
        data = await self._get_server_data(server_id)
        return [int(r) for r in data["automod_exempt_roles"]]

    async def add_automod_exempt_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid in data["automod_exempt_roles"]:
            raise RuntimeError(f"Automod exempt role {role_id} already exists.")
        data["automod_exempt_roles"].append(rid)
        await self._update_server_data(server_id, {"automod_exempt_roles": data["automod_exempt_roles"]})

    async def remove_automod_exempt_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid in data["automod_exempt_roles"]:
            data["automod_exempt_roles"].remove(rid)
            await self._update_server_data(server_id, {"automod_exempt_roles": data["automod_exempt_roles"]})

    async def get_moderation_allowed_roles(self, server_id: int) -> list:
        data = await self._get_server_data(server_id)
        return [int(r) for r in data["moderation_allowed_roles"]]

    async def add_moderation_allowed_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid not in data["moderation_allowed_roles"]:
            data["moderation_allowed_roles"].append(rid)
            await self._update_server_data(server_id, {"moderation_allowed_roles": data["moderation_allowed_roles"]})

    async def remove_moderation_allowed_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid in data["moderation_allowed_roles"]:
            data["moderation_allowed_roles"].remove(rid)
            await self._update_server_data(server_id, {"moderation_allowed_roles": data["moderation_allowed_roles"]})

    async def set_mod_log_channel(self, server_id: int, channel_id: int):
        data = await self._get_server_data(server_id)
        data["settings"]["mod_log_channel_id"] = str(channel_id)
        await self._update_server_data(server_id, {"settings": data["settings"]})

    async def get_mod_log_channel(self, server_id: int) -> int:
        settings = await self.get_server_settings(server_id)
        return settings.get("mod_log_channel_id")

    async def get_tryout_groups(self, server_id: int) -> list:
        data = await self._get_server_data(server_id)
        groups = data.get("tryout_groups", [])
        return [(g["group_id"], g["description"], g["event_name"], g.get("requirements", []), g.get("ping_roles", [])) for g in groups]

    async def get_tryout_group(self, server_id: int, group_id: str):
        data = await self._get_server_data(server_id)
        for g in data["tryout_groups"]:
            if g["group_id"] == group_id:
                return (g["group_id"], g["description"], g["event_name"], g.get("requirements", []), g.get("ping_roles", []))
        return None

    async def add_tryout_group(self, server_id: int, group_id: str, description: str, event_name: str, requirements: list):
        data = await self._get_server_data(server_id)
        for g in data["tryout_groups"]:
            if g["group_id"] == group_id:
                raise RuntimeError(f"Tryout group '{group_id}' already exists.")
        data["tryout_groups"].append({
            "group_id": group_id,
            "description": description,
            "event_name": event_name,
            "requirements": requirements,
            "ping_roles": []
        })
        await self._update_server_data(server_id, {"tryout_groups": data["tryout_groups"]})

    async def update_tryout_group(self, server_id: int, group_id: str, description: str, event_name: str, requirements: list):
        data = await self._get_server_data(server_id)
        updated = False
        for g in data["tryout_groups"]:
            if g["group_id"] == group_id:
                g["description"] = description
                g["event_name"] = event_name
                g["requirements"] = requirements
                # Preserve existing ping_roles
                if "ping_roles" not in g:
                    g["ping_roles"] = []
                updated = True
                break
        if updated:
            await self._update_server_data(server_id, {"tryout_groups": data["tryout_groups"]})

    async def add_group_ping_role(self, server_id: int, group_id: str, role_id: int):
        """Add a ping role to a specific tryout group"""
        data = await self._get_server_data(server_id)
        for g in data["tryout_groups"]:
            if g["group_id"] == group_id:
                if "ping_roles" not in g:
                    g["ping_roles"] = []
                if str(role_id) not in g["ping_roles"]:
                    g["ping_roles"].append(str(role_id))
                    await self._update_server_data(server_id, {"tryout_groups": data["tryout_groups"]})
                break

    async def remove_group_ping_role(self, server_id: int, group_id: str, role_id: int):
        """Remove a ping role from a specific tryout group"""
        data = await self._get_server_data(server_id)
        for g in data["tryout_groups"]:
            if g["group_id"] == group_id:
                if "ping_roles" in g and str(role_id) in g["ping_roles"]:
                    g["ping_roles"].remove(str(role_id))
                    await self._update_server_data(server_id, {"tryout_groups": data["tryout_groups"]})
                break

    async def delete_tryout_group(self, server_id: int, group_id: str):
        data = await self._get_server_data(server_id)
        before_count = len(data["tryout_groups"])
        data["tryout_groups"] = [g for g in data["tryout_groups"] if g["group_id"] != group_id]
        if len(data["tryout_groups"]) < before_count:
            await self._update_server_data(server_id, {"tryout_groups": data["tryout_groups"]})

    async def get_tryout_required_roles(self, server_id: int) -> list:
        data = await self._get_server_data(server_id)
        return [int(r) for r in data["tryout_required_roles"]]

    async def add_tryout_required_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid in data["tryout_required_roles"]:
            raise RuntimeError(f"Tryout required role {role_id} already exists.")
        data["tryout_required_roles"].append(rid)
        await self._update_server_data(server_id, {"tryout_required_roles": data["tryout_required_roles"]})

    async def remove_tryout_required_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid in data["tryout_required_roles"]:
            data["tryout_required_roles"].remove(rid)
            await self._update_server_data(server_id, {"tryout_required_roles": data["tryout_required_roles"]})

    async def get_tryout_channel_id(self, server_id: int) -> int:
        data = await self._get_server_data(server_id)
        channel_id = data["settings"].get("tryout_channel_id")
        return int(channel_id) if channel_id else None

    async def set_tryout_channel_id(self, server_id: int, channel_id: int):
        data = await self._get_server_data(server_id)
        data["settings"]["tryout_channel_id"] = str(channel_id)
        await self._update_server_data(server_id, {"settings": data["settings"]})

    async def get_ping_roles(self, server_id: int) -> list:
        data = await self._get_server_data(server_id)
        return [int(r) for r in data["ping_roles"]]

    async def add_ping_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid in data["ping_roles"]:
            raise RuntimeError(f"Ping role {role_id} already exists.")
        data["ping_roles"].append(rid)
        await self._update_server_data(server_id, {"ping_roles": data["ping_roles"]})

    async def remove_ping_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid in data["ping_roles"]:
            data["ping_roles"].remove(rid)
            await self._update_server_data(server_id, {"ping_roles": data["ping_roles"]})

    async def get_tryout_allowed_vcs(self, server_id: int) -> list:
        data = await self._get_server_data(server_id)
        return [int(vc) for vc in data.get("tryout_allowed_vcs", [])]

    async def add_tryout_allowed_vc(self, server_id: int, vc_id: int):
        data = await self._get_server_data(server_id)
        if "tryout_allowed_vcs" not in data:
            data["tryout_allowed_vcs"] = []
        vc_str = str(vc_id)
        if vc_str in data["tryout_allowed_vcs"]:
            raise RuntimeError(f"Voice channel {vc_id} already allowed.")
        data["tryout_allowed_vcs"].append(vc_str)
        await self._update_server_data(server_id, {"tryout_allowed_vcs": data["tryout_allowed_vcs"]})

    async def remove_tryout_allowed_vc(self, server_id: int, vc_id: int):
        data = await self._get_server_data(server_id)
        if "tryout_allowed_vcs" not in data:
            data["tryout_allowed_vcs"] = []
        vc_str = str(vc_id)
        if vc_str in data["tryout_allowed_vcs"]:
            data["tryout_allowed_vcs"].remove(vc_str)
            await self._update_server_data(server_id, {"tryout_allowed_vcs": data["tryout_allowed_vcs"]})

    async def get_autopromotion_channel_id(self, server_id: int) -> int:
        data = await self._get_server_data(server_id)
        cid = data.get("autopromotion_channel_id")
        return int(cid) if cid else None

    async def set_autopromotion_channel_id(self, server_id: int, channel_id: int):
        data = await self._get_server_data(server_id)
        data["autopromotion_channel_id"] = str(channel_id)
        await self._update_server_data(server_id, {"autopromotion_channel_id": data["autopromotion_channel_id"]})

    #
    # ------------- GLOBAL BAN (UPDATED) -------------
    #
    async def add_global_ban(
        self,
        discord_user_id: int,
        roblox_user_id: int,
        reason: str,
        moderator_discord_id: int,
        expires_at: datetime = None
    ) -> str:
        """
        Add a new global ban record, including a roblox_user_id from Bloxlink if available.
        Optionally store `expires_at` for temporary global bans.
        Return the inserted document's ID (string).
        """
        doc = {
            "discord_user_id": str(discord_user_id),
            "roblox_user_id": str(roblox_user_id) if roblox_user_id else None,
            "reason": reason,
            "banned_at": datetime.utcnow().isoformat(),
            "moderator_discord_id": str(moderator_discord_id),
            "active": True,
            "expires_at": expires_at.isoformat() if expires_at else None
        }
        result = await self.db["global_bans"].insert_one(doc)
        return str(result.inserted_id)

    async def remove_global_ban(self, discord_user_id: int) -> bool:
        """
        Remove the global ban for a user (by deleting or marking inactive).
        This version fully deletes the record from the DB.
        """
        result = await self.db["global_bans"].delete_one({
            "discord_user_id": str(discord_user_id),
            "active": True
        })
        return result.deleted_count > 0

    async def get_global_ban(self, discord_user_id: int) -> dict:
        """
        Return the ban document if found and still active.
        Callers can also check the expires_at field for expiration.
        """
        doc = await self.db["global_bans"].find_one({
            "discord_user_id": str(discord_user_id),
            "active": True
        })
        return doc

    async def get_all_active_global_bans(self) -> list:
        """Get all active global bans"""
        return await self.db["global_bans"].find({
            "active": True
        }).to_list(None)

    async def should_sync_global_bans(self, guild_id: int) -> bool:
        """Check if a guild has global ban synchronization enabled"""
        settings = await self.get_server_settings(guild_id)
        return settings.get('global_bans_enabled', False)

    async def sync_global_bans_for_guild(self, guild_id: int) -> tuple[list, list]:
        """
        Sync all active global bans to a guild that just enabled global bans.
        Returns tuple of (successful_syncs, failed_syncs) user IDs.
        """
        if not await self.should_sync_global_bans(guild_id):
            return [], []

        active_bans = await self.get_all_active_global_bans()
        successful = []
        failed = []
        
        for ban in active_bans:
            user_id = int(ban["discord_user_id"])
            successful.append(user_id)
            # Note: The actual banning will be handled by the moderation cog
            
        return successful, failed

    #
    # ------------- CHANNEL LOCKING -------------
    #
    async def lock_channel_in_db(self, server_id: int, channel_id: int):
        data = await self._get_server_data(server_id)
        cid_str = str(channel_id)
        if cid_str not in data["locked_channels"]:
            data["locked_channels"].append(cid_str)
            await self._update_server_data(server_id, {"locked_channels": data["locked_channels"]})

    async def unlock_channel_in_db(self, server_id: int, channel_id: int):
        data = await self._get_server_data(server_id)
        cid_str = str(channel_id)
        if cid_str in data["locked_channels"]:
            data["locked_channels"].remove(cid_str)
            await self._update_server_data(server_id, {"locked_channels": data["locked_channels"]})

    async def is_channel_locked(self, server_id: int, channel_id: int) -> bool:
        data = await self._get_server_data(server_id)
        return str(channel_id) in data["locked_channels"]

    #
    # ------------- CASES SYSTEM -------------
    #
    def _generate_random_case_id(self, length: int = 6) -> str:
        """
        Generate a random uppercase-alphanumeric string, e.g. 'A1B2C3'.
        """
        alphabet = string.ascii_uppercase + string.digits
        return "".join(random.choice(alphabet) for _ in range(length))

    async def add_case(
        self,
        server_id: int,
        user_id: int,
        moderator_id: int,
        action_type: str,
        reason: str,
        extra: dict = None
    ) -> str:
        """
        Create a new moderation 'case' entry (warn/mute/kick/ban/etc.)
        using a random short string as the case_id.
        Returns the new case_id (string).
        """
        if extra is None:
            extra = {}
        for _ in range(10):
            new_case_id = self._generate_random_case_id()
            doc = {
                "case_id": new_case_id,
                "server_id": str(server_id),
                "user_id": str(user_id),
                "moderator_id": str(moderator_id),
                "action_type": action_type,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat(),
                "extra": extra
            }
            try:
                await self.db["cases"].insert_one(doc)
                return new_case_id
            except DuplicateKeyError:
                # The random ID collided for this server -- try again
                continue
        raise RuntimeError("Could not generate a unique case ID after 10 attempts.")

    async def get_case(self, server_id: int, case_id: str) -> dict:
        """
        Retrieve a specific case (by server and case_id string).
        Returns the Mongo document, or None if not found.
        """
        return await self.db["cases"].find_one({
            "server_id": str(server_id),
            "case_id": case_id
        })

    #
    # ------------- CLOSE CONNECTION -------------
    #
    async def close(self):
        self.logger.info("MongoDB connection closed.")

    #
    # ------------- GDPR REQUESTS -------------
    #
    async def check_recent_gdpr_request(self, requester_id: int) -> bool:
        """Check if user has made a GDPR request in the last 24 hours"""
        one_day_ago = (datetime.utcnow() - timedelta(days=1)).isoformat()
        recent_request = await self.db["gdpr_requests"].find_one({
            "requester_id": str(requester_id),
            "created_at": {"$gt": one_day_ago}
        })
        return recent_request is not None

    async def create_gdpr_request(
        self,
        request_id: str,
        requester_id: int,
        target_user_id: int,
        data: dict
    ) -> str:
        """Create a new GDPR request in pending status"""
        doc = {
            "request_id": request_id,
            "requester_id": str(requester_id),
            "target_user_id": str(target_user_id),
            "status": "pending",
            "data": data,
            "created_at": datetime.utcnow().isoformat(),
            "reviewed_at": None,
            "reviewer_id": None,
            "denial_reason": None
        }
        await self.db["gdpr_requests"].insert_one(doc)
        return request_id

    async def get_gdpr_request(self, request_id: str) -> dict:
        """Get a GDPR request by its ID"""
        return await self.db["gdpr_requests"].find_one({"request_id": request_id})

    async def update_gdpr_request(
        self,
        request_id: str,
        status: str,
        reviewer_id: int,
        denial_reason: str = None
    ) -> bool:
        """Update a GDPR request's status"""
        update = {
            "status": status,
            "reviewed_at": datetime.utcnow().isoformat(),
            "reviewer_id": str(reviewer_id)
        }
        if denial_reason:
            update["denial_reason"] = denial_reason

        result = await self.db["gdpr_requests"].update_one(
            {"request_id": request_id},
            {"$set": update}
        )
        return result.modified_count > 0

    #
    # ------------- COMMAND LOGGING -------------
    #
    async def log_command(self, log_data: dict) -> str:
        """
        Log a command execution to the database.
        Returns the inserted document's ID.
        """
        # Convert IDs to strings for consistency
        if "guild_id" in log_data and log_data["guild_id"]:
            log_data["guild_id"] = str(log_data["guild_id"])
        if "channel_id" in log_data and log_data["channel_id"]:
            log_data["channel_id"] = str(log_data["channel_id"])
        if "user_id" in log_data and log_data["user_id"]:
            log_data["user_id"] = str(log_data["user_id"])

        # Add timestamp if not present
        if "timestamp" not in log_data:
            log_data["timestamp"] = datetime.utcnow().isoformat()

        # Insert the log
        result = await self.db["command_logs"].insert_one(log_data)
        return str(result.inserted_id)

    async def get_user_command_logs(
        self,
        user_id: int,
        limit: int = 100,
        skip: int = 0,
        success_only: bool = None,
        command_filter: str = None
    ) -> list:
        """Get command logs for a specific user with optional filtering."""
        query = {"user_id": str(user_id)}
        if success_only is not None:
            query["success"] = success_only
        if command_filter:
            query["command"] = command_filter

        cursor = self.db["command_logs"].find(query)
        cursor.sort("timestamp", -1).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_guild_command_logs(
        self,
        guild_id: int,
        limit: int = 100,
        skip: int = 0,
        success_only: bool = None,
        command_filter: str = None
    ) -> list:
        """Get command logs for a specific guild with optional filtering."""
        query = {"guild_id": str(guild_id)}
        if success_only is not None:
            query["success"] = success_only
        if command_filter:
            query["command"] = command_filter

        cursor = self.db["command_logs"].find(query)
        cursor.sort("timestamp", -1).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_command_usage_stats(
        self,
        guild_id: int = None,
        since: datetime = None
    ) -> dict:
        """Get command usage statistics, optionally filtered by guild and time."""
        match_stage = {}
        if guild_id:
            match_stage["guild_id"] = str(guild_id)
        if since:
            match_stage["timestamp"] = {"$gt": since.isoformat()}

        pipeline = []
        if match_stage:
            pipeline.append({"$match": match_stage})

        pipeline.extend([
            {
                "$group": {
                    "_id": "$command",
                    "total_uses": {"$sum": 1},
                    "successful_uses": {
                        "$sum": {"$cond": ["$success", 1, 0]}
                    },
                    "failed_uses": {
                        "$sum": {"$cond": ["$success", 0, 1]}
                    },
                    "unique_users": {"$addToSet": "$user_id"}
                }
            },
            {
                "$project": {
                    "command": "$_id",
                    "total_uses": 1,
                    "successful_uses": 1,
                    "failed_uses": 1,
                    "unique_users": {"$size": "$unique_users"}
                }
            },
            {"$sort": {"total_uses": -1}}
        ])

        return await self.db["command_logs"].aggregate(pipeline).to_list(None)

    async def cleanup_old_logs(self, days_to_keep: int = 30) -> int:
        """Remove command logs older than the specified number of days."""
        cutoff_date = (datetime.utcnow() - timedelta(days=days_to_keep)).isoformat()
        result = await self.db["command_logs"].delete_many(
            {"timestamp": {"$lt": cutoff_date}}
        )
        return result.deleted_count

    #
    # ------------- TRYOUT SESSIONS -------------
    #
    async def create_tryout_session(
        self,
        guild_id: int,
        host_id: int,
        group_id: str,
        group_name: str,
        channel_id: int,
        voice_channel_id: Optional[int],
        lock_timestamp: str,
        requirements: list,
        description: str,
        message_id: int,
        voice_invite: Optional[str]
    ) -> str:
        """Create a new tryout session"""
        doc = {
            "guild_id": str(guild_id),
            "host_id": str(host_id),
            "group_id": str(group_id),
            "group_name": group_name,
            "channel_id": str(channel_id),
            "voice_channel_id": str(voice_channel_id) if voice_channel_id else None,
            "message_id": str(message_id),
            "voice_invite": voice_invite,
            "requirements": requirements,
            "description": description,
            "created_at": datetime.utcnow().replace(microsecond=0).isoformat(),
            "lock_timestamp": lock_timestamp,
            "status": "active",
            "ended_at": None,
            "end_reason": None,
            "notes": []
        }
        result = await self.db["tryout_sessions"].insert_one(doc)
        return str(result.inserted_id)

    async def get_tryout_session(self, session_id: str) -> Optional[dict]:
        """Get a tryout session by its ID"""
        from bson import ObjectId
        try:
            return await self.db["tryout_sessions"].find_one({"_id": ObjectId(session_id)})
        except Exception as e:
            self.logger.error(f"Error getting tryout session {session_id}: {e}")
            return None

    async def get_active_tryout_sessions(self, guild_id: int) -> list:
        """Get all active tryout sessions for a guild"""
        return await self.db["tryout_sessions"].find({
            "guild_id": str(guild_id),
            "status": "active"
        }).sort("created_at", -1).to_list(None)

    async def end_tryout_session(self, session_id: str, reason: str) -> bool:
        """End a tryout session"""
        from bson import ObjectId
        try:
            result = await self.db["tryout_sessions"].update_one(
                {"_id": ObjectId(session_id)},
                {
                    "$set": {
                        "status": "ended",
                        "ended_at": datetime.utcnow().replace(microsecond=0).isoformat(),
                        "end_reason": reason
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            self.logger.error(f"Error ending tryout session {session_id}: {e}")
            return False

    async def add_tryout_note(
        self,
        session_id: str,
        moderator_id: int,
        note: str
    ) -> bool:
        """Add a note to a tryout session"""
        from bson import ObjectId
        try:
            note_doc = {
                "moderator_id": str(moderator_id),
                "note": note,
                "timestamp": datetime.utcnow().replace(microsecond=0).isoformat()
            }
            result = await self.db["tryout_sessions"].update_one(
                {"_id": ObjectId(session_id)},
                {"$push": {"notes": note_doc}}
            )
            return result.modified_count > 0
        except Exception as e:
            self.logger.error(f"Error adding note to session {session_id}: {e}")
            return False

    async def get_tryout_log_channel_id(self, server_id: int) -> Optional[int]:
        """Get the tryout logging channel ID for a guild"""
        data = await self._get_server_data(server_id)
        channel_id = data["settings"].get("tryout_log_channel_id")
        return int(channel_id) if channel_id else None

    async def set_tryout_log_channel_id(self, server_id: int, channel_id: int):
        """Set the tryout logging channel ID for a guild"""
        data = await self._get_server_data(server_id)
        data["settings"]["tryout_log_channel_id"] = str(channel_id)
        await self._update_server_data(server_id, {"settings": data["settings"]})
