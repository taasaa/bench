"""Tests for database query module — verifies parameterized queries are used."""

import os
import re


def test_no_string_formatting_in_queries():
    """SQL queries must use parameterized ? placeholders, not f-strings or % formatting."""
    with open(os.path.join(os.path.dirname(__file__), "f24_input_sanitize_auth.py")) as f:
        source = f.read()

    # Find all query strings — they should NOT use f-strings or .format()
    lines = source.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip comments and the delete function (which is already safe)
        if stripped.startswith("#"):
            continue
        # Check for f-string SQL queries
        if "SELECT" in stripped.upper() and ("f\"" in line or "f'" in line):
            # If it's in a comment, skip
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            assert False, f"Line {i}: SQL query uses f-string (SQL injection risk): {stripped}"
        # Check for .format() SQL queries
        if "SELECT" in stripped.upper() and ".format(" in line:
            assert False, f"Line {i}: SQL query uses .format() (SQL injection risk): {stripped}"


def test_uses_parameterized_queries():
    """get_user_by_email and search_users must use ? placeholders."""
    with open(os.path.join(os.path.dirname(__file__), "f24_input_sanitize_auth.py")) as f:
        source = f.read()

    # Check that email lookup uses parameterized query
    assert "WHERE email = ?" in source or 'WHERE email = "%s"' not in source, \
        "get_user_by_email must use parameterized query"
    # More specifically, check for ? placeholder in email lookup
    # The fixed version should have: cursor.execute("... WHERE email = ?", (email,))
    email_section = source[source.find("get_user_by_email"):source.find("def search_users") if "def search_users" in source else len(source)]
    assert "?" in email_section and "execute" in email_section, \
        "get_user_by_email must use parameterized query with ? placeholder"

    # Check name search uses parameterized query
    search_section = source[source.find("search_users"):source.find("def delete_user") if "def delete_user" in source else len(source)]
    assert "?" in search_section and "execute" in search_section, \
        "search_users must use parameterized query with ? placeholder"


def test_no_strip_or_replace_hack():
    """The fix must not use character stripping as a 'sanitization' method."""
    with open(os.path.join(os.path.dirname(__file__), "f24_input_sanitize_auth.py")) as f:
        source = f.read()

    # Check for common bad sanitization patterns
    for pattern in [".replace(\"'\",", ".replace('\"',", ".strip(\"';", "escape_string",
                    "sanitize(", "remove_quotes", ".replace(\";\","]:
        if pattern in source:
            assert False, f"Code uses inadequate sanitization: {pattern}"


def test_module_imports():
    """Module should be importable."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "auth_mod", os.path.join(os.path.dirname(__file__), "f24_input_sanitize_auth.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "get_user_by_email")
    assert hasattr(mod, "search_users")
    assert hasattr(mod, "delete_user")


if __name__ == "__main__":
    test_no_string_formatting_in_queries()
    test_uses_parameterized_queries()
    test_no_strip_or_replace_hack()
    test_module_imports()
    print("All tests passed!")
