#!/usr/bin/env bash
# verify.sh for f15-workspace-setup (agent-mode task)
# Agent creates files in /tmp/myproject/ or /tmp/api_service/
# We verify after the agent completes

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

cat > "$WORK_DIR/response.txt"

RESPONSE=$(cat "$WORK_DIR/response.txt")

TOTAL_CHECKS=6
PASSED=0

# Scenario detection
if echo "$RESPONSE" | grep -qi "api\|flask\|route\|app.py"; then
    PROJECT_DIR="/tmp/api_service"
else
    PROJECT_DIR="/tmp/myproject"
fi

# Check 1: Project directory exists
if [ -d "$PROJECT_DIR" ]; then
    PASSED=$((PASSED + 1))
else
    echo "  Project directory not created: $PROJECT_DIR" >&2
fi

# Check 2: __init__.py exists with __version__
INIT_FILE="$PROJECT_DIR/__init__.py"
if [ -f "$INIT_FILE" ]; then
    if grep -q '__version__.*=.*"1\.0\.0"\|__version__.*=.*"2\.0\.0"' "$INIT_FILE"; then
        PASSED=$((PASSED + 1))
    else
        echo "  __version__ not set correctly in __init__.py" >&2
    fi
else
    echo "  __init__.py not found" >&2
fi

# Check 3: models.py exists with User/Product dataclass
MODELS_FILE="$PROJECT_DIR/models.py"
if [ -f "$MODELS_FILE" ]; then
    if grep -qE "class (User|Product)" "$MODELS_FILE" && grep -qE "name.*:.*str|email.*:.*str|id.*:.*int" "$MODELS_FILE"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Dataclass not found or missing fields in models.py" >&2
    fi
else
    echo "  models.py not found" >&2
fi

# Check 4: utils.py or app.py exists with expected function/route
if [ -f "$PROJECT_DIR/utils.py" ]; then
    if grep -qE "def is_valid_email" "$PROJECT_DIR/utils.py"; then
        PASSED=$((PASSED + 1))
    else
        echo "  is_valid_email function not found in utils.py" >&2
    fi
elif [ -f "$PROJECT_DIR/app.py" ]; then
    if grep -qE "def do_GET|@app\.route|@app\.get" "$PROJECT_DIR/app.py"; then
        PASSED=$((PASSED + 1))
    else
        echo "  No Flask routes found in app.py" >&2
    fi
else
    echo "  utils.py or app.py not found" >&2
    PASSED=$((PASSED + 1))  # don't double-penalize
fi

# Check 5: tests/ directory with test file
TEST_DIR="$PROJECT_DIR/tests"
if [ -d "$TEST_DIR" ]; then
    TEST_FILE="$TEST_DIR/test_utils.py"
    [ -f "$PROJECT_DIR/tests/test_app.py" ] && TEST_FILE="$PROJECT_DIR/tests/test_app.py"
    if [ -f "$TEST_FILE" ] && grep -qE "def test_|pytest|unittest" "$TEST_FILE"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Test file not found or has no test functions" >&2
    fi
else
    echo "  tests/ directory not found" >&2
fi

# Check 6: Tests were run (agent reported test output)
if echo "$RESPONSE" | grep -qiE "passed|failed|error|ok|test"; then
    PASSED=$((PASSED + 1))
else
    echo "  Agent did not report test results" >&2
fi

if [[ $PASSED -ge 4 ]]; then
    # At least 4/6 checks = reasonable completion
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi