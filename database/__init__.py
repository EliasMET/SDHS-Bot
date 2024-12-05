import aiosqlite
import logging

class DatabaseManager:
    def __init__(self, *, connection: aiosqlite.Connection) -> None:
        self.connection = connection
        self.logger = logging.getLogger('DatabaseManager')

    async def initialize_database(self):
        """
        Initializes the database by creating necessary tables if they do not exist.
        """
        try:
            await self.connection.execute("""
                CREATE TABLE IF NOT EXISTS warns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    server_id TEXT NOT NULL,
                    moderator_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
                    server_id TEXT PRIMARY KEY,
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

            await self.connection.commit()
            self.logger.info("Database initialized and tables ensured.")
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise RuntimeError(f"Failed to initialize database: {e}")

    # ---------------------------
    # Methods for Managing Warns
    # ---------------------------

    async def add_warn(self, user_id: int, server_id: int, moderator_id: int, reason: str) -> int:
        """
        Adds a warning to a user.

        :param user_id: ID of the user being warned.
        :param server_id: ID of the server.
        :param moderator_id: ID of the moderator issuing the warning.
        :param reason: Reason for the warning.
        :return: The ID of the newly created warning.
        """
        try:
            cursor = await self.connection.execute(
                "INSERT INTO warns(user_id, server_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (str(user_id), str(server_id), str(moderator_id), reason),
            )
            await self.connection.commit()
            warn_id = cursor.lastrowid
            self.logger.info(f"Added warn ID {warn_id} for user {user_id} in server {server_id}.")
            return warn_id
        except Exception as e:
            self.logger.error(f"Failed to add warn: {e}")
            raise RuntimeError(f"Failed to add warn: {e}")

    async def remove_warn(self, warn_id: int, user_id: int, server_id: int) -> bool:
        """
        Removes a specific warning.

        :param warn_id: ID of the warning to remove.
        :param user_id: ID of the user.
        :param server_id: ID of the server.
        :return: True if a warning was removed, False otherwise.
        """
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
        """
        Retrieves all warnings across all servers.

        :return: A list of all warnings.
        """
        try:
            async with self.connection.execute(
                "SELECT id, user_id, server_id, moderator_id, reason, strftime('%s', created_at) FROM warns"
            ) as cursor:
                warnings = await cursor.fetchall()
                self.logger.info(f"Fetched all warnings: {len(warnings)} records found.")
                return warnings
        except Exception as e:
            self.logger.error(f"Failed to fetch all warnings: {e}")
            raise RuntimeError(f"Failed to fetch all warnings: {e}")

    async def get_warnings(self, user_id: int, server_id: int) -> list:
        """
        Retrieves all warnings for a specific user in a server.

        :param user_id: ID of the user.
        :param server_id: ID of the server.
        :return: A list of warnings.
        """
        try:
            async with self.connection.execute(
                "SELECT id, reason, moderator_id, strftime('%s', created_at) FROM warns WHERE user_id=? AND server_id=?",
                (str(user_id), str(server_id)),
            ) as cursor:
                warnings = await cursor.fetchall()
                self.logger.info(f"Fetched {len(warnings)} warnings for user {user_id} in server {server_id}.")
                return warnings
        except Exception as e:
            self.logger.error(f"Failed to fetch warnings: {e}")
            raise RuntimeError(f"Failed to fetch warnings: {e}")

    async def clear_all_warnings(self, user_id: int, server_id: int) -> int:
        """
        Clears all warnings for a specific user in a server.

        :param user_id: ID of the user.
        :param server_id: ID of the server.
        :return: Number of warnings removed.
        """
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
        """
        Counts the number of warnings a user has in a server.

        :param user_id: ID of the user.
        :param server_id: ID of the server.
        :return: Number of warnings.
        """
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
        """
        Removes warnings older than a certain timestamp.

        :param expiration_timestamp: Unix timestamp; warnings older than this will be removed.
        :return: Number of warnings removed.
        """
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
        """
        Initializes server settings with default values.

        :param server_id: ID of the server.
        """
        try:
            await self.connection.execute(
                "INSERT OR IGNORE INTO server_settings (server_id, automod_enabled, automod_logging_enabled, automod_log_channel_id, tryout_channel_id, mod_log_channel_id) VALUES (?, 1, 0, NULL, NULL, NULL)",
                (str(server_id),)
            )
            await self.connection.commit()
            self.logger.info(f"Initialized server settings for server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to initialize server settings: {e}")
            raise RuntimeError(f"Failed to initialize server settings: {e}")

    async def get_server_settings(self, server_id: int) -> dict:
        """
        Retrieves server settings.

        :param server_id: ID of the server.
        :return: A dictionary of server settings.
        """
        try:
            async with self.connection.execute(
                "SELECT automod_enabled, automod_logging_enabled, automod_log_channel_id, tryout_channel_id, mod_log_channel_id FROM server_settings WHERE server_id=?",
                (str(server_id),)
            ) as cursor:
                result = await cursor.fetchone()
                if result:
                    settings = {
                        'automod_enabled': bool(result[0]),
                        'automod_logging_enabled': bool(result[1]),
                        'automod_log_channel_id': int(result[2]) if result[2] else None,
                        'tryout_channel_id': int(result[3]) if result[3] else None,
                        'mod_log_channel_id': int(result[4]) if result[4] else None
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
                        'mod_log_channel_id': None
                    }
                    self.logger.info(f"Initialized and fetched default server settings for server {server_id}: {default_settings}")
                    return default_settings
        except Exception as e:
            self.logger.error(f"Failed to get server settings: {e}")
            raise RuntimeError(f"Failed to get server settings: {e}")

    async def update_server_setting(self, server_id: int, setting_name: str, value):
        """
        Updates a specific server setting.

        :param server_id: ID of the server.
        :param setting_name: Name of the setting to update.
        :param value: New value for the setting.
        """
        try:
            query = f"UPDATE server_settings SET {setting_name} = ? WHERE server_id = ?"
            await self.connection.execute(query, (str(value) if value is not None else None, str(server_id)))
            await self.connection.commit()
            self.logger.info(f"Updated server setting '{setting_name}' for server {server_id} to '{value}'.")
        except Exception as e:
            self.logger.error(f"Failed to update server setting '{setting_name}': {e}")
            raise RuntimeError(f"Failed to update server setting '{setting_name}': {e}")

    async def toggle_server_setting(self, server_id: int, setting_name: str):
        """
        Toggles a boolean server setting.

        :param server_id: ID of the server.
        :param setting_name: Name of the setting to toggle.
        """
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
    # Methods for Moderation Allowed Roles
    # ---------------------------

    async def get_moderation_allowed_roles(self, server_id: int) -> list:
        """
        Retrieves a list of role IDs allowed to use moderation commands.

        :param server_id: ID of the server.
        :return: List of role IDs.
        """
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
        """
        Adds a role to the list of allowed roles for moderation commands.

        :param server_id: ID of the server.
        :param role_id: ID of the role to add.
        """
        try:
            await self.connection.execute(
                "INSERT INTO moderation_allowed_roles (server_id, role_id) VALUES (?, ?)",
                (str(server_id), str(role_id))
            )
            await self.connection.commit()
            self.logger.info(f"Added role {role_id} to moderation allowed roles in server {server_id}.")
        except aiosqlite.IntegrityError:
            # Role already exists; ignore or handle as needed
            self.logger.warning(f"Role {role_id} already exists in moderation allowed roles for server {server_id}.")
        except Exception as e:
            self.logger.error(f"Failed to add moderation allowed role: {e}")
            raise RuntimeError(f"Failed to add moderation allowed role: {e}")

    async def remove_moderation_allowed_role(self, server_id: int, role_id: int):
        """
        Removes a role from the list of allowed roles for moderation commands.

        :param server_id: ID of the server.
        :param role_id: ID of the role to remove.
        """
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
        """
        Sets the moderation log channel for a server.

        :param server_id: ID of the server.
        :param channel_id: ID of the channel to set as the moderation log channel.
        """
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
        """
        Retrieves the moderation log channel ID for a server.

        :param server_id: ID of the server.
        :return: ID of the moderation log channel, or None if not set.
        """
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
        """
        Retrieves all tryout groups for a server.

        :param server_id: ID of the server.
        :return: List of tryout groups.
        """
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
        """
        Retrieves a specific tryout group.

        :param server_id: ID of the server.
        :param group_id: ID of the group.
        :return: Tryout group details or None if not found.
        """
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
        """
        Adds a new tryout group.

        :param server_id: ID of the server.
        :param group_id: ID of the group.
        :param description: Description of the group.
        :param link: Link associated with the group.
        :param event_name: Event name for the group.
        """
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
        """
        Updates an existing tryout group.

        :param server_id: ID of the server.
        :param group_id: ID of the group.
        :param description: New description.
        :param link: New link.
        :param event_name: New event name.
        """
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
        """
        Deletes a tryout group.

        :param server_id: ID of the server.
        :param group_id: ID of the group.
        """
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
        """
        Retrieves all roles required for tryouts in a server.

        :param server_id: ID of the server.
        :return: List of role IDs.
        """
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
        """
        Adds a role to the list of required roles for tryouts.

        :param server_id: ID of the server.
        :param role_id: ID of the role to add.
        """
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
        """
        Removes a role from the list of required roles for tryouts.

        :param server_id: ID of the server.
        :param role_id: ID of the role to remove.
        """
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
        """
        Retrieves the tryout channel ID for a server.

        :param server_id: ID of the server.
        :return: ID of the tryout channel or None if not set.
        """
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
        """
        Sets the tryout channel for a server.

        :param server_id: ID of the server.
        :param channel_id: ID of the channel to set as tryout channel.
        """
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
        """
        Retrieves all ping roles for a server.

        :param server_id: ID of the server.
        :return: List of role IDs.
        """
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
        """
        Adds a role to the list of ping roles for a server.

        :param server_id: ID of the server.
        :param role_id: ID of the role to add.
        """
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
        """
        Removes a role from the list of ping roles for a server.

        :param server_id: ID of the server.
        :param role_id: ID of the role to remove.
        """
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
        """
        Records a locked channel in the database.

        :param server_id: ID of the server.
        :param channel_id: ID of the channel to lock.
        """
        try:
            await self.connection.execute(
                "INSERT INTO locked_channels (server_id, channel_id) VALUES (?, ?)",
                (str(server_id), str(channel_id))
            )
            await self.connection.commit()
            self.logger.info(f"Locked channel {channel_id} in server {server_id} and recorded in DB.")
        except aiosqlite.IntegrityError:
            # Channel is already locked; ignore or log as needed
            self.logger.warning(f"Channel {channel_id} in server {server_id} is already locked.")
        except Exception as e:
            self.logger.error(f"Failed to lock channel in DB: {e}")
            raise RuntimeError(f"Failed to lock channel in DB: {e}")

    async def unlock_channel_in_db(self, server_id: int, channel_id: int):
        """
        Removes a locked channel from the database.

        :param server_id: ID of the server.
        :param channel_id: ID of the channel to unlock.
        """
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
        """
        Checks if a channel is locked.

        :param server_id: ID of the server.
        :param channel_id: ID of the channel.
        :return: True if the channel is locked, False otherwise.
        """
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
