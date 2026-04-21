#!/usr/bin/env bash
# verify.sh for f15-workspace-setup
# Dual-mode: agent creates real files OR model outputs a project plan as text.
# Detects mode by checking whether the expected directory exists.
# In model-eval mode, scores whether the response correctly describes
# all required project components.

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

cat > "$WORK_DIR/response.txt"
RESPONSE=$(cat "$WORK_DIR/response.txt")

TOTAL_CHECKS=6
PASSED=0

# Scenario detection from response content
if echo "$RESPONSE" | grep -qi "api\|flask\|route\|app\.py"; then
    IS_API=0
else
    IS_API=1
fi
if [[ $IS_API -eq 0 ]]; then
    PROJECT_DIR="/tmp/api_service"
    EXPECTED_VERSION="2.0.0"
else
    PROJECT_DIR="/tmp/myproject"
    EXPECTED_VERSION="1.0.0"
fi

# ──────────────────────────────────────────────────────────────────────────────
# AGENT MODE: real files were created
# ──────────────────────────────────────────────────────────────────────────────
if [ -d "$PROJECT_DIR" ]; then

    # Check 1: Project directory exists
    PASSED=$((PASSED + 1))

    # Check 2: __init__.py with correct __version__
    INIT_FILE="$PROJECT_DIR/__init__.py"
    if [ -f "$INIT_FILE" ] && grep -q "__version__.*=.*\"$EXPECTED_VERSION\"" "$INIT_FILE"; then
        PASSED=$((PASSED + 1))
    else
        echo "  __version__ not '$EXPECTED_VERSION' in __init__.py" >&2
    fi

    # Check 3: models.py with User/Product dataclass
    MODELS_FILE="$PROJECT_DIR/models.py"
    if [ -f "$MODELS_FILE" ] && grep -qE "class (User|Product)" "$MODELS_FILE" \
        && grep -qE "name.*:.*str|email.*:.*str|id.*:.*int" "$MODELS_FILE"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Dataclass not found or missing fields in models.py" >&2
    fi

    # Check 4: utils.py with is_valid_email OR app.py with Flask route
    if [ -f "$PROJECT_DIR/utils.py" ] && grep -qE "def is_valid_email" "$PROJECT_DIR/utils.py"; then
        PASSED=$((PASSED + 1))
    elif [ -f "$PROJECT_DIR/app.py" ] && grep -qE "def do_GET|@app\.route|@app\.get" "$PROJECT_DIR/app.py"; then
        PASSED=$((PASSED + 1))
    else
        echo "  utils.py/app.py not found or missing expected function/route" >&2
    fi

    # Check 5: tests/ directory with test file
    TEST_FILE=""
    [ -f "$PROJECT_DIR/tests/test_utils.py" ] && TEST_FILE="$PROJECT_DIR/tests/test_utils.py"
    [ -f "$PROJECT_DIR/tests/test_app.py" ] && TEST_FILE="$PROJECT_DIR/tests/test_app.py"
    if [ -n "$TEST_FILE" ] && grep -qE "def test_|pytest|unittest" "$TEST_FILE"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Test file not found or has no test functions" >&2
    fi

    # Check 6: Agent reported test output
    if echo "$RESPONSE" | grep -qiE "passed|failed|error|ok"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Agent did not report test results" >&2
    fi

# ──────────────────────────────────────────────────────────────────────────────
# MODEL-EVAL MODE: response is text describing the project plan
# ──────────────────────────────────────────────────────────────────────────────
else

    # Check 1: Response describes creating the correct project directory
    if echo "$RESPONSE" | grep -qiE "mkdir.*$PROJECT_DIR|create.*$PROJECT_DIR|project.*$PROJECT_DIR"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Response does not describe creating $PROJECT_DIR" >&2
    fi

    # Check 2: Response includes correct __version__ value
    if echo "$RESPONSE" | grep -q "__version__.*=.*\"$EXPECTED_VERSION\""; then
        PASSED=$((PASSED + 1))
    else
        echo "  Response does not include __version__ = '$EXPECTED_VERSION'" >&2
    fi

    # Check 3: Response includes User/Product dataclass with required fields
    if echo "$RESPONSE" | grep -qE "class (User|Product)" \
        && echo "$RESPONSE" | grep -qE "name.*:.*str|email.*:.*str"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Response missing User/Product dataclass with required fields" >&2
    fi

    # Check 4: Response describes is_valid_email (library) or Flask routes (API)
    if [[ $IS_API -eq 0 ]]; then
        # API scenario: should describe Flask routes
        if echo "$RESPONSE" | grep -qiE "@app\.route|@app\.get|def.*route|/hello|/health"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Response missing Flask routes for API scenario" >&2
        fi
    else
        # Library scenario: should describe is_valid_email function
        if echo "$RESPONSE" | grep -qiE "def is_valid_email|is_valid_email.*bool"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Response missing is_valid_email function" >&2
        fi
    fi

    # Check 5: Response mentions test file / tests directory
    if echo "$RESPONSE" | grep -qiE "test.*\.py|tests/|def test_"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Response does not mention tests" >&2
    fi

    # Check 6: Response mentions running/verifying tests (passed/failed output)
    if echo "$RESPONSE" | grep -qiE "passed|failed|error.*test|test.*ok|pytest"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Response does not mention running or verifying tests" >&2
    fi

fi

# Pass threshold: 4/6 checks
if [[ $PASSED -ge 4 ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
