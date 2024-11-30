CREATE TABLE IF NOT EXISTS `warns` (
  `id` int(11) NOT NULL,
  `user_id` varchar(20) NOT NULL,
  `server_id` varchar(20) NOT NULL,
  `moderator_id` varchar(20) NOT NULL,
  `reason` varchar(255) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `server_settings` (
  `server_id` varchar(20) NOT NULL PRIMARY KEY,
  `automod_enabled` INTEGER NOT NULL DEFAULT 1,
  `automod_logging_enabled` INTEGER NOT NULL DEFAULT 0,
  `automod_log_channel_id` varchar(20)
);
