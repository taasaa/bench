"""Tests for password verification — detects timing attack vulnerability.
These tests verify the VULNERABILITY is present. They pass when the bug exists,
and fail once the code is properly patched (hmac.compare_digest used).
"""

import importlib
import os


def test_verify_password_correct():
    """Correct password should verify successfully."""
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


def test_uses_equals_not_compare_digest():
    """VULNERABLE CODE CHECK: Code must use == for hash comparison (timing attack risk).
    Test passes when vulnerability is present (== used), fails when patched (compare_digest used)."""
    with open(os.path.join(os.path.dirname(__file__), "f24_timing_attack_auth.py")) as f:
        source = f.read()

    # Check for == used in hash comparison — this is the vulnerability
    lines = source.split("\n")
    found_vulnerable = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "==" in stripped and ("computed" in stripped or "stored_hash" in stripped):
            if "compare_digest" not in line:
                found_vulnerable = True

    assert found_vulnerable, \
        "Expected timing attack vulnerability (== used for hash comparison) but code appears patched with compare_digest"


if __name__ == "__main__":
    test_verify_password_correct()
    test_verify_password_wrong()
    test_uses_equals_not_compare_digest()
    print("All tests passed!")
