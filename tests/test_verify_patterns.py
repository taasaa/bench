"""Tests for verify.sh pattern reference scripts.

Each of the 4 scripts is tested with known-good and known-bad inputs,
verifying the PASS/FAIL output format and exit codes.
"""

import os
import subprocess

# Resolve the verify scripts directory relative to this test file
VERIFY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates",
)


def _run_script(script_name: str, stdin_data: str, args: list[str]) -> subprocess.CompletedProcess:
    """Run a verify script with stdin and arguments, return CompletedProcess."""
    script_path = os.path.join(VERIFY_DIR, script_name)
    return subprocess.run(
        [script_path, *args],
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=10,
    )


# ============================================================
# byte-identical.sh
# ============================================================


class TestByteIdentical:
    """Tests for byte-identical.sh."""

    def test_identical_input_passes(self, tmp_path):
        """Identical content should produce PASS 1/1."""
        expected = tmp_path / "expected.txt"
        expected.write_text("hello world\nline two\n")
        result = _run_script("byte-identical.sh", "hello world\nline two\n", [str(expected)])
        assert result.returncode == 0
        assert "PASS 1/1" in result.stdout

    def test_different_input_fails(self, tmp_path):
        """Different content should produce FAIL."""
        expected = tmp_path / "expected.txt"
        expected.write_text("hello world\n")
        result = _run_script("byte-identical.sh", "goodbye world\n", [str(expected)])
        assert result.returncode == 1
        assert "FAIL" in result.stdout

    def test_trailing_whitespace_normalized(self, tmp_path):
        """Trailing whitespace differences should be ignored."""
        expected = tmp_path / "expected.txt"
        expected.write_text("hello world   \nline two\t\n")
        result = _run_script("byte-identical.sh", "hello world\nline two\n", [str(expected)])
        assert result.returncode == 0
        assert "PASS 1/1" in result.stdout

    def test_missing_expected_file(self, tmp_path):
        """Missing expected file should produce FAIL with exit code 2."""
        result = _run_script("byte-identical.sh", "data", [str(tmp_path / "nonexistent.txt")])
        assert result.returncode == 2
        assert "FAIL" in result.stdout or "FAIL" in result.stderr

    def test_no_args_usage_error(self):
        """No arguments should produce FAIL with exit code 2."""
        result = _run_script("byte-identical.sh", "data", [])
        assert result.returncode == 2


# ============================================================
# json-parse.sh
# ============================================================


class TestJsonParse:
    """Tests for json-parse.sh."""

    def test_matching_value_passes(self):
        """JSON with matching field value should produce PASS 1/1."""
        payload = '{"name": "alice", "score": 95}'
        result = _run_script("json-parse.sh", payload, [".name", "alice"])
        assert result.returncode == 0
        assert "PASS 1/1" in result.stdout

    def test_wrong_value_fails(self):
        """JSON with non-matching field value should produce FAIL."""
        payload = '{"name": "alice"}'
        result = _run_script("json-parse.sh", payload, [".name", "bob"])
        assert result.returncode == 1
        assert "FAIL" in result.stdout

    def test_numeric_value(self):
        """Numeric JSON values should compare correctly as strings."""
        payload = '{"count": 42}'
        result = _run_script("json-parse.sh", payload, [".count", "42"])
        assert result.returncode == 0
        assert "PASS 1/1" in result.stdout

    def test_invalid_json_fails(self):
        """Invalid JSON should produce FAIL."""
        result = _run_script("json-parse.sh", "not json at all", [".key", "value"])
        assert result.returncode == 1
        assert "FAIL" in result.stdout

    def test_no_args_usage_error(self):
        """No arguments should produce FAIL with exit code 2."""
        result = _run_script("json-parse.sh", '{"a":1}', [])
        assert result.returncode == 2

    def test_missing_expected_value(self):
        """Missing second argument should produce FAIL with exit code 2."""
        result = _run_script("json-parse.sh", '{"a":1}', [".a"])
        assert result.returncode == 2


# ============================================================
# forbidden-string.sh
# ============================================================


class TestForbiddenString:
    """Tests for forbidden-string.sh."""

    def test_clean_input_passes(self):
        """Input with no forbidden strings should produce PASS N/N."""
        payload = "function add(a, b) { return a + b; }"
        result = _run_script("forbidden-string.sh", payload, ["password", "secret"])
        assert result.returncode == 0
        assert "PASS 2/2" in result.stdout

    def test_forbidden_string_fails(self):
        """Input containing a forbidden string should produce FAIL."""
        payload = "const secret = 'abc123';"
        result = _run_script("forbidden-string.sh", payload, ["password", "secret"])
        assert result.returncode == 1
        assert "FAIL" in result.stdout

    def test_case_insensitive(self):
        """Matching should be case-insensitive by default."""
        payload = "const SECRET_KEY = 'abc';"
        result = _run_script("forbidden-string.sh", payload, ["secret"])
        assert result.returncode == 1
        assert "FAIL" in result.stdout

    def test_no_args_usage_error(self):
        """No arguments should produce FAIL with exit code 2."""
        result = _run_script("forbidden-string.sh", "data", [])
        assert result.returncode == 2

    def test_single_pattern_pass(self):
        """Single clean pattern should produce PASS 1/1."""
        result = _run_script("forbidden-string.sh", "hello world", ["password"])
        assert result.returncode == 0
        assert "PASS 1/1" in result.stdout

    def test_multiple_violations(self):
        """Multiple forbidden patterns found should all be reported."""
        payload = "password=abc secret=xyz"
        result = _run_script("forbidden-string.sh", payload, ["password", "secret", "clean"])
        assert result.returncode == 1
        assert "FAIL" in result.stdout
        # Should report 2 violations out of 3 patterns
        assert "1/3" in result.stderr or "2/3" in result.stderr


# ============================================================
# line-count-delta.sh
# ============================================================


class TestLineCountDelta:
    """Tests for line-count-delta.sh."""

    def test_correct_delta_passes(self, tmp_path):
        """Correct line-count delta should produce PASS 1/1."""
        original = tmp_path / "original.txt"
        original.write_text("line1\nline2\nline3\n")
        # Replace line2 → new2: 1 removal, 1 addition
        edited = "line1\nnew2\nline3\n"
        result = _run_script("line-count-delta.sh", edited, [str(original), "+1-1"])
        assert result.returncode == 0
        assert "PASS 1/1" in result.stdout

    def test_wrong_delta_fails(self, tmp_path):
        """Wrong expected delta should produce FAIL."""
        original = tmp_path / "original.txt"
        original.write_text("line1\nline2\nline3\n")
        edited = "line1\nnew2\nline3\n"
        result = _run_script("line-count-delta.sh", edited, [str(original), "+2-0"])
        assert result.returncode == 1
        assert "FAIL" in result.stdout

    def test_pure_addition(self, tmp_path):
        """Adding lines without removing any should work."""
        original = tmp_path / "original.txt"
        original.write_text("line1\nline2\n")
        edited = "line1\nline2\nline3\nline4\n"
        result = _run_script("line-count-delta.sh", edited, [str(original), "+2-0"])
        assert result.returncode == 0
        assert "PASS 1/1" in result.stdout

    def test_pure_removal(self, tmp_path):
        """Removing lines without adding any should work."""
        original = tmp_path / "original.txt"
        original.write_text("line1\nline2\nline3\n")
        edited = "line1\n"
        result = _run_script("line-count-delta.sh", edited, [str(original), "+0-2"])
        assert result.returncode == 0
        assert "PASS 1/1" in result.stdout

    def test_no_change(self, tmp_path):
        """Identical files should produce +0-0 delta."""
        original = tmp_path / "original.txt"
        original.write_text("line1\nline2\n")
        result = _run_script("line-count-delta.sh", "line1\nline2\n", [str(original), "+0-0"])
        assert result.returncode == 0
        assert "PASS 1/1" in result.stdout

    def test_invalid_delta_format(self, tmp_path):
        """Invalid delta format should produce FAIL with exit code 2."""
        original = tmp_path / "original.txt"
        original.write_text("line1\n")
        result = _run_script("line-count-delta.sh", "line1\n", [str(original), "invalid"])
        assert result.returncode == 2
        assert "FAIL" in result.stdout or "FAIL" in result.stderr

    def test_missing_original_file(self, tmp_path):
        """Missing original file should produce FAIL with exit code 2."""
        result = _run_script(
            "line-count-delta.sh", "data", [str(tmp_path / "nonexistent.txt"), "+1-0"]
        )
        assert result.returncode == 2

    def test_no_args_usage_error(self):
        """No arguments should produce FAIL with exit code 2."""
        result = _run_script("line-count-delta.sh", "data", [])
        assert result.returncode == 2
