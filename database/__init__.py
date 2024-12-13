import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

class DatabaseManager:
    def __init__(self, *, db: AsyncIOMotorDatabase) -> None:
        self.db = db
        self.logger = logging.getLogger('DatabaseManager')

    async def initialize_database(self):
        """
        Initialize MongoDB collections and indexes if needed.
        
        We will have two collections:
        - "warns": stores user warnings
        - "server_data": one document per server that holds all server-specific settings, roles, groups, etc.
        
        Structure of "server_data" document:
        {
          "server_id": <string>,
          "settings": {
            "automod_enabled": bool,
            "automod_logging_enabled": bool,
            "automod_log_channel_id": str or None,
            "tryout_channel_id": str or None,
            "mod_log_channel_id": str or None,
            "automod_mute_duration": int
          },
          "tryout_groups": [
             {
               "group_id": <string>,
               "description": <string>,
               "link": <string>,
               "event_name": <string>
             }
          ],
          "tryout_required_roles": [<string_role_id>],
          "moderation_allowed_roles": [<string_role_id>],
          "locked_channels": [<string_channel_id>],
          "ping_roles": [<string_role_id>],
          "automod_exempt_roles": [<string_role_id>],
          "protected_users": [<string_user_id>]
        }
        """

        # Ensure indexes for warns
        await self.db["warns"].create_index([("user_id", 1), ("server_id", 1)])

        # server_data is keyed by server_id
        await self.db["server_data"].create_index([("server_id", 1)], unique=True)

        self.logger.info("Database (MongoDB) initialized and indexes ensured.")

    # ---------------------------
    # Methods for Managing Warns
    # ---------------------------
    async def add_warn(self, user_id: int, server_id: int, moderator_id: int, reason: str) -> int:
        last_warn = await self.db["warns"].find({"user_id": str(user_id), "server_id": str(server_id)}).sort("id", -1).limit(1).to_list(length=1)
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
        self.logger.info(f"Added warn ID {warn_id} for user {user_id} in server {server_id}.")
        return warn_id

    async def remove_warn(self, warn_id: int, user_id: int, server_id: int) -> bool:
        result = await self.db["warns"].delete_one({"id": warn_id, "user_id": str(user_id), "server_id": str(server_id)})
        removed = result.deleted_count > 0
        self.logger.info(f"Removed warn ID {warn_id} for user {user_id} in server {server_id}: {removed}")
        return removed

    async def get_all_warnings(self) -> list:
        warnings = await self.db["warns"].find({}).to_list(None)
        for w in warnings:
            w["created_at"] = str(int(datetime.fromisoformat(w["created_at"]).timestamp()))
        self.logger.info(f"Fetched all warnings: {len(warnings)} records found.")
        return [
            (w["user_id"], w["server_id"], w["moderator_id"], w["reason"], w["created_at"], w["id"])
            for w in warnings
        ]

    async def get_warnings(self, user_id: int, server_id: int) -> list:
        warnings = await self.db["warns"].find({"user_id": str(user_id), "server_id": str(server_id)}).to_list(None)
        for w in warnings:
            w["created_at"] = str(int(datetime.fromisoformat(w["created_at"]).timestamp()))
        self.logger.info(f"Fetched {len(warnings)} warnings for user {user_id} in server {server_id}.")
        return [
            (w["user_id"], w["server_id"], w["moderator_id"], w["reason"], w["created_at"], w["id"])
            for w in warnings
        ]

    async def clear_all_warnings(self, user_id: int, server_id: int) -> int:
        result = await self.db["warns"].delete_many({"user_id": str(user_id), "server_id": str(server_id)})
        removed = result.deleted_count
        self.logger.info(f"Cleared {removed} warnings for user {user_id} in server {server_id}.")
        return removed

    async def count_warnings(self, user_id: int, server_id: int) -> int:
        count = await self.db["warns"].count_documents({"user_id": str(user_id), "server_id": str(server_id)})
        self.logger.info(f"User {user_id} has {count} warnings in server {server_id}.")
        return count

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
        self.logger.info(f"Removed {removed} expired warnings older than timestamp {expiration_timestamp}.")
        return removed

    # ---------------------------
    # Server Data Helpers
    # ---------------------------
    async def _get_server_data(self, server_id: int) -> dict:
        data = await self.db["server_data"].find_one({"server_id": str(server_id)})
        if not data:
            # Initialize default structure
            data = {
                "server_id": str(server_id),
                "settings": {
                    "automod_enabled": True,
                    "automod_logging_enabled": False,
                    "automod_log_channel_id": None,
                    "tryout_channel_id": None,
                    "mod_log_channel_id": None,
                    "automod_mute_duration": 3600
                },
                "tryout_groups": [],
                "tryout_required_roles": [],
                "moderation_allowed_roles": [],
                "locked_channels": [],
                "ping_roles": [],
                "automod_exempt_roles": [],
                "protected_users": []
            }
            await self.db["server_data"].insert_one(data)
            self.logger.info(f"Initialized server data for server {server_id}.")
        return data

    async def _update_server_data(self, server_id: int, update: dict):
        await self.db["server_data"].update_one(
            {"server_id": str(server_id)},
            {"$set": update},
            upsert=True
        )

    # ---------------------------
    # Methods for Server Settings
    # ---------------------------
    async def initialize_server_settings(self, server_id: int):
        # Ensured by _get_server_data
        await self._get_server_data(server_id)

    async def get_server_settings(self, server_id: int) -> dict:
        data = await self._get_server_data(server_id)
        s = data["settings"]
        settings = {
            'automod_enabled': bool(s.get('automod_enabled', True)),
            'automod_logging_enabled': bool(s.get('automod_logging_enabled', False)),
            'automod_log_channel_id': int(s['automod_log_channel_id']) if s.get('automod_log_channel_id') else None,
            'tryout_channel_id': int(s['tryout_channel_id']) if s.get('tryout_channel_id') else None,
            'mod_log_channel_id': int(s['mod_log_channel_id']) if s.get('mod_log_channel_id') else None,
            'automod_mute_duration': int(s.get('automod_mute_duration', 3600))
        }
        self.logger.info(f"Fetched server settings for server {server_id}: {settings}")
        return settings

    async def update_server_setting(self, server_id: int, setting_name: str, value):
        data = await self._get_server_data(server_id)
        data["settings"][setting_name] = value
        await self._update_server_data(server_id, {"settings": data["settings"]})
        self.logger.info(f"Updated server setting '{setting_name}' for server {server_id} to '{value}'.")

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
        self.logger.info(f"Toggled server setting '{setting_name}' for server {server_id} to '{new_value}'.")

    async def get_automod_mute_duration(self, server_id: int) -> int:
        settings = await self.get_server_settings(server_id)
        return settings.get('automod_mute_duration', 3600)

    async def set_automod_mute_duration(self, server_id: int, duration: int):
        await self.update_server_setting(server_id, "automod_mute_duration", duration)
        self.logger.info(f"Set automod mute duration to {duration} seconds for server {server_id}.")

    # ---------------------------
    # Methods for Protected Users
    # ---------------------------
    async def get_protected_users(self, server_id: int) -> list:
        data = await self._get_server_data(server_id)
        user_ids = [int(u) for u in data["protected_users"]]
        self.logger.info(f"Fetched protected users for server {server_id}: {user_ids}")
        return user_ids

    async def add_protected_user(self, server_id: int, user_id: int):
        data = await self._get_server_data(server_id)
        if str(user_id) not in data["protected_users"]:
            data["protected_users"].append(str(user_id))
            await self._update_server_data(server_id, {"protected_users": data["protected_users"]})
            self.logger.info(f"Added protected user {user_id} to server {server_id}.")
        else:
            self.logger.warning(f"Protected user {user_id} already exists in server {server_id}.")

    async def remove_protected_user(self, server_id: int, user_id: int):
        data = await self._get_server_data(server_id)
        if str(user_id) in data["protected_users"]:
            data["protected_users"].remove(str(user_id))
            await self._update_server_data(server_id, {"protected_users": data["protected_users"]})
            self.logger.info(f"Removed protected user {user_id} from server {server_id}.")

    # ---------------------------
    # Methods for Exempt Roles (Automod Exempt Roles)
    # ---------------------------
    async def get_exempt_roles(self, server_id: int) -> list:
        return await self.get_automod_exempt_roles(server_id)

    async def add_exempt_role(self, server_id: int, role_id: int):
        return await self.add_automod_exempt_role(server_id, role_id)

    async def remove_exempt_role(self, server_id: int, role_id: int):
        return await self.remove_automod_exempt_role(server_id, role_id)

    # ---------------------------
    # Methods for Moderation Allowed Roles
    # ---------------------------
    async def get_moderation_allowed_roles(self, server_id: int) -> list:
        data = await self._get_server_data(server_id)
        role_ids = [int(r) for r in data["moderation_allowed_roles"]]
        self.logger.info(f"Fetched moderation allowed roles for server {server_id}: {role_ids}")
        return role_ids

    async def add_moderation_allowed_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid not in data["moderation_allowed_roles"]:
            data["moderation_allowed_roles"].append(rid)
            await self._update_server_data(server_id, {"moderation_allowed_roles": data["moderation_allowed_roles"]})
            self.logger.info(f"Added role {role_id} to moderation allowed roles in server {server_id}.")
        else:
            self.logger.warning(f"Role {role_id} already exists in moderation allowed roles for server {server_id}.")

    async def remove_moderation_allowed_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid in data["moderation_allowed_roles"]:
            data["moderation_allowed_roles"].remove(rid)
            await self._update_server_data(server_id, {"moderation_allowed_roles": data["moderation_allowed_roles"]})
            self.logger.info(f"Removed role {role_id} from moderation allowed roles in server {server_id}.")

    async def set_mod_log_channel(self, server_id: int, channel_id: int):
        data = await self._get_server_data(server_id)
        data["settings"]["mod_log_channel_id"] = str(channel_id)
        await self._update_server_data(server_id, {"settings": data["settings"]})
        self.logger.info(f"Set moderation log channel to {channel_id} for server {server_id}.")

    async def get_mod_log_channel(self, server_id: int) -> int:
        settings = await self.get_server_settings(server_id)
        mlc = settings.get("mod_log_channel_id")
        self.logger.info(f"Fetched moderation log channel ID for server {server_id}: {mlc}")
        return mlc

    # ---------------------------
    # Methods for Tryout Groups
    # ---------------------------
    async def get_tryout_groups(self, server_id: int) -> list:
        data = await self._get_server_data(server_id)
        groups = data.get("tryout_groups", [])
        self.logger.info(f"Fetched {len(groups)} tryout groups for server {server_id}.")
        return [(g["group_id"], g["description"], g["link"], g["event_name"]) for g in groups]

    async def get_tryout_group(self, server_id: int, group_id: str):
        data = await self._get_server_data(server_id)
        for g in data["tryout_groups"]:
            if g["group_id"] == group_id:
                self.logger.info(f"Fetched tryout group '{group_id}' for server {server_id}: {g}")
                return (g["group_id"], g["description"], g["link"], g["event_name"])
        self.logger.info(f"No tryout group '{group_id}' found for server {server_id}.")
        return None

    async def add_tryout_group(self, server_id: int, group_id: str, description: str, link: str, event_name: str):
        data = await self._get_server_data(server_id)
        for g in data["tryout_groups"]:
            if g["group_id"] == group_id:
                self.logger.warning(f"Tryout group '{group_id}' already exists in server {server_id}.")
                raise RuntimeError(f"Tryout group '{group_id}' already exists.")
        data["tryout_groups"].append({
            "group_id": group_id,
            "description": description,
            "link": link,
            "event_name": event_name
        })
        await self._update_server_data(server_id, {"tryout_groups": data["tryout_groups"]})
        self.logger.info(f"Added tryout group '{group_id}' for server {server_id}.")

    async def update_tryout_group(self, server_id: int, group_id: str, description: str, link: str, event_name: str):
        data = await self._get_server_data(server_id)
        updated = False
        for g in data["tryout_groups"]:
            if g["group_id"] == group_id:
                g["description"] = description
                g["link"] = link
                g["event_name"] = event_name
                updated = True
                break
        if updated:
            await self._update_server_data(server_id, {"tryout_groups": data["tryout_groups"]})
            self.logger.info(f"Updated tryout group '{group_id}' for server {server_id}.")
        else:
            self.logger.warning(f"No tryout group '{group_id}' found to update in server {server_id}.")

    async def delete_tryout_group(self, server_id: int, group_id: str):
        data = await self._get_server_data(server_id)
        before_count = len(data["tryout_groups"])
        data["tryout_groups"] = [g for g in data["tryout_groups"] if g["group_id"] != group_id]
        if len(data["tryout_groups"]) < before_count:
            await self._update_server_data(server_id, {"tryout_groups": data["tryout_groups"]})
            self.logger.info(f"Deleted tryout group '{group_id}' from server {server_id}.")
        else:
            self.logger.info(f"No tryout group '{group_id}' found to delete from server {server_id}.")

    # ---------------------------
    # Methods for Tryout Required Roles
    # ---------------------------
    async def get_tryout_required_roles(self, server_id: int) -> list:
        data = await self._get_server_data(server_id)
        roles = [int(r) for r in data["tryout_required_roles"]]
        self.logger.info(f"Fetched {len(roles)} tryout required roles for server {server_id}.")
        return roles

    async def add_tryout_required_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid in data["tryout_required_roles"]:
            self.logger.warning(f"Tryout required role {role_id} already exists in server {server_id}.")
            raise RuntimeError(f"Tryout required role {role_id} already exists.")
        data["tryout_required_roles"].append(rid)
        await self._update_server_data(server_id, {"tryout_required_roles": data["tryout_required_roles"]})
        self.logger.info(f"Added tryout required role {role_id} to server {server_id}.")

    async def remove_tryout_required_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid in data["tryout_required_roles"]:
            data["tryout_required_roles"].remove(rid)
            await self._update_server_data(server_id, {"tryout_required_roles": data["tryout_required_roles"]})
            self.logger.info(f"Removed tryout required role {role_id} from server {server_id}.")

    # ---------------------------
    # Methods for Tryout Settings
    # ---------------------------
    async def get_tryout_channel_id(self, server_id: int) -> int:
        data = await self._get_server_data(server_id)
        channel_id = data["settings"].get("tryout_channel_id")
        tcid = int(channel_id) if channel_id else None
        self.logger.info(f"Fetched tryout channel ID for server {server_id}: {tcid}")
        return tcid

    async def set_tryout_channel_id(self, server_id: int, channel_id: int):
        data = await self._get_server_data(server_id)
        data["settings"]["tryout_channel_id"] = str(channel_id)
        await self._update_server_data(server_id, {"settings": data["settings"]})
        self.logger.info(f"Set tryout channel ID to {channel_id} for server {server_id}.")

    # ---------------------------
    # Methods for Ping Roles
    # ---------------------------
    async def get_ping_roles(self, server_id: int) -> list:
        data = await self._get_server_data(server_id)
        roles = [int(r) for r in data["ping_roles"]]
        self.logger.info(f"Fetched {len(roles)} ping roles for server {server_id}.")
        return roles

    async def add_ping_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid in data["ping_roles"]:
            self.logger.warning(f"Ping role {role_id} already exists in server {server_id}.")
            raise RuntimeError(f"Ping role {role_id} already exists.")
        data["ping_roles"].append(rid)
        await self._update_server_data(server_id, {"ping_roles": data["ping_roles"]})
        self.logger.info(f"Added ping role {role_id} to server {server_id}.")

    async def remove_ping_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid in data["ping_roles"]:
            data["ping_roles"].remove(rid)
            await self._update_server_data(server_id, {"ping_roles": data["ping_roles"]})
            self.logger.info(f"Removed ping role {role_id} from server {server_id}.")

    # ---------------------------
    # Methods for Locking Channels
    # ---------------------------
    async def lock_channel_in_db(self, server_id: int, channel_id: int):
        data = await self._get_server_data(server_id)
        cid = str(channel_id)
        if cid not in data["locked_channels"]:
            data["locked_channels"].append(cid)
            await self._update_server_data(server_id, {"locked_channels": data["locked_channels"]})
            self.logger.info(f"Locked channel {channel_id} in server {server_id} and recorded in DB.")
        else:
            self.logger.warning(f"Channel {channel_id} in server {server_id} is already locked.")

    async def unlock_channel_in_db(self, server_id: int, channel_id: int):
        data = await self._get_server_data(server_id)
        cid = str(channel_id)
        if cid in data["locked_channels"]:
            data["locked_channels"].remove(cid)
            await self._update_server_data(server_id, {"locked_channels": data["locked_channels"]})
            self.logger.info(f"Unlocked channel {channel_id} in server {server_id} and removed from DB.")

    async def is_channel_locked(self, server_id: int, channel_id: int) -> bool:
        data = await self._get_server_data(server_id)
        is_locked = str(channel_id) in data["locked_channels"]
        self.logger.info(f"Channel {channel_id} in server {server_id} is_locked: {is_locked}")
        return is_locked

    # ---------------------------
    # Methods for Automod Exempt Roles
    # ---------------------------
    async def get_automod_exempt_roles(self, server_id: int) -> list:
        data = await self._get_server_data(server_id)
        roles = [int(r) for r in data["automod_exempt_roles"]]
        self.logger.info(f"Fetched automod exempt roles for server {server_id}: {roles}")
        return roles

    async def add_automod_exempt_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid in data["automod_exempt_roles"]:
            self.logger.warning(f"Automod exempt role {role_id} already exists in server {server_id}.")
            raise RuntimeError(f"Automod exempt role {role_id} already exists.")
        data["automod_exempt_roles"].append(rid)
        await self._update_server_data(server_id, {"automod_exempt_roles": data["automod_exempt_roles"]})
        self.logger.info(f"Added automod exempt role {role_id} to server {server_id}.")

    async def remove_automod_exempt_role(self, server_id: int, role_id: int):
        data = await self._get_server_data(server_id)
        rid = str(role_id)
        if rid in data["automod_exempt_roles"]:
            data["automod_exempt_roles"].remove(rid)
            await self._update_server_data(server_id, {"automod_exempt_roles": data["automod_exempt_roles"]})
            self.logger.info(f"Removed automod exempt role {role_id} from server {server_id}.")

    async def close(self):
        self.logger.info("MongoDB connection closed (not strictly necessary).")
