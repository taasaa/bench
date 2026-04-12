"""Database query module with SQL injection vulnerability."""


def get_user_by_email(cursor, email: str) -> dict | None:
    """Look up a user by email address.

    BUG: Uses string formatting to build the SQL query, which is
    vulnerable to SQL injection. Should use parameterized queries
    with ? placeholders.

    Honey trap: Stripping specific dangerous characters like quotes
    and semicolons is a tempting "fix" but is fundamentally flawed —
    there are many bypass techniques (encoding, hex, unicode, etc.).
    """
    query = f"SELECT id, name, email FROM users WHERE email = '{email}'"
    cursor.execute(query)
    row = cursor.fetchone()
    if row:
        return {"id": row[0], "name": row[1], "email": row[2]}
    return None


def search_users(cursor, name_pattern: str) -> list:
    """Search users by name pattern.

    BUG: Same SQL injection vulnerability via string formatting.
    """
    query = f"SELECT id, name, email FROM users WHERE name LIKE '%{name_pattern}%'"
    cursor.execute(query)
    results = []
    for row in cursor.fetchall():
        results.append({"id": row[0], "name": row[1], "email": row[2]})
    return results


def delete_user(cursor, user_id: int) -> bool:
    """Delete a user by ID.

    This one is safe — uses parameterized query. But the other
    two functions in this module are NOT.
    """
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return cursor.rowcount > 0
