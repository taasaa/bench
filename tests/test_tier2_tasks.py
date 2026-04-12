"""Tier 2 task verify.sh validation tests.

For each of the 5 Tier 2 tasks (f6, f8, f14, q4, f11), test verify.sh with:
  - A known-good input per sample (should output PASS)
  - A known-bad input per sample (should output FAIL)

This validates the scoring logic independently of the model.
"""

import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _run_verify(task_dir: str, input_text: str, sample_id: str | None = None) -> tuple[str, str, int]:
    """Run verify.sh in the given task dir with input_text on stdin.

    Args:
        task_dir: Relative path from project root to the task directory.
        input_text: Text to pipe to verify.sh via stdin.
        sample_id: Optional SAMPLE_ID env var value.

    Returns:
        (stdout, stderr, returncode)
    """
    script = os.path.join(ROOT, task_dir, "verify.sh")
    assert os.path.isfile(script), f"verify.sh not found: {script}"
    assert os.access(script, os.X_OK), f"verify.sh not executable: {script}"

    env = os.environ.copy()
    if sample_id is not None:
        env["SAMPLE_ID"] = sample_id

    proc = subprocess.run(
        [script],
        input=input_text,
        capture_output=True,
        text=True,
        timeout=10,
        cwd=os.path.join(ROOT, task_dir),
        env=env,
    )
    return proc.stdout.strip(), proc.stderr.strip(), proc.returncode


# ═══════════════════════════════════════════════════════════════════════════
# F6: Partial Implementation
# ═══════════════════════════════════════════════════════════════════════════

class TestF6PartialImpl:
    TASK_DIR = "tasks/basic/f6-partial-impl"

    # ── Per-sample known-good tests ──────────────────────────────────────

    @pytest.mark.parametrize("sample_id,class_name,m1,m2", [
        ("f6-cache-get-set", "Cache", "get", "set"),
        ("f6-store-read-write", "Store", "read", "write"),
        ("f6-registry-find-register", "Registry", "find", "register"),
        ("f6-lookup-query-store", "Lookup", "query", "store"),
    ])
    def test_pass_with_minimal_class(self, sample_id, class_name, m1, m2):
        code = f"""class {class_name}:
    def __init__(self):
        self._data = {{}}

    def {m1}(self, key):
        return self._data.get(key)

    def {m2}(self, key, value):
        self._data[key] = value
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, sample_id)
        assert stdout.startswith("PASS"), f"Expected PASS for {sample_id}, got: {stdout}\nstderr: {stderr}"

    # ── Known-bad tests ──────────────────────────────────────────────────

    def test_fail_with_extra_methods(self):
        """Adding forbidden methods (delete, clear) should FAIL."""
        code = """class Cache:
    def __init__(self):
        self._data = {}

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value

    def delete(self, key):
        del self._data[key]

    def clear(self):
        self._data.clear()
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f6-cache-get-set")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_ttl_logic(self):
        """Adding TTL/expiry logic should FAIL."""
        code = """import time

class Cache:
    def __init__(self):
        self._data = {}
        self._expiry = {}

    def get(self, key):
        if key in self._expiry and time.time() > self._expiry[key]:
            del self._data[key]
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value
        self._expiry[key] = time.time() + 3600
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f6-cache-get-set")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_wrong_class_name(self):
        """Wrong class name should FAIL."""
        code = """class MyCache:
    def __init__(self):
        self._data = {}

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f6-cache-get-set")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_missing_method(self):
        """Missing one of the required methods should FAIL."""
        code = """class Cache:
    def __init__(self):
        self._data = {}

    def get(self, key):
        return self._data.get(key)
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f6-cache-get-set")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_empty_response(self):
        """Empty response should FAIL."""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, "")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"


# ═══════════════════════════════════════════════════════════════════════════
# F8: Negative Constraint Chain
# ═══════════════════════════════════════════════════════════════════════════

class TestF8NegativeConstraint:
    TASK_DIR = "tasks/basic/f8-negative-constraint"

    @pytest.mark.parametrize("sample_id,func_name,param_name", [
        ("f8-fetch-user", "fetch_user", "user_id"),
        ("f8-fetch-product", "fetch_product", "product_id"),
        ("f8-fetch-order", "fetch_order", "order_id"),
        ("f8-fetch-article", "fetch_article", "article_id"),
    ])
    def test_pass_with_correct_function(self, sample_id, func_name, param_name):
        code = f"""import requests

def {func_name}({param_name}):
    if not isinstance({param_name}, int) or {param_name} <= 0:
        raise ValueError("{param_name} must be a positive integer")
    try:
        response = requests.get(f"https://api.example.com/{func_name}s/{{param_name}}")
        return response.json()
    except requests.exceptions.RequestException:
        raise ConnectionError("Network request failed")
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, sample_id)
        assert stdout.startswith("PASS"), f"Expected PASS for {sample_id}, got: {stdout}\nstderr: {stderr}"

    def test_fail_with_retry_logic(self):
        """Adding retry logic should FAIL."""
        code = (
            "import requests\n"
            "\n"
            "def fetch_user(user_id):\n"
            "    if not isinstance(user_id, int) or user_id <= 0:\n"
            "        raise ValueError('user_id must be a positive integer')\n"
            "    retry_count = 0\n"
            "    max_retry = 3\n"
            "    while retry_count < max_retry:\n"
            "        try:\n"
            "            response = requests.get('https://api.example.com/users/' + str(user_id))\n"
            "            return response.json()\n"
            "        except requests.exceptions.RequestException:\n"
            "            retry_count += 1\n"
            "    raise ConnectionError('Network request failed')\n"
        )
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f8-fetch-user")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_caching(self):
        """Adding caching should FAIL."""
        code = """import requests

_cache = {}

def fetch_user(user_id):
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    if user_id in _cache:
        return _cache[user_id]
    try:
        response = requests.get(f"https://api.example.com/users/{user_id}")
        result = response.json()
        _cache[user_id] = result
        return result
    except requests.exceptions.RequestException:
        raise ConnectionError("Network request failed")
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f8-fetch-user")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_logging(self):
        """Adding logging should FAIL."""
        code = """import requests
import logging

logger = logging.getLogger(__name__)

def fetch_user(user_id):
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    logger.info("Fetching user %s", user_id)
    try:
        response = requests.get(f"https://api.example.com/users/{user_id}")
        return response.json()
    except requests.exceptions.RequestException:
        raise ConnectionError("Network request failed")
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f8-fetch-user")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_without_requests_import(self):
        """Missing requests import should FAIL."""
        code = """def fetch_user(user_id):
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    import urllib.request
    response = urllib.request.urlopen(f"https://api.example.com/users/{user_id}")
    return response.read()
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f8-fetch-user")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_without_value_error(self):
        """Missing ValueError should FAIL."""
        code = """import requests

def fetch_user(user_id):
    try:
        response = requests.get(f"https://api.example.com/users/{user_id}")
        return response.json()
    except requests.exceptions.RequestException:
        raise ConnectionError("Network request failed")
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f8-fetch-user")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_empty_response(self):
        """Empty response should FAIL."""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, "")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"


# ═══════════════════════════════════════════════════════════════════════════
# F14: Insert Don't Replace
# ═══════════════════════════════════════════════════════════════════════════

class TestF14InsertDontReplace:
    TASK_DIR = "tasks/basic/f14-insert-dont-replace"

    def test_pass_with_discount_inserted(self):
        """Discount logic inserted between subtotal and tax should PASS."""
        code = """def calculate_total(items):
    subtotal = sum(items)
    if subtotal > 100:
        subtotal = subtotal * 0.9
    tax = subtotal * 0.08
    return round(subtotal + tax, 2)
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f14-discount")
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_pass_with_validation_inserted(self):
        """Validation logic inserted before processing should PASS."""
        code = """def process_age(age):
    if not isinstance(age, int) or age <= 0:
        raise ValueError("Age must be a positive integer")
    age_str = str(age)
    age_len = len(age_str)
    return f"Age: {age_str} (digits: {age_len})"
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f14-validation")
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_pass_with_free_shipping_inserted(self):
        """Free shipping logic inserted should PASS."""
        code = """def calculate_shipping(weight):
    base_rate = weight * 2.50
    handling = 5.00
    if weight > 10:
        return 0.0
    return round(base_rate + handling, 2)
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f14-shipping")
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_pass_with_capitalize_inserted(self):
        """Capitalization logic inserted between split and join should PASS."""
        code = """def format_name(name):
    parts = name.strip().split()
    parts = [p.capitalize() for p in parts]
    result = " ".join(parts)
    return result
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f14-capitalize")
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_fail_with_modified_original_line(self):
        """Changing an original line (not just inserting) should FAIL."""
        code = """def calculate_total(items):
    subtotal = sum(items) * 0.9  # Modified! Original was just sum(items)
    tax = subtotal * 0.08
    return round(subtotal + tax, 2)
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f14-discount")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_no_new_logic(self):
        """No new logic inserted should FAIL."""
        code = """def calculate_total(items):
    subtotal = sum(items)
    tax = subtotal * 0.08
    return round(subtotal + tax, 2)
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f14-discount")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_empty_response(self):
        """Empty response should FAIL."""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, "")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_wrong_return_value(self):
        """Correct lines present but wrong return value should FAIL correctness check."""
        code = """def calculate_total(items):
    subtotal = sum(items)
    subtotal = subtotal - 50  # Wrong discount logic
    tax = subtotal * 0.08
    return round(subtotal + tax, 2)
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, code, "f14-discount")
        # This should fail because the function returns wrong values
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"


# ═══════════════════════════════════════════════════════════════════════════
# Q4: Root Cause Not Symptom
# ═══════════════════════════════════════════════════════════════════════════

class TestQ4RootCause:
    TASK_DIR = "tasks/basic/q4-root-cause"

    def test_pass_pip_python_mismatch(self):
        """Correct root cause diagnosis for pip/python mismatch should PASS."""
        response = """The problem is that pip and python3 are pointing to different Python installations.
You can verify this by running `which pip` and `which python3` — they likely show different paths.

The fix is to use `python3 -m pip install requests` instead of bare `pip install requests`.
This ensures you're installing into the same Python that python3 uses.

Alternatively, create a virtualenv and activate it so both pip and python are consistent."""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, response, "q4-pip-python-mismatch")
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_pass_node_npx_mismatch(self):
        """Correct root cause diagnosis for node/npx mismatch should PASS."""
        response = """This is a PATH issue. The npm global bin directory is not in your PATH.

If you're using nvm, run `nvm use` to ensure the correct node version is active.
You can also use `npx tsc --version` to run typescript without relying on the global install.

To fix permanently, check `npm config get prefix` and add its bin directory to your PATH:
`export PATH="$(npm config get prefix)/bin:$PATH"`"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, response, "q4-node-npx-mismatch")
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_pass_docker_compose_port(self):
        """Correct root cause for docker compose networking should PASS."""
        response = """Containers in Docker Compose use a Docker network, not localhost.
Your app container needs to connect to the database using the service name as hostname, not localhost.

Change your database host configuration from `localhost` to the compose service name:
`host=db` (or whatever your database service is named in docker-compose.yml).

Docker Compose creates a network where containers resolve each other by service name.
You can also use `depends_on` in compose to ensure startup order."""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, response, "q4-docker-compose-port")
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_pass_cron_path_issue(self):
        """Correct root cause for cron environment should PASS."""
        response = """Cron runs with a minimal PATH and different environment from your interactive shell.
That's why it can't find pandas even though it works in your terminal.

Fix: Set the full PATH in your crontab entry:
```
PATH=/usr/local/bin:/usr/bin:/bin
0 9 * * * python3 /opt/scripts/daily_report.py
```

Or source your profile first:
```
0 9 * * * source ~/.bashrc && python3 /opt/scripts/daily_report.py
```

You can also use the full path: `/usr/bin/python3`."""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, response, "q4-cron-path-issue")
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_fail_with_symptom_fix(self):
        """Suggesting symptom fix (pip install --user) should FAIL."""
        response = """Just run `pip install --user requests` to install it for your user.
Or try `sudo pip install requests` for a system-wide install.
That should fix the import error."""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, response, "q4-pip-python-mismatch")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_no_root_cause(self):
        """Not identifying root cause should FAIL."""
        response = """This is a strange error. Try reinstalling everything from scratch.
Maybe update your pip version first."""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, response, "q4-pip-python-mismatch")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_no_fix(self):
        """No actionable fix command should FAIL."""
        response = """The issue is that pip and python3 are in different environments.
You should fix your setup."""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, response, "q4-pip-python-mismatch")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_empty_response(self):
        """Empty response should FAIL."""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, "")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"


# ═══════════════════════════════════════════════════════════════════════════
# F11: Intermittent Bug
# ═══════════════════════════════════════════════════════════════════════════

class TestF11IntermittentBug:
    TASK_DIR = "tasks/basic/f11-intermittent-bug"

    def test_pass_sleep_timestamp(self):
        """Correct diagnosis of timing-dependent tests should PASS."""
        response = """These tests have timing-dependent assertions that aren't deterministic.
Using fixed `time.sleep()` durations makes them fragile, especially on slower CI runners.

The fix is to replace sleep-based waits with polling or wait-for-condition patterns:
- Use a retry loop with `assert eventually` pattern
- Poll until the condition is met (e.g., `while not condition: time.sleep(0.01)`)
- Or use `time.monotonic()` for reliable elapsed time measurement
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, response, "f11-sleep-timestamp")
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_pass_concurrent_file_access(self):
        """Correct diagnosis of race condition should PASS."""
        response = """This is a race condition between the writer process and the reader.
`Popen` starts the process but doesn't wait for it to complete, so the file may not exist yet.

Fix: Use `subprocess.wait()` to block until the writer finishes:
```python
proc = subprocess.Popen(['python', 'write_data.py', filepath])
proc.wait()
```

Or poll for the file to exist:
```python
while not os.path.exists(filepath):
    time.sleep(0.1)
```

You could also use `proc.communicate()` which waits for completion."""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, response, "f11-concurrent-file-access")
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_pass_timeout_flaky(self):
        """Correct diagnosis of timeout-based flakiness should PASS."""
        response = """The tests use hardcoded sleep durations that aren't enough on slow CI.
This is a non-deterministic timing issue.

Fix: Replace fixed sleeps with event-based waiting or polling:
- For BackgroundTask: poll `while not task.is_complete:` with short sleeps
- For WebSocket: use `thread.join()` or wait for a condition with retry
- Use exponential backoff in the poll loop
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, response, "f11-timeout-flaky")
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_pass_datetime_mock(self):
        """Correct diagnosis of datetime boundary issue should PASS."""
        response = """The tests use `datetime.now()` and `date.today()` which are non-deterministic —
they capture real wall-clock time that can shift across midnight boundaries.

Fix: Inject a fixed time or use freezegun to mock time:
```python
from freezegun import freeze_time
with freeze_time("2024-01-15 12:00:00"):
    result = is_expired(expiry)
```

Or pass the current time as a parameter to make it deterministic:
```python
def is_expired(expiry, now=None):
    now = now or datetime.now()
```
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, response, "f11-datetime-mock")
        assert stdout.startswith("PASS"), f"Expected PASS, got: {stdout}\nstderr: {stderr}"

    def test_fail_with_increase_sleep(self):
        """Suggesting 'increase sleep to X' should FAIL."""
        response = """The problem is timing. You should increase the sleep duration to be safe.
For test_api_response_time, increase sleep to 0.5 seconds.
For test_cache_invalidation, change sleep to 0.2 seconds.
This will make the tests more reliable.
"""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, response, "f11-sleep-timestamp")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_no_diagnosis(self):
        """Not identifying timing issue should FAIL."""
        response = """This seems like a CI issue. Try running the tests again.
Sometimes GitHub Actions is just slow. Maybe contact support."""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, response, "f11-sleep-timestamp")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"

    def test_fail_with_empty_response(self):
        """Empty response should FAIL."""
        stdout, stderr, rc = _run_verify(self.TASK_DIR, "")
        assert stdout.startswith("FAIL"), f"Expected FAIL, got: {stdout}"
