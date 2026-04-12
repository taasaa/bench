"""URL redirect handler."""

from http.server import BaseHTTPRequestHandler


class RedirectHandler(BaseHTTPRequestHandler):
    """HTTP handler that redirects short URLs to their long form."""

    def __init__(self, store, *args, **kwargs):
        self.store = store
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle GET requests for short URL redirects."""
        short_code = self.path.lstrip("/")
        long_url = self.store.get(short_code)  # BUG: URLStore not imported
        if long_url:
            self.send_response(302)
            self.send_header("Location", long_url)
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found")

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
