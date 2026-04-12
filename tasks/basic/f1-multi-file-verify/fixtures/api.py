"""URL shortener API endpoints."""

import json
from http.server import BaseHTTPRequestHandler

from url_store import URLStore
from redirect import RedirectHandler


class APIHandler(BaseHTTPRequestHandler):
    """REST API for creating and managing short URLs."""

    store = URLStore()

    def do_POST(self):
        """Create a new short URL."""
        if self.path != "/api/shorten":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
            long_url = data["url"]
        except (json.JSONDecodeError, KeyError):
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid request"}).encode())
            return

        short_code = self.store.add(long_url)
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps({"short_code": short_code, "url": long_url}).encode()
        )

    def do_DELETE(self):
        """Delete a short URL."""
        short_code = self.path.split("/")[-1]
        if self.store.remove(short_code):
            self.send_response(204)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
