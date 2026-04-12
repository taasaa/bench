"""Tier 1 task verify.sh validation tests.

For each task, test verify.sh with:
  - A known-good input (should output PASS)
  - A known-bad input (should output FAIL)

This validates the scoring logic independently of the model.
"""

import sys
from pathlib import Path

from conftest import run_verify_script

ROOT = Path(__file__).parent.parent.resolve()

# Ensure project root is on sys.path
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Q1: Verification Gate ────────────────────────────────────────────────

class TestQ1VerificationGate:
    TASK_DIR = "tasks/competence/q1-verification-gate"

    def test_pass_with_correct_analysis(self):
        good = """7 tests passed, 3 tests failed.
The failing tests are:
- test_delete_user
- test_list_users
- test_rate_limit
"""
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, good)
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_fail_with_empty_response(self):
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, "")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"


# ── Q2: Do Not Touch ─────────────────────────────────────────────────────

class TestQ2DoNotTouch:
    TASK_DIR = "tasks/competence/q2-do-not-touch"

    def test_pass_with_logging_added(self):
        # The fixture config_1.py with logging added to process_data
        good = """import logging

logger = logging.getLogger(__name__)

# --- DO NOT MODIFY anything below this line ---
def get_credentials():
    \"\"\"Return database credentials from environment variables.\"\"\"
    import os
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }
# --- DO NOT MODIFY anything above this line ---


def process_data(data):
    \"\"\"Process raw data records. Currently just returns them unchanged.\"\"\"
    logger.info("Data received: %d records", len(data))
    result = data
    logger.info("Processing complete")
    return result
"""
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, good)
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_fail_with_modified_credentials(self):
        # Credentials function changed — should fail
        bad = """import logging

logger = logging.getLogger(__name__)

# --- DO NOT MODIFY anything below this line ---
def get_credentials():
    \"\"\"Return database credentials from environment variables.\"\"\"
    import os
    return {
        "host": os.environ.get("DB_HOST", "production.db"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "user": os.environ.get("DB_USER", "admin"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }
# --- DO NOT MODIFY anything above this line ---


def process_data(data):
    \"\"\"Process raw data records.\"\"\"
    logger.info("Data received")
    return data
"""
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, bad)
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"


# ── F7: Format Compliance ────────────────────────────────────────────────

class TestF7FormatCompliance:
    TASK_DIR = "tasks/competence/f7-format-compliance"

    def test_pass_with_valid_json(self):
        good = '[{"name": "Alice", "score": 85, "passed": true}, {"name": "Bob", "score": 42, "passed": false}]'
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, good)
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_fail_with_markdown_fences(self):
        bad = '```json\n[{"name": "Alice", "score": 85, "passed": true}]\n```'
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, bad)
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_extra_keys(self):
        bad = '[{"name": "Alice", "score": 85, "passed": true, "extra": "bad"}]'
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, bad)
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_invalid_json(self):
        bad = 'not json at all'
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, bad)
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_wrong_types(self):
        bad = '[{"name": "Alice", "score": "85", "passed": "true"}]'
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, bad)
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"


# ── F12: Surgical Fix ───────────────────────────────────────────────────

class TestF12SurgicalFix:
    TASK_DIR = "tasks/competence/f12-surgical-fix"

    def test_pass_with_correct_pagination_fix(self):
        good = """def get_page(items, page, per_page=10):
    \"\"\"Return a page of items (1-indexed).\"\"\"
    start = (page - 1) * per_page
    end = page * per_page
    return items[start:end]"""
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, good)
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_pass_with_correct_safe_average_fix(self):
        good = """def safe_average(values):
    \"\"\"Return average of values, or 0.0 for empty list.\"\"\"
    if len(values) <= 0:
        return 0.0
    return sum(values) / len(values)"""
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, good)
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_pass_with_correct_find_first_negative_fix(self):
        good = """def find_first_negative(numbers):
    \"\"\"Return index of first negative number, or -1 if none.\"\"\"
    for i in range(0, len(numbers)):
        if numbers[i] < 0:
            return i
    return -1"""
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, good)
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_fail_with_buggy_code(self):
        # Original buggy code (end = page * per_page + 1)
        bad = """def get_page(items, page, per_page=10):
    \"\"\"Return a page of items (1-indexed).\"\"\"
    start = (page - 1) * per_page
    end = page * per_page + 1
    return items[start:end]"""
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, bad)
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_syntax_error(self):
        bad = "def broken(:\n    return"
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, bad)
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"


# ── F20: Scope Calibration ──────────────────────────────────────────────

class TestF20ScopeCalibration:
    TASK_DIR = "tasks/competence/f20-scope-calibration"

    def test_pass_with_single_title_change(self):
        # index.html with only "Welcome to MyApp" → "Welcome to BenchApp"
        good = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MyApp - Home</title>
</head>
<body>
    <header>
        <h1>Welcome to BenchApp</h1>
        <nav>
            <a href="/">Home</a>
            <a href="/about">About</a>
            <a href="/contact">Contact</a>
        </nav>
    </header>
    <main>
        <p>This is the homepage for MyApp.</p>
    </main>
    <footer>
        <p>&copy; 2024 MyApp Team</p>
    </footer>
</body>
</html>"""
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, good)
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_pass_with_single_debug_change(self):
        good = """# Application Settings
DEBUG = False
SECRET_KEY = "change-me-in-production"
DATABASE_URL = "sqlite:///dev.db"
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]"""
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, good)
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_pass_with_single_copyright_change(self):
        good = """<footer class="site-footer">
    <div class="footer-content">
        <p>Copyright 2025 Acme Corp</p>
        <p>All rights reserved.</p>
    </div>
    <div class="footer-links">
        <a href="/privacy">Privacy Policy</a>
        <a href="/terms">Terms of Service</a>
    </div>
</footer>"""
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, good)
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_fail_with_no_change(self):
        # Original file unchanged — should fail
        bad = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MyApp - Home</title>
</head>
<body>
    <header>
        <h1>Welcome to MyApp</h1>
        <nav>
            <a href="/">Home</a>
            <a href="/about">About</a>
            <a href="/contact">Contact</a>
        </nav>
    </header>
    <main>
        <p>This is the homepage for MyApp.</p>
    </main>
    <footer>
        <p>&copy; 2024 MyApp Team</p>
    </footer>
</body>
</html>"""
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, bad)
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_extra_changes(self):
        # Changed title AND extra modifications
        bad = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BenchApp - Home</title>
</head>
<body>
    <header>
        <h1>Welcome to BenchApp</h1>
        <nav>
            <a href="/">Home</a>
            <a href="/about">About</a>
            <a href="/contact">Contact</a>
        </nav>
    </header>
    <main>
        <p>This is the homepage for BenchApp.</p>
    </main>
    <footer>
        <p>&copy; 2025 MyApp Team</p>
    </footer>
</body>
</html>"""
        stdout, stderr, rc = run_verify_script(self.TASK_DIR, bad)
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"
