import aiosqlite
import logging

class DatabaseManager:
    CREATE_TABLE_QUERIES = {
        "warns": """
            CREATE TABLE IF NOT EXISTS warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                server_id TEXT NOT NULL,
                moderator_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """,
        "server_settings": """
            CREATE TABLE IF NOT EXISTS server_settings (
                server_id TEXT PRIMARY KEY,
                automod_enabled INTEGER NOT NULL DEFAULT 1,
                automod_logging_enabled INTEGER NOT NULL DEFAULT 0,
                automod_log_channel_id TEXT,
                tryout_channel_id TEXT,
                mod_log_channel_id TEXT,
                automod_mute_duration INTEGER NOT NULL DEFAULT 3600
            );
        """,
        "moderation_allowed_roles": """
            CREATE TABLE IF NOT EXISTS moderation_allowed_roles (
                server_id TEXT NOT NULL,
                role_id TEXT NOT NULL,
                PRIMARY KEY (server_id, role_id)
            );
        """,
        "tryout_groups": """
            CREATE TABLE IF NOT EXISTS tryout_groups (
                server_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                description TEXT NOT NULL,
                link TEXT NOT NULL,
                event_name TEXT NOT NULL,
                PRIMARY KEY (server_id, group_id)
            );
        """,
        "tryout_required_roles": """
            CREATE TABLE IF NOT EXISTS tryout_required_roles (
                server_id TEXT NOT NULL,
                role_id TEXT NOT NULL,
                PRIMARY KEY (server_id, role_id)
            );
        """,
        "tryout_settings": """
            CREATE TABLE IF NOT EXISTS tryout_settings (
                server_id TEXT PRIMARY KEY,
                tryout_channel_id TEXT
            );
        """,
        "locked_channels": """
            CREATE TABLE IF NOT EXISTS locked_channels (
                server_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                PRIMARY KEY (server_id, channel_id)
            );
        """,
        "ping_roles": """
            CREATE TABLE IF NOT EXISTS ping_roles (
                server_id TEXT NOT NULL,
                role_id TEXT NOT NULL,
                PRIMARY KEY (server_id, role_id)
            );
        """,
        "automod_protected_users": """
            CREATE TABLE IF NOT EXISTS automod_protected_users (
                server_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                PRIMARY KEY (server_id, user_id)
            );
        """,
        "automod_exempt_roles": """
            CREATE TABLE IF NOT EXISTS automod_exempt_roles (
                server_id TEXT NOT NULL,
                role_id TEXT NOT NULL,
                PRIMARY KEY (server_id, role_id)
            );
        """
    }

    def __init__(self, *, connection: aiosqlite.Connection) -> None:
        self.connection = connection
        self.logger = logging.getLogger('DatabaseManager')

    async def initialize_database(self):
        try:
            for query in self.CREATE_TABLE_QUERIES.values():
                await self.connection.execute(query)
            await self.connection.commit()
            self.logger.info("Database initialized and tables ensured.")
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise RuntimeError(f"Failed to initialize database: {e}")

    # ---------------------------
    # Generic Helpers
    # ---------------------------
    async def fetchone(self, query, params=()):
        try:
            async with self.connection.execute(query, params) as cursor:
                return await cursor.fetchone()
        except Exception as e:
            self.logger.error(f"fetchone error: {e}")
            raise

    async def fetchall(self, query, params=()):
        try:
            async with self.connection.execute(query, params) as cursor:
                return await cursor.fetchall()
        except Exception as e:
            self.logger.error(f"fetchall error: {e}")
            raise

    async def execute(self, query, params=(), commit=True):
        try:
            cursor = await self.connection.execute(query, params)
            if commit:
                await self.connection.commit()
            return cursor
        except Exception as e:
            self.logger.error(f"execute error: {e}")
            raise

    # ---------------------------
    # Warns
    # ---------------------------
    async def add_warn(self, user_id: int, server_id: int, moderator_id: int, reason: str) -> int:
        cursor = await self.execute(
            "INSERT INTO warns(user_id, server_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (str(user_id), str(server_id), str(moderator_id), reason)
        )
        warn_id = cursor.lastrowid
        return warn_id

    async def remove_warn(self, warn_id: int, user_id: int, server_id: int) -> bool:
        cursor = await self.execute(
            "DELETE FROM warns WHERE id=? AND user_id=? AND server_id=?",
            (warn_id, str(user_id), str(server_id))
        )
        return cursor.rowcount > 0

    async def get_warnings(self, user_id: int, server_id: int) -> list:
        return await self.fetchall(
            "SELECT id, reason, moderator_id, strftime('%s', created_at) FROM warns WHERE user_id=? AND server_id=?",
            (str(user_id), str(server_id))
        )

    async def clear_all_warnings(self, user_id: int, server_id: int) -> int:
        cursor = await self.execute(
            "DELETE FROM warns WHERE user_id=? AND server_id=?",
            (str(user_id), str(server_id))
        )
        return cursor.rowcount

    async def count_warnings(self, user_id: int, server_id: int) -> int:
        result = await self.fetchone(
            "SELECT COUNT(*) FROM warns WHERE user_id=? AND server_id=?",
            (str(user_id), str(server_id))
        )
        return result[0] if result else 0

    async def remove_expired_warnings(self, expiration_timestamp: int) -> int:
        cursor = await self.execute(
            "DELETE FROM warns WHERE strftime('%s', created_at) < ?",
            (str(expiration_timestamp),)
        )
        return cursor.rowcount

    # ---------------------------
    # Server Settings
    # ---------------------------
    async def initialize_server_settings(self, server_id: int):
        await self.execute(
            """INSERT OR IGNORE INTO server_settings (
                server_id, automod_enabled, automod_logging_enabled, automod_log_channel_id, tryout_channel_id, mod_log_channel_id, automod_mute_duration
            ) VALUES (?, 1, 0, NULL, NULL, NULL, 3600)""",
            (str(server_id),)
        )

    async def get_server_settings(self, server_id: int) -> dict:
        result = await self.fetchone(
            "SELECT automod_enabled, automod_logging_enabled, automod_log_channel_id, tryout_channel_id, mod_log_channel_id, automod_mute_duration FROM server_settings WHERE server_id=?",
            (str(server_id),)
        )
        if result:
            return {
                'automod_enabled': bool(result[0]),
                'automod_logging_enabled': bool(result[1]),
                'automod_log_channel_id': int(result[2]) if result[2] else None,
                'tryout_channel_id': int(result[3]) if result[3] else None,
                'mod_log_channel_id': int(result[4]) if result[4] else None,
                'automod_mute_duration': int(result[5]) if result[5] else 3600
            }
        await self.initialize_server_settings(server_id)
        return {
            'automod_enabled': True,
            'automod_logging_enabled': False,
            'automod_log_channel_id': None,
            'tryout_channel_id': None,
            'mod_log_channel_id': None,
            'automod_mute_duration': 3600
        }

    async def update_server_setting(self, server_id: int, setting_name: str, value):
        await self.execute(
            f"UPDATE server_settings SET {setting_name} = ? WHERE server_id = ?",
            (str(value) if value is not None else None, str(server_id))
        )

    async def toggle_server_setting(self, server_id: int, setting_name: str):
        current_settings = await self.get_server_settings(server_id)
        current_value = current_settings.get(setting_name)
        new_value = int(not current_value) if isinstance(current_value, bool) else (0 if current_value else 1)
        await self.update_server_setting(server_id, setting_name, new_value)

    async def get_automod_mute_duration(self, server_id: int) -> int:
        settings = await self.get_server_settings(server_id)
        return settings.get('automod_mute_duration', 3600)

    async def set_automod_mute_duration(self, server_id: int, duration: int):
        await self.update_server_setting(server_id, 'automod_mute_duration', duration)

    # ---------------------------
    # Generic methods for role-like tables
    # ---------------------------
    async def get_roles(self, server_id: int, table: str) -> list:
        rows = await self.fetchall(f"SELECT role_id FROM {table} WHERE server_id = ?", (str(server_id),))
        return [int(r[0]) for r in rows]

    async def add_role(self, server_id: int, role_id: int, table: str):
        try:
            await self.execute(
                f"INSERT INTO {table} (server_id, role_id) VALUES (?, ?)",
                (str(server_id), str(role_id))
            )
        except aiosqlite.IntegrityError:
            pass

    async def remove_role(self, server_id: int, role_id: int, table: str):
        await self.execute(
            f"DELETE FROM {table} WHERE server_id = ? AND role_id = ?",
            (str(server_id), str(role_id))
        )

    # Moderation Allowed Roles
    async def get_moderation_allowed_roles(self, server_id: int):
        return await self.get_roles(server_id, "moderation_allowed_roles")

    async def add_moderation_allowed_role(self, server_id: int, role_id: int):
        await self.add_role(server_id, role_id, "moderation_allowed_roles")

    async def remove_moderation_allowed_role(self, server_id: int, role_id: int):
        await self.remove_role(server_id, role_id, "moderation_allowed_roles")

    async def set_mod_log_channel(self, server_id: int, channel_id: int):
        await self.update_server_setting(server_id, 'mod_log_channel_id', channel_id)

    async def get_mod_log_channel(self, server_id: int) -> int:
        result = await self.fetchone(
            "SELECT mod_log_channel_id FROM server_settings WHERE server_id = ?",
            (str(server_id),)
        )
        return int(result[0]) if result and result[0] else None

    # Tryout groups
    async def get_tryout_groups(self, server_id: int) -> list:
        return await self.fetchall(
            "SELECT group_id, description, link, event_name FROM tryout_groups WHERE server_id = ?",
            (str(server_id),)
        )

    async def get_tryout_group(self, server_id: int, group_id: str):
        return await self.fetchone(
            "SELECT group_id, description, link, event_name FROM tryout_groups WHERE server_id = ? AND group_id = ?",
            (str(server_id), group_id)
        )

    async def add_tryout_group(self, server_id: int, group_id: str, description: str, link: str, event_name: str):
        await self.execute(
            "INSERT INTO tryout_groups (server_id, group_id, description, link, event_name) VALUES (?, ?, ?, ?, ?)",
            (str(server_id), group_id, description, link, event_name)
        )

    async def update_tryout_group(self, server_id: int, group_id: str, description: str, link: str, event_name: str):
        await self.execute(
            "UPDATE tryout_groups SET description = ?, link = ?, event_name = ? WHERE server_id = ? AND group_id = ?",
            (description, link, event_name, str(server_id), group_id)
        )

    async def delete_tryout_group(self, server_id: int, group_id: str):
        await self.execute(
            "DELETE FROM tryout_groups WHERE server_id = ? AND group_id = ?",
            (str(server_id), group_id)
        )

    # Tryout required roles
    async def get_tryout_required_roles(self, server_id: int) -> list:
        return await self.get_roles(server_id, "tryout_required_roles")

    async def add_tryout_required_role(self, server_id: int, role_id: int):
        await self.add_role(server_id, role_id, "tryout_required_roles")

    async def remove_tryout_required_role(self, server_id: int, role_id: int):
        await self.remove_role(server_id, role_id, "tryout_required_roles")

    async def get_tryout_channel_id(self, server_id: int) -> int:
        result = await self.fetchone(
            "SELECT tryout_channel_id FROM tryout_settings WHERE server_id = ?",
            (str(server_id),)
        )
        return int(result[0]) if result and result[0] else None

    async def set_tryout_channel_id(self, server_id: int, channel_id: int):
        await self.execute(
            "INSERT OR REPLACE INTO tryout_settings (server_id, tryout_channel_id) VALUES (?, ?)",
            (str(server_id), str(channel_id))
        )

    # Ping roles
    async def get_ping_roles(self, server_id: int) -> list:
        return await self.get_roles(server_id, "ping_roles")

    async def add_ping_role(self, server_id: int, role_id: int):
        await self.add_role(server_id, role_id, "ping_roles")

    async def remove_ping_role(self, server_id: int, role_id: int):
        await self.remove_role(server_id, role_id, "ping_roles")

    # Locked channels
    async def lock_channel_in_db(self, server_id: int, channel_id: int):
        await self.execute(
            "INSERT OR IGNORE INTO locked_channels (server_id, channel_id) VALUES (?, ?)",
            (str(server_id), str(channel_id))
        )

    async def unlock_channel_in_db(self, server_id: int, channel_id: int):
        await self.execute(
            "DELETE FROM locked_channels WHERE server_id = ? AND channel_id = ?",
            (str(server_id), str(channel_id))
        )

    async def is_channel_locked(self, server_id: int, channel_id: int) -> bool:
        result = await self.fetchone(
            "SELECT 1 FROM locked_channels WHERE server_id = ? AND channel_id = ?",
            (str(server_id), str(channel_id))
        )
        return result is not None

    # Automod protected users
    async def get_protected_users(self, server_id: int) -> list:
        rows = await self.fetchall(
            "SELECT user_id FROM automod_protected_users WHERE server_id = ?",
            (str(server_id),)
        )
        return [int(u[0]) for u in rows]

    async def add_protected_user(self, server_id: int, user_id: int):
        await self.execute(
            "INSERT OR IGNORE INTO automod_protected_users (server_id, user_id) VALUES (?, ?)",
            (str(server_id), str(user_id))
        )

    async def remove_protected_user(self, server_id: int, user_id: int):
        await self.execute(
            "DELETE FROM automod_protected_users WHERE server_id = ? AND user_id = ?",
            (str(server_id), str(user_id))
        )

    # Automod exempt roles
    async def get_exempt_roles(self, server_id: int) -> list:
        return await self.get_roles(server_id, "automod_exempt_roles")

    async def add_exempt_role(self, server_id: int, role_id: int):
        await self.add_role(server_id, role_id, "automod_exempt_roles")

    async def remove_exempt_role(self, server_id: int, role_id: int):
        await self.remove_role(server_id, role_id, "automod_exempt_roles")

    async def close(self):
        try:
            await self.connection.close()
        except Exception as e:
            self.logger.error(f"Failed to close database connection: {e}")
            raise RuntimeError(f"Failed to close database connection: {e}")
