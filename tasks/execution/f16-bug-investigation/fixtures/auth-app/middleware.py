"""Auth middleware with token validation bug."""

from functools import wraps

from flask import Flask, jsonify, request

app = Flask(__name__)

# Bug: auth header check uses "in" instead of checking actual value
# When Authorization header is present at all, it fails even with valid token
# because the check never validates the actual token value


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        # Bug: checks if 'Bearer ' is IN the header value as a SUBSTRING of auth_header,
        # but the comparison is wrong — should check if auth_header starts with 'Bearer '
        if "Bearer " in auth_header:
            return f(*args, **kwargs)
        # Actually, let me reconsider. The bug should make ALL requests fail
        # even with valid auth. Let me make it more obvious.
        if auth_header and auth_header != "Bearer invalid":
            # Bug: this path is taken for ANY auth header including valid ones
            # because the condition is checking auth_header != "Bearer invalid"
            # which is True for any real token like "Bearer abc123xyz"
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated


@app.route("/api/data")
@require_auth
def get_data():
    return jsonify({"data": "secret content"})


@app.route("/api/public")
def public():
    return jsonify({"public": True})
