import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

class DatabaseManager:
    def __init__(self, *, db: AsyncIOMotorDatabase) -> None:
        self.db = db
        self.logger = logging.getLogger('DatabaseManager')

    async def initialize_database(self):
        await self.db["warns"].create_index([("user_id", 1), ("server_id", 1)])
        await self.db["server_data"].create_index([("server_id", 1)], unique=True)
        self.logger.info("Database initialized.")

    async def add_warn(self, user_id: int, server_id: int, moderator_id: int, reason: str) -> int:
        last_warn = await self.db["warns"].find({"user_id": str(user_id), "server_id": str(server_id)}) \
            .sort("id", -1).limit(1).to_list(1)
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
        result = await self.db["warns"].delete_one({"id": warn_id, "user_id": str(user_id), "server_id": str(server_id)})
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
        warnings = await self.db["warns"].find({"user_id": str(user_id), "server_id": str(server_id)}).to_list(None)
        for w in warnings:
            w["created_at"] = str(int(datetime.fromisoformat(w["created_at"]).timestamp()))
        return [
            (w["user_id"], w["server_id"], w["moderator_id"], w["reason"], w["created_at"], w["id"])
            for w in warnings
        ]

    async def clear_all_warnings(self, user_id: int, server_id: int) -> int:
        result = await self.db["warns"].delete_many({"user_id": str(user_id), "server_id": str(server_id)})
        return result.deleted_count

    async def count_warnings(self, user_id: int, server_id: int) -> int:
        return await self.db["warns"].count_documents({"user_id": str(user_id), "server_id": str(server_id)})

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

    async def _get_server_data(self, server_id: int) -> dict:
        data = await self.db["server_data"].find_one({"server_id": str(server_id)})
        if not data:
            data = {
                "server_id": str(server_id),
                "settings": {
                    "automod_enabled": True,
                    "automod_logging_enabled": False,
                    "automod_log_channel_id": None,
                    "tryout_channel_id": None,
                    "mod_log_channel_id": None,
                    "automod_mute_duration": 3600,
                    "automod_spam_limit": 5,    # Default spam limit
                    "automod_spam_window": 5    # Default spam time window
                },
                "tryout_groups": [],
                "tryout_required_roles": [],
                "moderation_allowed_roles": [],
                "locked_channels": [],
                "ping_roles": [],
                "automod_exempt_roles": [],
                "protected_users": [],
                "tryout_allowed_vcs": [],
                "autopromotion_channel_id": None
            }
            await self.db["server_data"].insert_one(data)
        else:
            # Ensure new fields exist
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
            'automod_spam_window': int(s.get('automod_spam_window', 5))
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

    # New methods for spam settings
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
        return [(g["group_id"], g["description"], g["event_name"], g.get("requirements", [])) for g in groups]

    async def get_tryout_group(self, server_id: int, group_id: str):
        data = await self._get_server_data(server_id)
        for g in data["tryout_groups"]:
            if g["group_id"] == group_id:
                return (g["group_id"], g["description"], g["event_name"], g.get("requirements", []))
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
            "requirements": requirements
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
                updated = True
                break
        if updated:
            await self._update_server_data(server_id, {"tryout_groups": data["tryout_groups"]})

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

    async def close(self):
        self.logger.info("MongoDB connection closed.")

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