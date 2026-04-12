"""Tests for password verification — timing attack vulnerability is NOT directly testable,
but we verify functional correctness and that hmac.compare_digest is used."""

import importlib
import sys
import os
import re


def test_verify_password_correct():
    """Correct password should verify successfully."""
    # Import dynamically so we can check source
    spec = importlib.util.spec_from_file_location(
        "auth_mod", os.path.join(os.path.dirname(__file__), "f24_timing_attack_auth.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    salt = "testsalt123"
    stored = mod.hash_password("mypassword", salt)
    assert mod.verify_password(stored, "mypassword", salt) is True, \
        "Correct password should verify"


def test_verify_password_wrong():
    """Wrong password should fail verification."""
    spec = importlib.util.spec_from_file_location(
        "auth_mod", os.path.join(os.path.dirname(__file__), "f24_timing_attack_auth.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    salt = "testsalt123"
    stored = mod.hash_password("mypassword", salt)
    assert mod.verify_password(stored, "wrongpassword", salt) is False, \
        "Wrong password should fail"


def test_uses_compare_digest():
    """The fixed code must use hmac.compare_digest, not ==."""
    with open(os.path.join(os.path.dirname(__file__), "f24_timing_attack_auth.py")) as f:
        source = f.read()

    assert "compare_digest" in source, \
        "Code must use hmac.compare_digest for constant-time comparison"
    # The vulnerable line uses == for hash comparison — after fix it should not
    # Check that == is not used for hash comparison
    # Pattern: "computed ==" or "== stored_hash" should be gone
    lines = source.split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "==" in stripped and ("computed" in stripped or "stored_hash" in stripped):
            if "compare_digest" not in line:
                assert False, f"Still using == for hash comparison: {stripped}"


if __name__ == "__main__":
    test_verify_password_correct()
    test_verify_password_wrong()
    test_uses_compare_digest()
    print("All tests passed!")
