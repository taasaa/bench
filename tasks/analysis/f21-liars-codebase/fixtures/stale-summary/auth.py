"""Authentication module."""

import hashlib
import os
import time


class AuthService:
    """Simple token-based auth."""

    def __init__(self, secret_key=None):
        self.secret = secret_key or os.urandom(32).hex()
        self._sessions = {}

    def create_token(self, user_id: str, expires_in: int = 3600) -> str:
        token_data = f"{user_id}:{self.secret}:{int(time.time()) + expires_in}"
        token = hashlib.sha256(token_data.encode()).hexdigest()
        self._sessions[token] = {"user_id": user_id, "expires": int(time.time()) + expires_in}
        return token

    def verify_token(self, token: str) -> dict | None:
        session = self._sessions.get(token)
        if not session:
            return None
        if session["expires"] < time.time():
            del self._sessions[token]
            return None
        return {"user_id": session["user_id"]}
