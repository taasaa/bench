"""Flask app with subtle status endpoint bug."""

from flask import Flask, jsonify

app = Flask(__name__)

# Bug: status_endpoint_debug is never set, so this always goes to error path
_status_endpoint_debug = False


@app.route("/api/status")
def status():
    if _status_endpoint_debug:
        return jsonify({"status": "ok"})
    else:
        return jsonify({"status": "error"})


@app.route("/api/health")
def health():
    return jsonify({"healthy": True})


if __name__ == "__main__":
    app.run(debug=True)
