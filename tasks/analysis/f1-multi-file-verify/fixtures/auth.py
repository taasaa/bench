"""Authentication module."""

from user_model import User, create_user

# In-memory user store
_users: dict[str, User] = {}


def register(username: str, email: str, password: str) -> User:
    """Register a new user."""
    if username in _users:
        raise ValueError(f"User {username} already exists")
    user = create_user(username, email, password)
    _users[username] = user
    return user


def authenticate(username: str, password: str) -> User | None:
    """Authenticate a user by username and password.

    Returns the User object on success, None on failure.
    """
    user = _users.get(username)
    if user is None:
        return None

    # BUG: uses 'password' attribute instead of 'password_hash'
    stored_hash = user.password  # should be user.password_hash
    from user_model import hashlib

    candidate = hashlib.sha256(f"{user.salt}{password}".encode()).hexdigest()
    if candidate == stored_hash:
        return user
    return None


def get_user(username: str) -> User | None:
    """Look up a user by username."""
    return _users.get(username)
