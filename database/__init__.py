import aiosqlite

class DatabaseManager:
    def __init__(self, *, connection: aiosqlite.Connection) -> None:
        self.connection = connection

    async def add_warn(self, user_id: int, server_id: int, moderator_id: int, reason: str) -> int:
        """
        Add a warning to the database.

        :param user_id: The ID of the user receiving the warning.
        :param server_id: The ID of the server where the warning occurred.
        :param moderator_id: The ID of the moderator issuing the warning.
        :param reason: The reason for the warning.
        :return: The ID of the newly added warning.
        """
        try:
            async with self.connection.execute(
                "SELECT MAX(id) FROM warns WHERE user_id=? AND server_id=?",
                (user_id, server_id),
            ) as cursor:
                result = await cursor.fetchone()
                warn_id = (result[0] or 0) + 1  # Increment the last warn ID for the user
                await self.connection.execute(
                    "INSERT INTO warns(id, user_id, server_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    (warn_id, user_id, server_id, moderator_id, reason),
                )
                await self.connection.commit()
                return warn_id
        except Exception as e:
            raise RuntimeError(f"Failed to add warn: {e}")

    async def remove_warn(self, warn_id: int, user_id: int, server_id: int) -> bool:
        """
        Remove a specific warning from the database.

        :param warn_id: The ID of the warning to remove.
        :param user_id: The ID of the user associated with the warning.
        :param server_id: The ID of the server where the warning occurred.
        :return: True if a warning was removed, False otherwise.
        """
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
        """
        Fetch all warnings from the database.

        :return: A list of all warnings.
        """
        try:
            async with self.connection.execute(
                "SELECT user_id, server_id, moderator_id, reason, strftime('%s', created_at), id FROM warns"
            ) as cursor:
                return await cursor.fetchall()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch all warnings: {e}")

    async def get_warnings(self, user_id: int, server_id: int) -> list:
        """
        Get all warnings for a user in a specific server.

        :param user_id: The ID of the user.
        :param server_id: The ID of the server.
        :return: A list of warnings for the user.
        """
        try:
            async with self.connection.execute(
                "SELECT user_id, server_id, moderator_id, reason, strftime('%s', created_at), id FROM warns WHERE user_id=? AND server_id=?",
                (user_id, server_id),
            ) as cursor:
                return await cursor.fetchall()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch warnings: {e}")

    async def clear_all_warnings(self, user_id: int, server_id: int) -> int:
        """
        Clear all warnings for a specific user in a server.

        :param user_id: The ID of the user.
        :param server_id: The ID of the server.
        :return: The number of warnings removed.
        """
        try:
            async with self.connection.execute(
                "DELETE FROM warns WHERE user_id=? AND server_id=?", (user_id, server_id)
            ) as cursor:
                await self.connection.commit()
                return cursor.rowcount  # Return the number of warnings removed
        except Exception as e:
            raise RuntimeError(f"Failed to clear all warnings: {e}")

    async def count_warnings(self, user_id: int, server_id: int) -> int:
        """
        Count the number of warnings for a user in a server.

        :param user_id: The ID of the user.
        :param server_id: The ID of the server.
        :return: The number of warnings.
        """
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
        """
        Remove all warnings older than expiration_timestamp.

        :param expiration_timestamp: Timestamp; warnings older than this will be removed.
        :return: Number of warnings removed.
        """
        try:
            async with self.connection.execute(
                "DELETE FROM warns WHERE strftime('%s', created_at) < ?",
                (expiration_timestamp,),
            ) as cursor:
                await self.connection.commit()
                return cursor.rowcount  # Return the number of warnings removed
        except Exception as e:
            raise RuntimeError(f"Failed to remove expired warnings: {e}")

    # New methods for server settings

    async def initialize_server_settings(self, server_id: int):
        """
        Initialize default settings for a server if they do not exist.
        """
        try:
            async with self.connection.execute(
                "INSERT OR IGNORE INTO server_settings (server_id, automod_enabled, automod_logging_enabled, automod_log_channel_id) VALUES (?, 1, 0, NULL)",
                (str(server_id),)
            ):
                await self.connection.commit()
        except Exception as e:
            raise RuntimeError(f"Failed to initialize server settings: {e}")

    async def get_server_settings(self, server_id: int) -> dict:
        """
        Retrieve server settings from the database.
        """
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
        """
        Update a specific server setting.
        """
        try:
            query = f"UPDATE server_settings SET {setting_name} = ? WHERE server_id = ?"
            async with self.connection.execute(query, (value, str(server_id))):
                await self.connection.commit()
        except Exception as e:
            raise RuntimeError(f"Failed to update server setting '{setting_name}': {e}")

    async def toggle_server_setting(self, server_id: int, setting_name: str):
        """
        Toggle a boolean server setting.
        """
        try:
            current_settings = await self.get_server_settings(server_id)
            current_value = current_settings.get(setting_name)
            new_value = not current_value
            await self.update_server_setting(server_id, setting_name, int(new_value))
        except Exception as e:
            raise RuntimeError(f"Failed to toggle server setting '{setting_name}': {e}")
