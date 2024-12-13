import logging
import os
import sqlite3
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

class DatabaseManager:
    def __init__(self, *, db: AsyncIOMotorDatabase) -> None:
        self.db = db
        self.logger = logging.getLogger('DatabaseManager')

    async def initialize_database(self):
        """
        Initialize MongoDB collections and indexes if needed.
        This replaces the schema application logic.
        """
        # For example, ensure indexes for frequently queried fields:
        await self.db["warns"].create_index([("user_id", 1), ("server_id", 1)])
        await self.db["server_settings"].create_index([("server_id", 1)], unique=True)
        await self.db["tryout_groups"].create_index([("server_id", 1), ("group_id", 1)], unique=True)
        await self.db["tryout_required_roles"].create_index([("server_id", 1), ("role_id", 1)], unique=True)
        await self.db["tryout_settings"].create_index([("server_id", 1)], unique=True)
        await self.db["moderation_allowed_roles"].create_index([("server_id", 1), ("role_id", 1)], unique=True)
        await self.db["locked_channels"].create_index([("server_id", 1), ("channel_id", 1)], unique=True)
        await self.db["ping_roles"].create_index([("server_id", 1), ("role_id", 1)], unique=True)
        await self.db["automod_exempt_roles"].create_index([("server_id", 1), ("role_id", 1)], unique=True)
        await self.db["protected_users"].create_index([("server_id", 1), ("user_id", 1)], unique=True)
        self.logger.info("Database (MongoDB) initialized and indexes ensured.")

    async def migrate_from_sqlite_to_mongo(self):
        """
        Migrate data from SQLite database.db to MongoDB.
        Run this command once and then you can remove the old SQLite DB.
        """
        sqlite_path = f"{os.path.realpath(os.path.dirname(__file__))}/database/database.db"
        if not os.path.isfile(sqlite_path):
            self.logger.info("No SQLite database found to migrate.")
            return

        self.logger.info("Starting migration from SQLite to MongoDB...")

        conn = sqlite3.connect(sqlite_path)
        c = conn.cursor()

        # Migrate warns
        c.execute("SELECT id, user_id, server_id, moderator_id, reason, created_at FROM warns")
        warns_data = c.fetchall()
        if warns_data:
            docs = []
            for row in warns_data:
                _id, user_id, server_id, moderator_id, reason, created_at = row
                docs.append({
                    "id": _id,
                    "user_id": str(user_id),
                    "server_id": str(server_id),
                    "moderator_id": str(moderator_id),
                    "reason": reason,
                    "created_at": created_at
                })
            await self.db["warns"].insert_many(docs)

        # Migrate server_settings
        c.execute("SELECT server_id, automod_enabled, automod_logging_enabled, automod_log_channel_id, tryout_channel_id, mod_log_channel_id, automod_mute_duration FROM server_settings")
        settings_data = c.fetchall()
        if settings_data:
            docs = []
            for row in settings_data:
                server_id, ae, ale, alcid, tcid, mlcid, amd = row
                docs.append({
                    "server_id": str(server_id),
                    "automod_enabled": bool(ae),
                    "automod_logging_enabled": bool(ale),
                    "automod_log_channel_id": alcid if alcid else None,
                    "tryout_channel_id": tcid if tcid else None,
                    "mod_log_channel_id": mlcid if mlcid else None,
                    "automod_mute_duration": amd if amd else 3600
                })
            await self.db["server_settings"].insert_many(docs)

        # tryout_groups
        c.execute("SELECT server_id, group_id, description, link, event_name FROM tryout_groups")
        groups_data = c.fetchall()
        if groups_data:
            docs = []
            for row in groups_data:
                sid, gid, desc, link, event = row
                docs.append({
                    "server_id": str(sid),
                    "group_id": str(gid),
                    "description": desc,
                    "link": link,
                    "event_name": event
                })
            await self.db["tryout_groups"].insert_many(docs)

        # tryout_required_roles
        c.execute("SELECT server_id, role_id FROM tryout_required_roles")
        rr_data = c.fetchall()
        if rr_data:
            docs = []
            for row in rr_data:
                sid, rid = row
                docs.append({
                    "server_id": str(sid),
                    "role_id": str(rid)
                })
            await self.db["tryout_required_roles"].insert_many(docs)

        # tryout_settings
        c.execute("SELECT server_id, tryout_channel_id FROM tryout_settings")
        ts_data = c.fetchall()
        if ts_data:
            docs = []
            for row in ts_data:
                sid, tcid = row
                docs.append({
                    "server_id": str(sid),
                    "tryout_channel_id": tcid if tcid else None
                })
            await self.db["tryout_settings"].insert_many(docs)

        # moderation_allowed_roles
        c.execute("SELECT server_id, role_id FROM moderation_allowed_roles")
        mar_data = c.fetchall()
        if mar_data:
            docs = []
            for row in mar_data:
                sid, rid = row
                docs.append({"server_id": str(sid), "role_id": str(rid)})
            await self.db["moderation_allowed_roles"].insert_many(docs)

        # locked_channels
        c.execute("SELECT server_id, channel_id FROM locked_channels")
        lc_data = c.fetchall()
        if lc_data:
            docs = []
            for row in lc_data:
                sid, chid = row
                docs.append({"server_id": str(sid), "channel_id": str(chid)})
            await self.db["locked_channels"].insert_many(docs)

        # ping_roles
        c.execute("SELECT server_id, role_id FROM ping_roles")
        pr_data = c.fetchall()
        if pr_data:
            docs = []
            for row in pr_data:
                sid, rid = row
                docs.append({"server_id": str(sid), "role_id": str(rid)})
            await self.db["ping_roles"].insert_many(docs)

        # automod_exempt_roles
        # In original schema, the table is automod_exempt_roles. In code, we also handle automod_exempt_roles.
        c.execute("SELECT server_id, role_id FROM automod_exempt_roles")
        aer_data = c.fetchall()
        if aer_data:
            docs = []
            for row in aer_data:
                sid, rid = row
                docs.append({"server_id": str(sid), "role_id": str(rid)})
            await self.db["automod_exempt_roles"].insert_many(docs)

        # protected_users (in code it's called 'protected_users', in schema it was 'automod_protected_users')
        # The code uses 'protected_users' table name. Let's check schema and code difference:
        # Code: CREATE TABLE IF NOT EXISTS protected_users
        # Schema: CREATE TABLE IF NOT EXISTS automod_protected_users
        # The final code references protected_users. Let's read from either if it exists:
        try:
            c.execute("SELECT server_id, user_id FROM protected_users")
            pu_data = c.fetchall()
        except sqlite3.OperationalError:
            # maybe table name is automod_protected_users in schema
            c.execute("SELECT server_id, user_id FROM automod_protected_users")
            pu_data = c.fetchall()

        if pu_data:
            docs = []
            for row in pu_data:
                sid, uid = row
                docs.append({"server_id": str(sid), "user_id": str(uid)})
            await self.db["protected_users"].insert_many(docs)

        conn.close()
        self.logger.info("Migration from SQLite to MongoDB completed.")

    # ---------------------------
    # Methods for Managing Warns
    # ---------------------------
    async def add_warn(self, user_id: int, server_id: int, moderator_id: int, reason: str) -> int:
        # Find max id for that user & server
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
        # Convert created_at to unix timestamp (if needed)
        for w in warnings:
            w["created_at"] = str(int(datetime.fromisoformat(w["created_at"]).timestamp()))
        self.logger.info(f"Fetched all warnings: {len(warnings)} records found.")
        # Return in same format: user_id, server_id, moderator_id, reason, created_at, id
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
        # expiration_timestamp is in UNIX time
        # compare to created_at converted back to UNIX
        # We'll fetch and check individually or just do a comparison:
        # More efficient way: We'll do a bulk operation after fetching which are expired
        all_warnings = await self.db["warns"].find({}).to_list(None)
        to_remove_ids = []
        for w in all_warnings:
            ts = int(datetime.fromisoformat(w["created_at"]).timestamp())
            if ts < expiration_timestamp:
                to_remove_ids.append(w["_id"])
        if to_remove_ids:
            result = await self.db["warns"].delete_many({"_id": {"$in": to_remove_ids}})
            removed = result.deleted_count
        else:
            removed = 0
        self.logger.info(f"Removed {removed} expired warnings older than timestamp {expiration_timestamp}.")
        return removed

    # ---------------------------
    # Methods for Server Settings
    # ---------------------------
    async def initialize_server_settings(self, server_id: int):
        await self.db["server_settings"].update_one(
            {"server_id": str(server_id)},
            {"$setOnInsert": {
                "automod_enabled": True,
                "automod_logging_enabled": False,
                "automod_log_channel_id": None,
                "tryout_channel_id": None,
                "mod_log_channel_id": None,
                "automod_mute_duration": 3600
            }},
            upsert=True
        )
        self.logger.info(f"Initialized server settings for server {server_id}.")

    async def get_server_settings(self, server_id: int) -> dict:
        settings = await self.db["server_settings"].find_one({"server_id": str(server_id)})
        if not settings:
            await self.initialize_server_settings(server_id)
            settings = {
                'automod_enabled': True,
                'automod_logging_enabled': False,
                'automod_log_channel_id': None,
                'tryout_channel_id': None,
                'mod_log_channel_id': None,
                'automod_mute_duration': 3600
            }
            self.logger.info(f"Initialized and fetched default server settings for server {server_id}: {settings}")
        else:
            # Convert fields as needed
            settings = {
                'automod_enabled': bool(settings.get('automod_enabled', True)),
                'automod_logging_enabled': bool(settings.get('automod_logging_enabled', False)),
                'automod_log_channel_id': int(settings['automod_log_channel_id']) if settings.get('automod_log_channel_id') else None,
                'tryout_channel_id': int(settings['tryout_channel_id']) if settings.get('tryout_channel_id') else None,
                'mod_log_channel_id': int(settings['mod_log_channel_id']) if settings.get('mod_log_channel_id') else None,
                'automod_mute_duration': int(settings.get('automod_mute_duration', 3600))
            }
            self.logger.info(f"Fetched server settings for server {server_id}: {settings}")
        return settings

    async def update_server_setting(self, server_id: int, setting_name: str, value):
        await self.db["server_settings"].update_one(
            {"server_id": str(server_id)},
            {"$set": {setting_name: value}}
        )
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

    # ---------------------------
    # Automod Mute Duration Methods
    # ---------------------------
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
        users = await self.db["protected_users"].find({"server_id": str(server_id)}).to_list(None)
        user_ids = [int(u["user_id"]) for u in users]
        self.logger.info(f"Fetched protected users for server {server_id}: {user_ids}")
        return user_ids

    async def add_protected_user(self, server_id: int, user_id: int):
        try:
            await self.db["protected_users"].insert_one({"server_id": str(server_id), "user_id": str(user_id)})
            self.logger.info(f"Added protected user {user_id} to server {server_id}.")
        except:
            self.logger.warning(f"Protected user {user_id} already exists in server {server_id}.")

    async def remove_protected_user(self, server_id: int, user_id: int):
        await self.db["protected_users"].delete_one({"server_id": str(server_id), "user_id": str(user_id)})
        self.logger.info(f"Removed protected user {user_id} from server {server_id}.")

    # ---------------------------
    # Methods for Exempt Roles (Alias for Automod Exempt Roles)
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
        roles = await self.db["moderation_allowed_roles"].find({"server_id": str(server_id)}).to_list(None)
        role_ids = [int(r["role_id"]) for r in roles]
        self.logger.info(f"Fetched moderation allowed roles for server {server_id}: {role_ids}")
        return role_ids

    async def add_moderation_allowed_role(self, server_id: int, role_id: int):
        try:
            await self.db["moderation_allowed_roles"].insert_one({"server_id": str(server_id), "role_id": str(role_id)})
            self.logger.info(f"Added role {role_id} to moderation allowed roles in server {server_id}.")
        except:
            self.logger.warning(f"Role {role_id} already exists in moderation allowed roles for server {server_id}.")

    async def remove_moderation_allowed_role(self, server_id: int, role_id: int):
        await self.db["moderation_allowed_roles"].delete_one({"server_id": str(server_id), "role_id": str(role_id)})
        self.logger.info(f"Removed role {role_id} from moderation allowed roles in server {server_id}.")

    # ---------------------------
    # Methods for Moderation Log Channel
    # ---------------------------
    async def set_mod_log_channel(self, server_id: int, channel_id: int):
        await self.update_server_setting(server_id, "mod_log_channel_id", str(channel_id))
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
        groups = await self.db["tryout_groups"].find({"server_id": str(server_id)}).to_list(None)
        self.logger.info(f"Fetched {len(groups)} tryout groups for server {server_id}.")
        return [(g["group_id"], g["description"], g["link"], g["event_name"]) for g in groups]

    async def get_tryout_group(self, server_id: int, group_id: str):
        group = await self.db["tryout_groups"].find_one({"server_id": str(server_id), "group_id": str(group_id)})
        self.logger.info(f"Fetched tryout group '{group_id}' for server {server_id}: {group}")
        if group:
            return (group["group_id"], group["description"], group["link"], group["event_name"])
        return None

    async def add_tryout_group(self, server_id: int, group_id: str, description: str, link: str, event_name: str):
        try:
            await self.db["tryout_groups"].insert_one({
                "server_id": str(server_id),
                "group_id": group_id,
                "description": description,
                "link": link,
                "event_name": event_name
            })
            self.logger.info(f"Added tryout group '{group_id}' for server {server_id}.")
        except:
            self.logger.warning(f"Tryout group '{group_id}' already exists in server {server_id}.")
            raise RuntimeError(f"Tryout group '{group_id}' already exists.")

    async def update_tryout_group(self, server_id: int, group_id: str, description: str, link: str, event_name: str):
        result = await self.db["tryout_groups"].update_one(
            {"server_id": str(server_id), "group_id": group_id},
            {"$set": {"description": description, "link": link, "event_name": event_name}}
        )
        if result.modified_count == 0:
            self.logger.warning(f"No tryout group '{group_id}' found to update in server {server_id}.")
        else:
            self.logger.info(f"Updated tryout group '{group_id}' for server {server_id}.")

    async def delete_tryout_group(self, server_id: int, group_id: str):
        await self.db["tryout_groups"].delete_one({"server_id": str(server_id), "group_id": group_id})
        self.logger.info(f"Deleted tryout group '{group_id}' from server {server_id}.")

    # ---------------------------
    # Methods for Tryout Required Roles
    # ---------------------------
    async def get_tryout_required_roles(self, server_id: int) -> list:
        roles = await self.db["tryout_required_roles"].find({"server_id": str(server_id)}).to_list(None)
        role_ids = [int(r["role_id"]) for r in roles]
        self.logger.info(f"Fetched {len(role_ids)} tryout required roles for server {server_id}.")
        return role_ids

    async def add_tryout_required_role(self, server_id: int, role_id: int):
        try:
            await self.db["tryout_required_roles"].insert_one({"server_id": str(server_id), "role_id": str(role_id)})
            self.logger.info(f"Added tryout required role {role_id} to server {server_id}.")
        except:
            self.logger.warning(f"Tryout required role {role_id} already exists in server {server_id}.")
            raise RuntimeError(f"Tryout required role {role_id} already exists.")

    async def remove_tryout_required_role(self, server_id: int, role_id: int):
        await self.db["tryout_required_roles"].delete_one({"server_id": str(server_id), "role_id": str(role_id)})
        self.logger.info(f"Removed tryout required role {role_id} from server {server_id}.")

    # ---------------------------
    # Methods for Tryout Settings
    # ---------------------------
    async def get_tryout_channel_id(self, server_id: int) -> int:
        setting = await self.db["tryout_settings"].find_one({"server_id": str(server_id)})
        tcid = int(setting["tryout_channel_id"]) if setting and setting["tryout_channel_id"] else None
        self.logger.info(f"Fetched tryout channel ID for server {server_id}: {tcid}")
        return tcid

    async def set_tryout_channel_id(self, server_id: int, channel_id: int):
        await self.db["tryout_settings"].update_one(
            {"server_id": str(server_id)},
            {"$set": {"tryout_channel_id": str(channel_id)}},
            upsert=True
        )
        self.logger.info(f"Set tryout channel ID to {channel_id} for server {server_id}.")

    # ---------------------------
    # Methods for Ping Roles
    # ---------------------------
    async def get_ping_roles(self, server_id: int) -> list:
        roles = await self.db["ping_roles"].find({"server_id": str(server_id)}).to_list(None)
        role_ids = [int(r["role_id"]) for r in roles]
        self.logger.info(f"Fetched {len(role_ids)} ping roles for server {server_id}.")
        return role_ids

    async def add_ping_role(self, server_id: int, role_id: int):
        try:
            await self.db["ping_roles"].insert_one({"server_id": str(server_id), "role_id": str(role_id)})
            self.logger.info(f"Added ping role {role_id} to server {server_id}.")
        except:
            self.logger.warning(f"Ping role {role_id} already exists in server {server_id}.")
            raise RuntimeError(f"Ping role {role_id} already exists.")

    async def remove_ping_role(self, server_id: int, role_id: int):
        await self.db["ping_roles"].delete_one({"server_id": str(server_id), "role_id": str(role_id)})
        self.logger.info(f"Removed ping role {role_id} from server {server_id}.")

    # ---------------------------
    # Methods for Locking Channels
    # ---------------------------
    async def lock_channel_in_db(self, server_id: int, channel_id: int):
        try:
            await self.db["locked_channels"].insert_one({"server_id": str(server_id), "channel_id": str(channel_id)})
            self.logger.info(f"Locked channel {channel_id} in server {server_id} and recorded in DB.")
        except:
            self.logger.warning(f"Channel {channel_id} in server {server_id} is already locked.")

    async def unlock_channel_in_db(self, server_id: int, channel_id: int):
        await self.db["locked_channels"].delete_one({"server_id": str(server_id), "channel_id": str(channel_id)})
        self.logger.info(f"Unlocked channel {channel_id} in server {server_id} and removed from DB.")

    async def is_channel_locked(self, server_id: int, channel_id: int) -> bool:
        result = await self.db["locked_channels"].find_one({"server_id": str(server_id), "channel_id": str(channel_id)})
        is_locked = result is not None
        self.logger.info(f"Channel {channel_id} in server {server_id} is_locked: {is_locked}")
        return is_locked

    # ---------------------------
    # Methods for Automod Exempt Roles
    # ---------------------------
    async def get_automod_exempt_roles(self, server_id: int) -> list:
        roles = await self.db["automod_exempt_roles"].find({"server_id": str(server_id)}).to_list(None)
        role_ids = [int(r["role_id"]) for r in roles]
        self.logger.info(f"Fetched automod exempt roles for server {server_id}: {role_ids}")
        return role_ids

    async def add_automod_exempt_role(self, server_id: int, role_id: int):
        try:
            await self.db["automod_exempt_roles"].insert_one({"server_id": str(server_id), "role_id": str(role_id)})
            self.logger.info(f"Added automod exempt role {role_id} to server {server_id}.")
        except:
            self.logger.warning(f"Automod exempt role {role_id} already exists in server {server_id}.")
            raise RuntimeError(f"Automod exempt role {role_id} already exists.")

    async def remove_automod_exempt_role(self, server_id: int, role_id: int):
        await self.db["automod_exempt_roles"].delete_one({"server_id": str(server_id), "role_id": str(role_id)})
        self.logger.info(f"Removed automod exempt role {role_id} from server {server_id}.")

    async def close(self):
        """
        Closes the database connection.
        For MongoDB, this is optional since motor handles connection pooling.
        """
        self.logger.info("MongoDB connection closed (not strictly necessary).")
