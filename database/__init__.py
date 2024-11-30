import aiosqlite

class DatabaseManager:
    def __init__(self, *, connection: aiosqlite.Connection) -> None:
        self.connection = connection

    # Existing methods for managing warns...

    async def add_warn(self, user_id: int, server_id: int, moderator_id: int, reason: str) -> int:
        try:
            async with self.connection.execute(
                "SELECT MAX(id) FROM warns WHERE user_id=? AND server_id=?",
                (user_id, server_id),
            ) as cursor:
                result = await cursor.fetchone()
                warn_id = (result[0] or 0) + 1
                await self.connection.execute(
                    "INSERT INTO warns(id, user_id, server_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    (warn_id, user_id, server_id, moderator_id, reason),
                )
                await self.connection.commit()
                return warn_id
        except Exception as e:
            raise RuntimeError(f"Failed to add warn: {e}")

    async def remove_warn(self, warn_id: int, user_id: int, server_id: int) -> bool:
        try:
            async with self.connection.execute(
                "DELETE FROM warns WHERE id=? AND user_id=? AND server_id=?",
                (warn_id, user_id, server_id),
            ) as cursor:
                await self.connection.commit()
                return cursor.rowcount > 0
        except Exception as e:
            raise RuntimeError(f"Failed to remove warn: {e}")

    async def get_all_warnings(self) -> list:
        try:
            async with self.connection.execute(
                "SELECT user_id, server_id, moderator_id, reason, strftime('%s', created_at), id FROM warns"
            ) as cursor:
                return await cursor.fetchall()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch all warnings: {e}")

    async def get_warnings(self, user_id: int, server_id: int) -> list:
        try:
            async with self.connection.execute(
                "SELECT user_id, server_id, moderator_id, reason, strftime('%s', created_at), id FROM warns WHERE user_id=? AND server_id=?",
                (user_id, server_id),
            ) as cursor:
                return await cursor.fetchall()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch warnings: {e}")

    async def clear_all_warnings(self, user_id: int, server_id: int) -> int:
        try:
            async with self.connection.execute(
                "DELETE FROM warns WHERE user_id=? AND server_id=?", (user_id, server_id)
            ) as cursor:
                await self.connection.commit()
                return cursor.rowcount
        except Exception as e:
            raise RuntimeError(f"Failed to clear all warnings: {e}")

    async def count_warnings(self, user_id: int, server_id: int) -> int:
        try:
            async with self.connection.execute(
                "SELECT COUNT(*) FROM warns WHERE user_id=? AND server_id=?",
                (user_id, server_id),
            ) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            raise RuntimeError(f"Failed to count warnings: {e}")

    async def remove_expired_warnings(self, expiration_timestamp: int) -> int:
        try:
            async with self.connection.execute(
                "DELETE FROM warns WHERE strftime('%s', created_at) < ?",
                (expiration_timestamp,),
            ) as cursor:
                await self.connection.commit()
                return cursor.rowcount
        except Exception as e:
            raise RuntimeError(f"Failed to remove expired warnings: {e}")

    # Methods for server settings...

    async def initialize_server_settings(self, server_id: int):
        try:
            async with self.connection.execute(
                "INSERT OR IGNORE INTO server_settings (server_id, automod_enabled, automod_logging_enabled, automod_log_channel_id) VALUES (?, 1, 0, NULL)",
                (str(server_id),)
            ):
                await self.connection.commit()
        except Exception as e:
            raise RuntimeError(f"Failed to initialize server settings: {e}")

    async def get_server_settings(self, server_id: int) -> dict:
        try:
            async with self.connection.execute(
                "SELECT automod_enabled, automod_logging_enabled, automod_log_channel_id FROM server_settings WHERE server_id=?",
                (str(server_id),)
            ) as cursor:
                result = await cursor.fetchone()
                if result:
                    return {
                        'automod_enabled': bool(result[0]),
                        'automod_logging_enabled': bool(result[1]),
                        'automod_log_channel_id': result[2]
                    }
                else:
                    # Initialize settings if they do not exist
                    await self.initialize_server_settings(server_id)
                    return {
                        'automod_enabled': True,
                        'automod_logging_enabled': False,
                        'automod_log_channel_id': None
                    }
        except Exception as e:
            raise RuntimeError(f"Failed to get server settings: {e}")

    async def update_server_setting(self, server_id: int, setting_name: str, value):
        try:
            query = f"UPDATE server_settings SET {setting_name} = ? WHERE server_id = ?"
            async with self.connection.execute(query, (value, str(server_id))):
                await self.connection.commit()
        except Exception as e:
            raise RuntimeError(f"Failed to update server setting '{setting_name}': {e}")

    async def toggle_server_setting(self, server_id: int, setting_name: str):
        try:
            current_settings = await self.get_server_settings(server_id)
            current_value = current_settings.get(setting_name)
            new_value = not current_value
            await self.update_server_setting(server_id, setting_name, int(new_value))
        except Exception as e:
            raise RuntimeError(f"Failed to toggle server setting '{setting_name}': {e}")

    # Methods for tryout groups...

    async def get_tryout_groups(self, server_id: int) -> list:
        try:
            async with self.connection.execute(
                "SELECT group_id, description, link, event_name FROM tryout_groups WHERE server_id = ?",
                (str(server_id),)
            ) as cursor:
                return await cursor.fetchall()
        except Exception as e:
            raise RuntimeError(f"Failed to get tryout groups: {e}")

    async def get_tryout_group(self, server_id: int, group_id: str):
        try:
            async with self.connection.execute(
                "SELECT group_id, description, link, event_name FROM tryout_groups WHERE server_id = ? AND group_id = ?",
                (str(server_id), group_id)
            ) as cursor:
                return await cursor.fetchone()
        except Exception as e:
            raise RuntimeError(f"Failed to get tryout group: {e}")

    async def add_tryout_group(self, server_id: int, group_id: str, description: str, link: str, event_name: str):
        try:
            async with self.connection.execute(
                "INSERT INTO tryout_groups (server_id, group_id, description, link, event_name) VALUES (?, ?, ?, ?, ?)",
                (str(server_id), group_id, description, link, event_name)
            ):
                await self.connection.commit()
        except Exception as e:
            raise RuntimeError(f"Failed to add tryout group: {e}")

    async def update_tryout_group(self, server_id: int, group_id: str, description: str, link: str, event_name: str):
        try:
            async with self.connection.execute(
                "UPDATE tryout_groups SET description = ?, link = ?, event_name = ? WHERE server_id = ? AND group_id = ?",
                (description, link, event_name, str(server_id), group_id)
            ):
                await self.connection.commit()
        except Exception as e:
            raise RuntimeError(f"Failed to update tryout group: {e}")

    async def delete_tryout_group(self, server_id: int, group_id: str):
        try:
            async with self.connection.execute(
                "DELETE FROM tryout_groups WHERE server_id = ? AND group_id = ?",
                (str(server_id), group_id)
            ):
                await self.connection.commit()
        except Exception as e:
            raise RuntimeError(f"Failed to delete tryout group: {e}")

    # Methods for tryout required roles...

    async def get_tryout_required_roles(self, server_id: int) -> list:
        try:
            async with self.connection.execute(
                "SELECT role_id FROM tryout_required_roles WHERE server_id = ?",
                (str(server_id),)
            ) as cursor:
                roles = await cursor.fetchall()
                return [int(role[0]) for role in roles]
        except Exception as e:
            raise RuntimeError(f"Failed to get tryout required roles: {e}")

    async def add_tryout_required_role(self, server_id: int, role_id: int):
        try:
            async with self.connection.execute(
                "INSERT INTO tryout_required_roles (server_id, role_id) VALUES (?, ?)",
                (str(server_id), str(role_id))
            ):
                await self.connection.commit()
        except Exception as e:
            raise RuntimeError(f"Failed to add required role: {e}")

    async def remove_tryout_required_role(self, server_id: int, role_id: int):
        try:
            async with self.connection.execute(
                "DELETE FROM tryout_required_roles WHERE server_id = ? AND role_id = ?",
                (str(server_id), str(role_id))
            ):
                await self.connection.commit()
        except Exception as e:
            raise RuntimeError(f"Failed to remove required role: {e}")

    # Methods for tryout settings...

    async def get_tryout_channel_id(self, server_id: int) -> int:
        try:
            async with self.connection.execute(
                "SELECT tryout_channel_id FROM tryout_settings WHERE server_id = ?",
                (str(server_id),)
            ) as cursor:
                result = await cursor.fetchone()
                return int(result[0]) if result and result[0] else None
        except Exception as e:
            raise RuntimeError(f"Failed to get tryout channel ID: {e}")

    async def set_tryout_channel_id(self, server_id: int, channel_id: int):
        try:
            async with self.connection.execute(
                "INSERT OR REPLACE INTO tryout_settings (server_id, tryout_channel_id) VALUES (?, ?)",
                (str(server_id), str(channel_id))
            ):
                await self.connection.commit()
        except Exception as e:
            raise RuntimeError(f"Failed to set tryout channel: {e}")