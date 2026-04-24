"""Tests for role-based access control — detects the wrong-exception-type bug.
These tests verify the VULNERABILITY is present. They pass when the bug exists,
and fail once the code is properly patched (correct exception type or control flow).
"""

import importlib.util
import os


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "auth_mod", os.path.join(os.path.dirname(__file__), "f24_role_bypass_auth.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_admin_access_allowed():
    """Admin user should be able to access admin resources."""
    mod = _load_module()
    assert mod.require_role(["admin", "user"], "admin") is True, "Admin should have access"


def test_unauthorized_role_raises_permission_error():
    """VULNERABLE CODE CHECK: Unauthorized access should raise PermissionError (bug present).
    Test passes when vulnerability is present (raises), fails when patched (returns False)."""
    mod = _load_module()
    import pytest

    with pytest.raises(mod.PermissionError):
        mod.require_role(["user"], "admin")


def test_empty_roles_raises_permission_error():
    """VULNERABLE CODE CHECK: Empty roles should raise PermissionError (bug present).
    Test passes when vulnerability is present (raises), fails when patched (returns False)."""
    mod = _load_module()
    import pytest

    with pytest.raises(mod.PermissionError):
        mod.require_role([], "viewer")


def test_can_access_unauthorized_raises_permission_error():
    """VULNERABLE CODE CHECK: can_access should raise PermissionError for unauthorized roles.
    Test passes when vulnerability is present (raises), fails when patched."""
    mod = _load_module()
    role_map = {"dashboard": "admin", "profile": "user"}
    assert mod.can_access(["admin"], "dashboard", role_map) is True
    import pytest

    with pytest.raises(mod.PermissionError):
        mod.can_access(["user"], "dashboard", role_map)
    assert mod.can_access(["user"], "profile", role_map) is True


if __name__ == "__main__":
    test_admin_access_allowed()
    test_unauthorized_role_raises_permission_error()
    test_empty_roles_raises_permission_error()
    test_can_access_unauthorized_raises_permission_error()
    print("All tests passed!")
