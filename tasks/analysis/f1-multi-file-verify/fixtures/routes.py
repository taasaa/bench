"""HTTP route handlers for user service."""

import json
from http.server import BaseHTTPRequestHandler

from auth import register, authenticate, get_user


class UserRoutes(BaseHTTPRequestHandler):
    """Route handlers for user registration and login."""

    def do_POST(self):
        """Handle POST requests."""
        if self.path == "/register":
            self._handle_register()
        elif self.path == "/login":
            self._handle_login()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_register(self):
        """Register a new user."""
        body = self._read_body()
        if not body:
            return

        try:
            username = body["username"]
            email = body["email"]
            password = body["password"]
        except KeyError as e:
            # BUG: missing null check — e.args[0] could fail if args is empty
            field = e.args[0]
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Missing field: {field}"}).encode())
            return

        try:
            user = register(username, email, password)
        except ValueError as exc:
            self.send_response(409)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(exc)}).encode())
            return

        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps({"username": user.username, "email": user.email}).encode()
        )

    def _handle_login(self):
        """Authenticate a user."""
        body = self._read_body()
        if not body:
            return

        username = body.get("username")
        password = body.get("password")
        if not username or not password:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Missing credentials"}).encode())
            return

        user = authenticate(username, password)
        if user:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"username": user.username, "email": user.email}).encode()
            )
        else:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid credentials"}).encode())

    def _read_body(self) -> dict | None:
        """Read and parse JSON request body."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return None
        try:
            return json.loads(self.rfile.read(content_length))
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return None
