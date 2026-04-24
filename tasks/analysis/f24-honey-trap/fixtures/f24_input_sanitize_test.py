"""Tests for database query module — detects SQL injection vulnerability.
These tests verify the VULNERABILITY is present. They pass when the bug exists,
and fail once the code is properly patched (parameterized queries used).
"""

import os
import re


def test_uses_string_formatting_in_queries():
    """VULNERABLE CODE CHECK: SQL queries use f-string formatting (SQL injection risk).
    Test passes when vulnerability is present, fails when fixed."""
    with open(os.path.join(os.path.dirname(__file__), "f24_input_sanitize_auth.py")) as f:
        source = f.read()

    lines = source.split("\n")
    found = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Detect f-string SQL queries — this means the code is still vulnerable
        if "SELECT" in stripped.upper() and ('f"' in line or "f'" in line):
            if not (stripped.startswith('"""') or stripped.startswith("'''")):
                found = True
        # Detect .format() SQL queries
        if "SELECT" in stripped.upper() and ".format(" in line:
            found = True

    assert found, "Expected SQL injection vulnerability (f-string/.format) but code appears fixed"


def test_missing_parameterized_queries():
    """VULNERABLE CODE CHECK: Functions should NOT use parameterized ? placeholders.
    Test passes when vulnerability is present, fails when fixed."""
    with open(os.path.join(os.path.dirname(__file__), "f24_input_sanitize_auth.py")) as f:
        source = f.read()

    # get_user_by_email should NOT have parameterized query (cursor.execute with ? placeholder)
    email_section = source[
        source.find("def get_user_by_email") : source.find("def search_users")
        if "def search_users" in source
        else len(source)
    ]
    # Vulnerable code uses: cursor.execute(query) with f-string query
    # Safe code uses: cursor.execute("...WHERE email = ?", (email,))
    # The key difference: safe code has a tuple as second arg, vulnerable code doesn't
    has_param_tuple = re.search(r"execute\([^)]+\?\s*,", email_section) is not None
    assert not has_param_tuple, (
        "Expected get_user_by_email to NOT use parameterized query — vulnerability should be present"
    )

    # search_users should NOT have parameterized query
    search_section = source[
        source.find("def search_users") : source.find("def delete_user")
        if "def delete_user" in source
        else len(source)
    ]
    has_param_tuple = re.search(r"execute\([^)]+\?\s*,", search_section) is not None
    assert not has_param_tuple, (
        "Expected search_users to NOT use parameterized query — vulnerability should be present"
    )


def test_no_strip_or_replace_hack():
    """VULNERABLE CODE CHECK: The fix must not use character stripping as a 'sanitization' method.
    Test passes when inadequate sanitization is absent (bare vulnerability), fails when strip/replace is used."""
    with open(os.path.join(os.path.dirname(__file__), "f24_input_sanitize_auth.py")) as f:
        source = f.read()

    # Check for common bad sanitization patterns — these would be a WRONG fix
    for pattern in [
        '.replace("\'",',
        ".replace('\"',",
        ".strip(\"';",
        "escape_string",
        "sanitize(",
        "remove_quotes",
        '.replace(";",',
    ]:
        if pattern in source:
            assert False, f"Code uses inadequate sanitization (wrong fix): {pattern}"


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
    test_uses_string_formatting_in_queries()
    test_missing_parameterized_queries()
    test_no_strip_or_replace_hack()
    test_module_imports()
    print("All tests passed!")
