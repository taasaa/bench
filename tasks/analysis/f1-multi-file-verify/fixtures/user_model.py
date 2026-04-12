"""User model for authentication system."""

from dataclasses import dataclass, field
import hashlib
import os


@dataclass
class User:
    """Represents a user in the system."""

    username: str
    email: str
    password_hash: str = ""
    salt: str = field(default_factory=lambda: os.urandom(16).hex())

    def set_password(self, raw_password: str) -> None:
        """Hash and store the password."""
        self.password_hash = hashlib.sha256(
            f"{self.salt}{raw_password}".encode()
        ).hexdigest()

    def check_password(self, raw_password: str) -> bool:
        """Verify a password against the stored hash."""
        candidate = hashlib.sha256(
            f"{self.salt}{raw_password}".encode()
        ).hexdigest()
        return candidate == self.password_hash


def create_user(username: str, email: str, password: str) -> User:
    """Factory function to create a new user."""
    user = User(username=username, email=email)
    user.set_password(password)
    return user
