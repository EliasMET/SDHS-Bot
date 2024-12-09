import aiosqlite
import logging

class DatabaseManager:
    def __init__(self, *, connection: aiosqlite.Connection) -> None:
        self.connection = connection
        self.logger = logging.getLogger('DatabaseManager')

    async def initialize_database(self):
        """
        Initializes the database by creating necessary tables if they do not exist,
        and ensures columns are present.
        """
        try:
            await self.connection.execute("""
                CREATE TABLE IF NOT EXISTS warns (
                    id INTEGER PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    server_id TEXT NOT NULL,
                    moderator_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

            await self.connection.execute("""
                CREATE TABLE IF NOT EXISTS server_settings (
                    server_id TEXT PRIMARY KEY,
                    automod_enabled INTEGER NOT NULL DEFAULT 1,
                    automod_logging_enabled INTEGER NOT NULL DEFAULT 0,
                    automod_log_channel_id TEXT,
                    tryout_channel_id TEXT,
                    mod_log_channel_id TEXT
                );
            """)

            # Ensure automod_mute_duration column exists
            await self.ensure_column_exists("server_settings", "automod_mute_duration", "INTEGER NOT NULL DEFAULT 3600")

            await self.connection.execute("""
                CREATE TABLE IF NOT EXISTS moderation_allowed_roles (
                    server_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    PRIMARY KEY (server_id, role_id)
                );
            """)

            await self.connection.execute("""
                CREATE TABLE IF NOT EXISTS tryout_groups (
                    server_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    description TEXT NOT NULL,
                    link TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    PRIMARY KEY (server_id, group_id)
                );
            """)

            await self.connection.execute("""
                CREATE TABLE IF NOT EXISTS tryout_required_roles (
                    server_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    PRIMARY KEY (server_id, role_id)
                );
            """)

            await self.connection.execute("""
                CREATE TABLE IF NOT EXISTS tryout_settings (
                    server_id TEXT NOT NULL PRIMARY KEY,
                    tryout_channel_id TEXT
                );
            """)

            await self.connection.execute("""
                CREATE TABLE IF NOT EXISTS locked_channels (
                    server_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    PRIMARY KEY (server_id, channel_id)
                );
            """)

            await self.connection.execute("""
                CREATE TABLE IF NOT EXISTS ping_roles (
                    server_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    PRIMARY KEY (server_id, role_id)
                );
            """)

            # Automod exempt roles
            await self.connection.execute("""
                CREATE TABLE IF NOT EXISTS automod_exempt_roles (
                    server_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    PRIMARY KEY (server_id, role_id)
                );
            """)

            # Protected users
            await self.connection.execute("""
                CREATE TABLE IF NOT EXISTS protected_users (
                    server_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    PRIMARY KEY (server_id, user_id)
                );
            """)

            await self.connection.commit()
            self.logger.info("Database initialized and tables ensured.")
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise RuntimeError(f"Failed to initialize database: {e}")

    async def ensure_column_exists(self, table: str, column: str, column_def: str):
        """
        Ensures that a column exists in a given table. If it doesn't, it will be added.
        """
        try:
            async with self.connection.execute(f"PRAGMA table_info({table})") as cursor:
                cols = await cursor.fetchall()
                col_names = [c[1] for c in cols]

            if column not in col_names:
                # Add the column
                await self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def};")
                await self.connection.commit()
                self.logger.info(f"Added missing column '{column}' to table '{table}'.")
        except Exception as e:
            self.logger.error(f"Failed to ensure column exists '{column}' in '{table}': {e}")
            raise RuntimeError(f"Failed to ensure column exists: {e}")

    # ---------------------------
    # Methods for Managing Warns
    # ---------------------------

    async def add_warn(self, user_id: int, server_id: int, moderator_id: int, reason: str) -> int:
        try:
            async with self.connection.execute(
                "SELECT MAX(id) FROM warns WHERE user_id=? AND server_id=?",
                (str(user_id), str(server_id)),
            ) as cursor:
                result = await cursor.fetchone()
                warn_id = (result[0] or 0) + 1
            await self.connection.execute(
                "INSERT INTO warns(id, user_id, server_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (warn_id, str(user_id), str(server_id), str(moderator_id), reason),
            )
            await self.connection.commit()
            self.logger.info(f"Added warn ID {warn_id} for user {user_id} in server {server_id}.")
            return warn_id
        except Exception as e:
            self.logger.error(f"Failed to add warn: {e}")
            raise RuntimeError(f"Failed to add warn: {e}")

    async def remove_warn(self, warn_id: int, user_id: int, server_id: int) -> bool:
        try:
            async with self.connection.execute(
                "DELETE FROM warns WHERE id=? AND user_id=? AND server_id=?",
                (warn_id, str(user_id), str(server_id)),
            ) as cursor:
                await self.connection.commit()
                removed = cursor.rowcount > 0
                self.logger.info(f"Removed warn ID {warn_id} for user {user_id} in server {server_id}: {removed}")
                return removed
        except Exception as e:
            self.logger.error(f"Failed to remove warn: {e}")
            raise RuntimeError(f"Failed to remove warn: {e}")

    async def get_all_warnings(self) -> list:
        try:
            async with self.connection.execute(
                "SELECT user_id, server_id, moderator_id, reason, strftime('%s', created_at), id FROM warns"
            ) as cursor:
                warnings = await cursor.fetchall()
                self.logger.info(f"Fetched all warnings: {len(warnings)} records found.")
                return warnings
        except Exception as e:
            self.logger.error(f"Failed to fetch all warnings: {e}")
            raise RuntimeError(f"Failed to fetch all warnings: {e}")

    async def get_warnings(self, user_id: int, server_id: int) -> list:
        try:
            async with self.connection.execute(
                "SELECT user_id, server_id, moderator_id, reason, strftime('%s', created_at), id FROM warns WHERE user_id=? AND server_id=?",
                (str(user_id), str(server_id)),
            ) as cursor:
                warnings = await cursor.fetchall()
                self.logger.info(f"Fetched {len(warnings)} warnings for user {user_id} in server {server_id}.")
                return warnings
        except Exception as e:
            self.logger.error(f"Failed to fetch warnings: {e}")
            raise RuntimeError(f"Failed to fetch warnings: {e}")

    async def clear_all_warnings(self, user_id: int, server_id: int) -> int:
        try:
            async with self.connection.execute(
                "DELETE FROM warns WHERE user_id=? AND server_id=?", (str(user_id), str(server_id))
            ) as cursor:
                await self.connection.commit()
                removed = cursor.rowcount
                self.logger.info(f"Cleared {removed} warnings for user {user_id} in server {server_id}.")
                return removed
        except Exception as e:
            self.logger.error(f"Failed to clear all warnings: {e}")
            raise RuntimeError(f"Failed to clear all warnings: {e}")

    async def count_warnings(self, user_id: int, server_id: int) -> int:
        try:
            async with self.connection.execute(
                "SELECT COUNT(*) FROM warns WHERE user_id=? AND server_id=?",
                (str(user_id), str(server_id)),
            ) as cursor:
                result = await cursor.fetchone()
                count = result[0] if result else 0
                self.logger.info(f"User {user_id} has {count} warnings in server {server_id}.")
                return count
        except Exception as e:
            self.logger.error(f"Failed to count warnings: {e}")
            raise RuntimeError(f"Failed to count warnings: {e}")

    async def remove_expired_warnings(self, expiration_timestamp: int) -> int:
        try:
            async with self.connection.execute(
                "DELETE FROM warns WHERE strftime('%s', created_at) < ?",
                (str(expiration_timestamp),),
            ) as cursor:
                await self.connection.commit()
                removed = cursor.rowcount
                self.logger.info(f"Removed {removed} expired warnings older than timestamp {expiration_timestamp}.")
                return removed
        except Exception as e:
            self.logger.error(f"Failed to remove expired warnings: {e}")
            raise RuntimeError(f"Failed to remove expired warnings: {e}")

    # ---------------------------
    # Methods for Server Settings
    # ---------------------------

    async def initialize_server_settings(self, server_id: int):
        try:
            await self.connection.execute(
                "INSERT OR IGNORE INTO server_settings (server_id, automod_enabled, automod_logging_enabled, automod_log_channel_id, tryout_channel_id, mod_log_channel_id, automod_mute_duration) VALUES (?, 1, 0, NULL, NULL, NULL, 3600)",
                (str(server_id),)
            )
            await self.connection.commit()
            self.logger.info(f"Initialized server settings for server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to initialize server settings: {e}")
            raise RuntimeError(f"Failed to initialize server settings: {e}")

    async def get_server_settings(self, server_id: int) -> dict:
        try:
            async with self.connection.execute(
                "SELECT automod_enabled, automod_logging_enabled, automod_log_channel_id, tryout_channel_id, mod_log_channel_id, automod_mute_duration FROM server_settings WHERE server_id=?",
                (str(server_id),)
            ) as cursor:
                result = await cursor.fetchone()
                if result:
                    settings = {
                        'automod_enabled': bool(result[0]),
                        'automod_logging_enabled': bool(result[1]),
                        'automod_log_channel_id': int(result[2]) if result[2] else None,
                        'tryout_channel_id': int(result[3]) if result[3] else None,
                        'mod_log_channel_id': int(result[4]) if result[4] else None,
                        'automod_mute_duration': int(result[5]) if result[5] else 3600
                    }
                    self.logger.info(f"Fetched server settings for server {server_id}: {settings}")
                    return settings
                else:
                    # Initialize settings if they do not exist
                    await self.initialize_server_settings(server_id)
                    default_settings = {
                        'automod_enabled': True,
                        'automod_logging_enabled': False,
                        'automod_log_channel_id': None,
                        'tryout_channel_id': None,
                        'mod_log_channel_id': None,
                        'automod_mute_duration': 3600
                    }
                    self.logger.info(f"Initialized and fetched default server settings for server {server_id}: {default_settings}")
                    return default_settings
        except Exception as e:
            self.logger.error(f"Failed to get server settings: {e}")
            raise RuntimeError(f"Failed to get server settings: {e}")

    async def update_server_setting(self, server_id: int, setting_name: str, value):
        try:
            query = f"UPDATE server_settings SET {setting_name} = ? WHERE server_id = ?"
            await self.connection.execute(query, (str(value) if value is not None else None, str(server_id)))
            await self.connection.commit()
            self.logger.info(f"Updated server setting '{setting_name}' for server {server_id} to '{value}'.")
        except Exception as e:
            self.logger.error(f"Failed to update server setting '{setting_name}': {e}")
            raise RuntimeError(f"Failed to update server setting '{setting_name}': {e}")

    async def toggle_server_setting(self, server_id: int, setting_name: str):
        try:
            current_settings = await self.get_server_settings(server_id)
            current_value = current_settings.get(setting_name)
            if isinstance(current_value, bool):
                new_value = int(not current_value)
            elif isinstance(current_value, (int, float)):
                new_value = 0 if current_value else 1
            else:
                new_value = 1  # Default toggle
            await self.update_server_setting(server_id, setting_name, new_value)
            self.logger.info(f"Toggled server setting '{setting_name}' for server {server_id} to '{new_value}'.")
        except Exception as e:
            self.logger.error(f"Failed to toggle server setting '{setting_name}': {e}")
            raise RuntimeError(f"Failed to toggle server setting '{setting_name}': {e}")

    # ---------------------------
    # Automod Mute Duration Methods
    # ---------------------------

    async def get_automod_mute_duration(self, server_id: int) -> int:
        try:
            async with self.connection.execute(
                "SELECT automod_mute_duration FROM server_settings WHERE server_id = ?",
                (str(server_id),)
            ) as cursor:
                result = await cursor.fetchone()
                duration = int(result[0]) if result and result[0] else 3600
                self.logger.info(f"Fetched automod mute duration for server {server_id}: {duration} seconds")
                return duration
        except Exception as e:
            self.logger.error(f"Failed to get automod mute duration: {e}")
            raise RuntimeError(f"Failed to get automod mute duration: {e}")

    async def set_automod_mute_duration(self, server_id: int, duration: int):
        try:
            await self.connection.execute(
                "UPDATE server_settings SET automod_mute_duration = ? WHERE server_id = ?",
                (str(duration), str(server_id))
            )
            await self.connection.commit()
            self.logger.info(f"Set automod mute duration to {duration} seconds for server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to set automod mute duration: {e}")
            raise RuntimeError(f"Failed to set automod mute duration: {e}")

    # ---------------------------
    # Methods for Protected Users
    # ---------------------------

    async def get_protected_users(self, server_id: int) -> list:
        """
        Retrieves a list of user IDs that are protected from automod.
        """
        try:
            async with self.connection.execute(
                "SELECT user_id FROM protected_users WHERE server_id = ?",
                (str(server_id),)
            ) as cursor:
                users = await cursor.fetchall()
                user_ids = [int(u[0]) for u in users]
                self.logger.info(f"Fetched protected users for server {server_id}: {user_ids}")
                return user_ids
        except Exception as e:
            self.logger.error(f"Failed to get protected users: {e}")
            raise RuntimeError(f"Failed to get protected users: {e}")

    async def add_protected_user(self, server_id: int, user_id: int):
        """
        Adds a user to the list of protected users.
        """
        try:
            await self.connection.execute(
                "INSERT INTO protected_users (server_id, user_id) VALUES (?, ?)",
                (str(server_id), str(user_id))
            )
            await self.connection.commit()
            self.logger.info(f"Added protected user {user_id} to server {server_id}.")
        except aiosqlite.IntegrityError:
            self.logger.warning(f"Protected user {user_id} already exists in server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to add protected user: {e}")
            raise RuntimeError(f"Failed to add protected user: {e}")

    async def remove_protected_user(self, server_id: int, user_id: int):
        """
        Removes a user from the list of protected users.
        """
        try:
            await self.connection.execute(
                "DELETE FROM protected_users WHERE server_id = ? AND user_id = ?",
                (str(server_id), str(user_id))
            )
            await self.connection.commit()
            self.logger.info(f"Removed protected user {user_id} from server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to remove protected user: {e}")
            raise RuntimeError(f"Failed to remove protected user: {e}")

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
        try:
            async with self.connection.execute(
                "SELECT role_id FROM moderation_allowed_roles WHERE server_id = ?",
                (str(server_id),)
            ) as cursor:
                roles = await cursor.fetchall()
                role_ids = [int(role[0]) for role in roles]
                self.logger.info(f"Fetched moderation allowed roles for server {server_id}: {role_ids}")
                return role_ids
        except Exception as e:
            self.logger.error(f"Failed to get moderation allowed roles: {e}")
            raise RuntimeError(f"Failed to get moderation allowed roles: {e}")

    async def add_moderation_allowed_role(self, server_id: int, role_id: int):
        try:
            await self.connection.execute(
                "INSERT INTO moderation_allowed_roles (server_id, role_id) VALUES (?, ?)",
                (str(server_id), str(role_id))
            )
            await self.connection.commit()
            self.logger.info(f"Added role {role_id} to moderation allowed roles in server {server_id}.")
        except aiosqlite.IntegrityError:
            self.logger.warning(f"Role {role_id} already exists in moderation allowed roles for server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to add moderation allowed role: {e}")
            raise RuntimeError(f"Failed to add moderation allowed role: {e}")

    async def remove_moderation_allowed_role(self, server_id: int, role_id: int):
        try:
            await self.connection.execute(
                "DELETE FROM moderation_allowed_roles WHERE server_id = ? AND role_id = ?",
                (str(server_id), str(role_id))
            )
            await self.connection.commit()
            self.logger.info(f"Removed role {role_id} from moderation allowed roles in server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to remove moderation allowed role: {e}")
            raise RuntimeError(f"Failed to remove moderation allowed role: {e}")

    # ---------------------------
    # Methods for Moderation Log Channel
    # ---------------------------

    async def set_mod_log_channel(self, server_id: int, channel_id: int):
        try:
            await self.connection.execute(
                "UPDATE server_settings SET mod_log_channel_id = ? WHERE server_id = ?",
                (str(channel_id), str(server_id))
            )
            await self.connection.commit()
            self.logger.info(f"Set moderation log channel to {channel_id} for server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to set moderation log channel: {e}")
            raise RuntimeError(f"Failed to set moderation log channel: {e}")

    async def get_mod_log_channel(self, server_id: int) -> int:
        try:
            async with self.connection.execute(
                "SELECT mod_log_channel_id FROM server_settings WHERE server_id = ?",
                (str(server_id),)
            ) as cursor:
                result = await cursor.fetchone()
                mod_log_channel_id = int(result[0]) if result and result[0] else None
                self.logger.info(f"Fetched moderation log channel ID for server {server_id}: {mod_log_channel_id}")
                return mod_log_channel_id
        except Exception as e:
            self.logger.error(f"Failed to get moderation log channel: {e}")
            raise RuntimeError(f"Failed to get moderation log channel: {e}")

    # ---------------------------
    # Methods for Tryout Groups
    # ---------------------------

    async def get_tryout_groups(self, server_id: int) -> list:
        try:
            async with self.connection.execute(
                "SELECT group_id, description, link, event_name FROM tryout_groups WHERE server_id = ?",
                (str(server_id),)
            ) as cursor:
                groups = await cursor.fetchall()
                self.logger.info(f"Fetched {len(groups)} tryout groups for server {server_id}.")
                return groups
        except Exception as e:
            self.logger.error(f"Failed to get tryout groups: {e}")
            raise RuntimeError(f"Failed to get tryout groups: {e}")

    async def get_tryout_group(self, server_id: int, group_id: str):
        try:
            async with self.connection.execute(
                "SELECT group_id, description, link, event_name FROM tryout_groups WHERE server_id = ? AND group_id = ?",
                (str(server_id), group_id)
            ) as cursor:
                group = await cursor.fetchone()
                self.logger.info(f"Fetched tryout group '{group_id}' for server {server_id}: {group}")
                return group
        except Exception as e:
            self.logger.error(f"Failed to get tryout group: {e}")
            raise RuntimeError(f"Failed to get tryout group: {e}")

    async def add_tryout_group(self, server_id: int, group_id: str, description: str, link: str, event_name: str):
        try:
            await self.connection.execute(
                "INSERT INTO tryout_groups (server_id, group_id, description, link, event_name) VALUES (?, ?, ?, ?, ?)",
                (str(server_id), group_id, description, link, event_name)
            )
            await self.connection.commit()
            self.logger.info(f"Added tryout group '{group_id}' for server {server_id}.")
        except aiosqlite.IntegrityError:
            self.logger.warning(f"Tryout group '{group_id}' already exists in server {server_id}.")
            raise RuntimeError(f"Tryout group '{group_id}' already exists.")
        except Exception as e:
            self.logger.error(f"Failed to add tryout group: {e}")
            raise RuntimeError(f"Failed to add tryout group: {e}")

    async def update_tryout_group(self, server_id: int, group_id: str, description: str, link: str, event_name: str):
        try:
            await self.connection.execute(
                "UPDATE tryout_groups SET description = ?, link = ?, event_name = ? WHERE server_id = ? AND group_id = ?",
                (description, link, event_name, str(server_id), group_id)
            )
            await self.connection.commit()
            self.logger.info(f"Updated tryout group '{group_id}' for server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to update tryout group: {e}")
            raise RuntimeError(f"Failed to update tryout group: {e}")

    async def delete_tryout_group(self, server_id: int, group_id: str):
        try:
            await self.connection.execute(
                "DELETE FROM tryout_groups WHERE server_id = ? AND group_id = ?",
                (str(server_id), group_id)
            )
            await self.connection.commit()
            self.logger.info(f"Deleted tryout group '{group_id}' from server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to delete tryout group: {e}")
            raise RuntimeError(f"Failed to delete tryout group: {e}")

    # ---------------------------
    # Methods for Tryout Required Roles
    # ---------------------------

    async def get_tryout_required_roles(self, server_id: int) -> list:
        try:
            async with self.connection.execute(
                "SELECT role_id FROM tryout_required_roles WHERE server_id = ?",
                (str(server_id),)
            ) as cursor:
                roles = await cursor.fetchall()
                role_ids = [int(role[0]) for role in roles]
                self.logger.info(f"Fetched {len(role_ids)} tryout required roles for server {server_id}.")
                return role_ids
        except Exception as e:
            self.logger.error(f"Failed to get tryout required roles: {e}")
            raise RuntimeError(f"Failed to get tryout required roles: {e}")

    async def add_tryout_required_role(self, server_id: int, role_id: int):
        try:
            await self.connection.execute(
                "INSERT INTO tryout_required_roles (server_id, role_id) VALUES (?, ?)",
                (str(server_id), str(role_id))
            )
            await self.connection.commit()
            self.logger.info(f"Added tryout required role {role_id} to server {server_id}.")
        except aiosqlite.IntegrityError:
            self.logger.warning(f"Tryout required role {role_id} already exists in server {server_id}.")
            raise RuntimeError(f"Tryout required role {role_id} already exists.")
        except Exception as e:
            self.logger.error(f"Failed to add tryout required role: {e}")
            raise RuntimeError(f"Failed to add tryout required role: {e}")

    async def remove_tryout_required_role(self, server_id: int, role_id: int):
        try:
            await self.connection.execute(
                "DELETE FROM tryout_required_roles WHERE server_id = ? AND role_id = ?",
                (str(server_id), str(role_id))
            )
            await self.connection.commit()
            self.logger.info(f"Removed tryout required role {role_id} from server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to remove tryout required role: {e}")
            raise RuntimeError(f"Failed to remove tryout required role: {e}")

    # ---------------------------
    # Methods for Tryout Settings
    # ---------------------------

    async def get_tryout_channel_id(self, server_id: int) -> int:
        try:
            async with self.connection.execute(
                "SELECT tryout_channel_id FROM tryout_settings WHERE server_id = ?",
                (str(server_id),)
            ) as cursor:
                result = await cursor.fetchone()
                tryout_channel_id = int(result[0]) if result and result[0] else None
                self.logger.info(f"Fetched tryout channel ID for server {server_id}: {tryout_channel_id}")
                return tryout_channel_id
        except Exception as e:
            self.logger.error(f"Failed to get tryout channel ID: {e}")
            raise RuntimeError(f"Failed to get tryout channel ID: {e}")

    async def set_tryout_channel_id(self, server_id: int, channel_id: int):
        try:
            await self.connection.execute(
                "INSERT OR REPLACE INTO tryout_settings (server_id, tryout_channel_id) VALUES (?, ?)",
                (str(server_id), str(channel_id))
            )
            await self.connection.commit()
            self.logger.info(f"Set tryout channel ID to {channel_id} for server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to set tryout channel: {e}")
            raise RuntimeError(f"Failed to set tryout channel: {e}")

    # ---------------------------
    # Methods for Ping Roles (Under Tryouts)
    # ---------------------------

    async def get_ping_roles(self, server_id: int) -> list:
        try:
            async with self.connection.execute(
                "SELECT role_id FROM ping_roles WHERE server_id = ?",
                (str(server_id),)
            ) as cursor:
                roles = await cursor.fetchall()
                role_ids = [int(role[0]) for role in roles]
                self.logger.info(f"Fetched {len(role_ids)} ping roles for server {server_id}.")
                return role_ids
        except Exception as e:
            self.logger.error(f"Failed to get ping roles: {e}")
            raise RuntimeError(f"Failed to get ping roles: {e}")

    async def add_ping_role(self, server_id: int, role_id: int):
        try:
            await self.connection.execute(
                "INSERT INTO ping_roles (server_id, role_id) VALUES (?, ?)",
                (str(server_id), str(role_id))
            )
            await self.connection.commit()
            self.logger.info(f"Added ping role {role_id} to server {server_id}.")
        except aiosqlite.IntegrityError:
            self.logger.warning(f"Ping role {role_id} already exists in server {server_id}.")
            raise RuntimeError(f"Ping role {role_id} already exists.")
        except Exception as e:
            self.logger.error(f"Failed to add ping role: {e}")
            raise RuntimeError(f"Failed to add ping role: {e}")

    async def remove_ping_role(self, server_id: int, role_id: int):
        try:
            await self.connection.execute(
                "DELETE FROM ping_roles WHERE server_id = ? AND role_id = ?",
                (str(server_id), str(role_id))
            )
            await self.connection.commit()
            self.logger.info(f"Removed ping role {role_id} from server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to remove ping role: {e}")
            raise RuntimeError(f"Failed to remove ping role: {e}")

    # ---------------------------
    # Methods for Locking Channels
    # ---------------------------

    async def lock_channel_in_db(self, server_id: int, channel_id: int):
        try:
            await self.connection.execute(
                "INSERT INTO locked_channels (server_id, channel_id) VALUES (?, ?)",
                (str(server_id), str(channel_id))
            )
            await self.connection.commit()
            self.logger.info(f"Locked channel {channel_id} in server {server_id} and recorded in DB.")
        except aiosqlite.IntegrityError:
            self.logger.warning(f"Channel {channel_id} in server {server_id} is already locked.")
        except Exception as e:
            self.logger.error(f"Failed to lock channel in DB: {e}")
            raise RuntimeError(f"Failed to lock channel in DB: {e}")

    async def unlock_channel_in_db(self, server_id: int, channel_id: int):
        try:
            await self.connection.execute(
                "DELETE FROM locked_channels WHERE server_id = ? AND channel_id = ?",
                (str(server_id), str(channel_id))
            )
            await self.connection.commit()
            self.logger.info(f"Unlocked channel {channel_id} in server {server_id} and removed from DB.")
        except Exception as e:
            self.logger.error(f"Failed to unlock channel in DB: {e}")
            raise RuntimeError(f"Failed to unlock channel in DB: {e}")

    async def is_channel_locked(self, server_id: int, channel_id: int) -> bool:
        try:
            async with self.connection.execute(
                "SELECT 1 FROM locked_channels WHERE server_id = ? AND channel_id = ?",
                (str(server_id), str(channel_id))
            ) as cursor:
                result = await cursor.fetchone()
                is_locked = result is not None
                self.logger.info(f"Channel {channel_id} in server {server_id} is_locked: {is_locked}")
                return is_locked
        except Exception as e:
            self.logger.error(f"Failed to check if channel is locked: {e}")
            raise RuntimeError(f"Failed to check if channel is locked: {e}")

    # ---------------------------
    # Methods for Automod Exempt Roles
    # ---------------------------

    async def get_automod_exempt_roles(self, server_id: int) -> list:
        """
        Retrieves a list of role IDs that are exempt from automod.
        """
        try:
            async with self.connection.execute(
                "SELECT role_id FROM automod_exempt_roles WHERE server_id = ?",
                (str(server_id),)
            ) as cursor:
                roles = await cursor.fetchall()
                role_ids = [int(role[0]) for role in roles]
                self.logger.info(f"Fetched automod exempt roles for server {server_id}: {role_ids}")
                return role_ids
        except Exception as e:
            self.logger.error(f"Failed to get automod exempt roles: {e}")
            raise RuntimeError(f"Failed to get automod exempt roles: {e}")

    async def add_automod_exempt_role(self, server_id: int, role_id: int):
        """
        Adds a role to the list of automod exempt roles.
        """
        try:
            await self.connection.execute(
                "INSERT INTO automod_exempt_roles (server_id, role_id) VALUES (?, ?)",
                (str(server_id), str(role_id))
            )
            await self.connection.commit()
            self.logger.info(f"Added automod exempt role {role_id} to server {server_id}.")
        except aiosqlite.IntegrityError:
            self.logger.warning(f"Automod exempt role {role_id} already exists in server {server_id}.")
            raise RuntimeError(f"Automod exempt role {role_id} already exists.")
        except Exception as e:
            self.logger.error(f"Failed to add automod exempt role: {e}")
            raise RuntimeError(f"Failed to add automod exempt role: {e}")

    async def remove_automod_exempt_role(self, server_id: int, role_id: int):
        """
        Removes a role from the list of automod exempt roles.
        """
        try:
            await self.connection.execute(
                "DELETE FROM automod_exempt_roles WHERE server_id = ? AND role_id = ?",
                (str(server_id), str(role_id))
            )
            await self.connection.commit()
            self.logger.info(f"Removed automod exempt role {role_id} from server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to remove automod exempt role: {e}")
            raise RuntimeError(f"Failed to remove automod exempt role: {e}")

    # ---------------------------
    # Additional Utility Methods (Optional)
    # ---------------------------

    async def close(self):
        """
        Closes the database connection.
        """
        try:
            await self.connection.close()
            self.logger.info("Database connection closed.")
        except Exception as e:
            self.logger.error(f"Failed to close database connection: {e}")
            raise RuntimeError(f"Failed to close database connection: {e}")
