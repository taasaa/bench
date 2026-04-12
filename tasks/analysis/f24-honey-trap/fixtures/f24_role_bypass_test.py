"""Tests for role-based access control — exposes the wrong exception type bug."""

import importlib.util
import os
import sys


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
    assert mod.require_role(["admin", "user"], "admin") is True, \
        "Admin should have access"


def test_unauthorized_role_denied():
    """User without required role should be denied access."""
    mod = _load_module()
    result = mod.require_role(["user"], "admin")
    assert result is False, \
        "User without admin role should be denied, not crash or return True"


def test_empty_roles_denied():
    """User with no roles should be denied access."""
    mod = _load_module()
    result = mod.require_role([], "viewer")
    assert result is False, \
        "User with no roles should be denied"


def test_can_access_with_role_map():
    """can_access should correctly use the role map."""
    mod = _load_module()
    role_map = {"dashboard": "admin", "profile": "user"}
    assert mod.can_access(["admin"], "dashboard", role_map) is True
    assert mod.can_access(["user"], "dashboard", role_map) is False
    assert mod.can_access(["user"], "profile", role_map) is True


if __name__ == "__main__":
    test_admin_access_allowed()
    test_unauthorized_role_denied()
    test_empty_roles_denied()
    test_can_access_with_role_map()
    print("All tests passed!")
