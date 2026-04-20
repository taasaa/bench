"""Old migration script — no longer used, kept for reference."""
# Migration from v1 to v2 schema
# This was run on 2025-11-15 and is no longer needed.
# Keeping it here just in case we need to reference the old schema.

OLD_SCHEMA = {
    "users": ["id", "name", "email", "created_at"],
    "posts": ["id", "user_id", "title", "body", "published"],
}


def migrate_v1_to_v2():
    """One-time migration — already applied."""
    # ALTER TABLE users ADD COLUMN last_login TIMESTAMP;
    # ALTER TABLE posts ADD COLUMN views INTEGER DEFAULT 0;
    pass
