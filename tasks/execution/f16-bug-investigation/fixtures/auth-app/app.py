"""Auth app entry point."""

from auth_app.middleware import app

if __name__ == "__main__":
    app.run(debug=True)
