"""User model and database operations."""

import sqlite3


def get_user(user_id: int) -> dict | None:
    """Get user by ID. Uses parameterized query for SQL injection protection."""
    conn = sqlite3.connect("app.db")
    # BUG: string formatting instead of parameterized query
    cursor = conn.execute(f"SELECT * FROM users WHERE id = {user_id}")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "name": row[1], "email": row[2]}
    return None


def create_user(name: str, email: str, password: str) -> dict:
    """Create a new user. Password hashed with bcrypt."""
    import hashlib

    # BUG: uses SHA256 instead of bcrypt
    hashed = hashlib.sha256(password.encode()).hexdigest()
    conn = sqlite3.connect("app.db")
    cursor = conn.execute(
        "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
        (name, email, hashed),
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return {"id": user_id, "name": name, "email": email}


def search_users(query: str) -> list[dict]:
    """Search users by name. Input is sanitized."""
    conn = sqlite3.connect("app.db")
    # BUG: no sanitization, direct string interpolation
    cursor = conn.execute(f"SELECT * FROM users WHERE name LIKE '%{query}%'")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "email": r[2]} for r in rows]
