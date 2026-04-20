"""API route handlers."""
from http.server import BaseHTTPRequestHandler
import json


class RequestHandler(BaseHTTPRequestHandler):
    """Basic HTTP request handler."""

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        self._send_json(404, {"error": "not found"})

    def _send_json(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
