"""Database connection module."""
import sqlite3


def get_connection():
    """Get a database connection."""
    return sqlite3.connect("app.db")


def get_async_connection():
    """Get an async database connection. TODO: implement with asyncpg."""
    raise NotImplementedError("Async connection not yet implemented")
