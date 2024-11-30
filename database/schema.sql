-- Existing Tables

CREATE TABLE IF NOT EXISTS `warns` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `user_id` VARCHAR(20) NOT NULL,
  `server_id` VARCHAR(20) NOT NULL,
  `moderator_id` VARCHAR(20) NOT NULL,
  `reason` VARCHAR(255) NOT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `server_settings` (
  `server_id` VARCHAR(20) NOT NULL PRIMARY KEY,
  `automod_enabled` INTEGER NOT NULL DEFAULT 1,
  `automod_logging_enabled` INTEGER NOT NULL DEFAULT 0,
  `automod_log_channel_id` VARCHAR(20),
  `tryout_channel_id` VARCHAR(20),
  `mod_log_channel_id` VARCHAR(20) -- New Column for Moderation Log Channel
);

CREATE TABLE IF NOT EXISTS `tryout_groups` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `server_id` VARCHAR(20) NOT NULL,
  `group_id` VARCHAR(20) NOT NULL,
  `description` TEXT NOT NULL,
  `link` TEXT NOT NULL,
  `event_name` TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS `tryout_required_roles` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `server_id` VARCHAR(20) NOT NULL,
  `role_id` VARCHAR(20) NOT NULL
);

CREATE TABLE IF NOT EXISTS `tryout_settings` (
  `server_id` VARCHAR(20) NOT NULL PRIMARY KEY,
  `tryout_channel_id` VARCHAR(20)
);

-- New Table for Moderation Allowed Roles

CREATE TABLE IF NOT EXISTS `moderation_allowed_roles` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `server_id` VARCHAR(20) NOT NULL,
  `role_id` VARCHAR(20) NOT NULL
);
