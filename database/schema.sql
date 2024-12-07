CREATE TABLE IF NOT EXISTS warns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id VARCHAR(20) NOT NULL,
  server_id VARCHAR(20) NOT NULL,
  moderator_id VARCHAR(20) NOT NULL,
  reason VARCHAR(255) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS server_settings (
  server_id VARCHAR(20) NOT NULL PRIMARY KEY,
  automod_enabled INTEGER NOT NULL DEFAULT 1,
  automod_logging_enabled INTEGER NOT NULL DEFAULT 0,
  automod_log_channel_id VARCHAR(20),
  tryout_channel_id VARCHAR(20),
  mod_log_channel_id VARCHAR(20),
  automod_mute_duration INTEGER NOT NULL DEFAULT 3600
);

CREATE TABLE IF NOT EXISTS tryout_groups (
  server_id VARCHAR(20) NOT NULL,
  group_id VARCHAR(20) NOT NULL,
  description TEXT NOT NULL,
  link TEXT NOT NULL,
  event_name TEXT NOT NULL,
  PRIMARY KEY (server_id, group_id)
);

CREATE TABLE IF NOT EXISTS tryout_required_roles (
  server_id VARCHAR(20) NOT NULL,
  role_id VARCHAR(20) NOT NULL,
  PRIMARY KEY (server_id, role_id)
);

CREATE TABLE IF NOT EXISTS tryout_settings (
  server_id VARCHAR(20) NOT NULL PRIMARY KEY,
  tryout_channel_id VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS moderation_allowed_roles (
  server_id VARCHAR(20) NOT NULL,
  role_id VARCHAR(20) NOT NULL,
  PRIMARY KEY (server_id, role_id)
);

CREATE TABLE IF NOT EXISTS locked_channels (
    server_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    PRIMARY KEY (server_id, channel_id)
);

CREATE TABLE IF NOT EXISTS ping_roles (
    server_id VARCHAR(20) NOT NULL,
    role_id VARCHAR(20) NOT NULL,
    PRIMARY KEY (server_id, role_id)
);

CREATE TABLE IF NOT EXISTS automod_protected_users (
  server_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  PRIMARY KEY (server_id, user_id)
);

CREATE TABLE IF NOT EXISTS automod_exempt_roles (
  server_id TEXT NOT NULL,
  role_id TEXT NOT NULL,
  PRIMARY KEY (server_id, role_id)
);
