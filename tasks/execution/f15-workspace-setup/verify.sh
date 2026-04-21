#!/usr/bin/env bash
# verify.sh for f15-workspace-setup
# Dual-mode: agent creates real files OR model outputs a project plan as text.
# Detects mode by checking whether the expected directory exists.

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

cat > "$WORK_DIR/response.txt"
RESPONSE=$(cat "$WORK_DIR/response.txt")

TOTAL_CHECKS=6
PASSED=0

# Scenario detection from response content
if echo "$RESPONSE" | grep -qi "cross.import\|is_email_valid\|validators\.py\|Contact\|validlib"; then
    SCENARIO="cross-imports"
    PROJECT_DIR="/tmp/validlib"
elif echo "$RESPONSE" | grep -qi "partial\|partialproj\|existing.*file\|greet\|helpers\.py"; then
    SCENARIO="partial-scaffold"
    PROJECT_DIR="/tmp/partialproj"
elif echo "$RESPONSE" | grep -qi "pyproject\|mathkit\|src.*layout\|installable"; then
    SCENARIO="pyproject-package"
    PROJECT_DIR="/tmp/mathkit"
elif echo "$RESPONSE" | grep -qi "api\|flask\|route\|app\.py"; then
    SCENARIO="api"
    PROJECT_DIR="/tmp/api_service"
else
    SCENARIO="basic"
    PROJECT_DIR="/tmp/myproject"
fi

# ──────────────────────────────────────────────────────────────────────────────
# AGENT MODE: real files were created
# ──────────────────────────────────────────────────────────────────────────────
if [ -d "$PROJECT_DIR" ]; then

    # Check 1: Project directory exists
    PASSED=$((PASSED + 1))

    case "$SCENARIO" in
        basic)
            # Check 2: __init__.py with version
            if [ -f "$PROJECT_DIR/__init__.py" ] && grep -q '__version__.*=.*"1\.0\.0"' "$PROJECT_DIR/__init__.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  __version__ not '1.0.0' in __init__.py" >&2
            fi
            # Check 3: models.py with User dataclass
            if [ -f "$PROJECT_DIR/models.py" ] && grep -qE "class User" "$PROJECT_DIR/models.py" \
                && grep -qE "name.*:.*str|email.*:.*str" "$PROJECT_DIR/models.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  User dataclass not found in models.py" >&2
            fi
            # Check 4: utils.py with is_valid_email
            if [ -f "$PROJECT_DIR/utils.py" ] && grep -qE "def is_valid_email" "$PROJECT_DIR/utils.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  utils.py not found or missing is_valid_email" >&2
            fi
            # Check 5: tests/
            if [ -f "$PROJECT_DIR/tests/test_utils.py" ] && grep -qE "def test_|pytest|unittest" "$PROJECT_DIR/tests/test_utils.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Test file not found or has no test functions" >&2
            fi
            ;;
        api)
            # Check 2: __init__.py with version
            if [ -f "$PROJECT_DIR/__init__.py" ] && grep -q '__version__.*=.*"2\.0\.0"' "$PROJECT_DIR/__init__.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  __version__ not '2.0.0' in __init__.py" >&2
            fi
            # Check 3: models.py with Product dataclass
            if [ -f "$PROJECT_DIR/models.py" ] && grep -qE "class Product" "$PROJECT_DIR/models.py" \
                && grep -qE "id.*:.*int|name.*:.*str|price.*:.*float" "$PROJECT_DIR/models.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Product dataclass not found in models.py" >&2
            fi
            # Check 4: app.py with Flask route
            if [ -f "$PROJECT_DIR/app.py" ] && grep -qE "@app\.route|@app\.get|def.*route|/hello|/health" "$PROJECT_DIR/app.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  app.py not found or missing Flask routes" >&2
            fi
            # Check 5: tests/
            if [ -f "$PROJECT_DIR/tests/test_app.py" ] && grep -qE "def test_|pytest|unittest" "$PROJECT_DIR/tests/test_app.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Test file not found or has no test functions" >&2
            fi
            ;;
        cross-imports)
            # Check 2: __init__.py with version
            if [ -f "$PROJECT_DIR/__init__.py" ] && grep -q '__version__.*=.*"3\.0\.0"' "$PROJECT_DIR/__init__.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  __version__ not '3.0.0' in __init__.py" >&2
            fi
            # Check 3: models.py with Contact dataclass AND is_email_valid that imports validators
            if [ -f "$PROJECT_DIR/models.py" ] && grep -qE "class Contact" "$PROJECT_DIR/models.py" \
                && grep -qE "def is_email_valid" "$PROJECT_DIR/models.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Contact dataclass with is_email_valid method not found" >&2
            fi
            # Check 4: validators.py with is_valid_email function
            if [ -f "$PROJECT_DIR/validators.py" ] && grep -qE "def is_valid_email" "$PROJECT_DIR/validators.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  validators.py not found or missing is_valid_email" >&2
            fi
            # Check 5: tests/ with test_contact.py
            if [ -f "$PROJECT_DIR/tests/test_contact.py" ] && grep -qE "def test_" "$PROJECT_DIR/tests/test_contact.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  test_contact.py not found or has no test functions" >&2
            fi
            ;;
        partial-scaffold)
            # Check 2: existing __init__.py preserved with correct version
            if [ -f "$PROJECT_DIR/__init__.py" ] && grep -q '__version__.*=.*"1\.5\.0"' "$PROJECT_DIR/__init__.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Existing __init__.py not preserved or version changed" >&2
            fi
            # Check 3: models.py added with Item dataclass
            if [ -f "$PROJECT_DIR/models.py" ] && grep -qE "class Item" "$PROJECT_DIR/models.py" \
                && grep -qE "id.*:.*int|name.*:.*str|price.*:.*float" "$PROJECT_DIR/models.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Item dataclass not found in models.py" >&2
            fi
            # Check 4: existing helpers.py preserved unchanged
            if [ -f "$PROJECT_DIR/helpers.py" ] && grep -qE "def greet" "$PROJECT_DIR/helpers.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Existing helpers.py not preserved" >&2
            fi
            # Check 5: tests/ with test_helpers.py
            if [ -f "$PROJECT_DIR/tests/test_helpers.py" ] && grep -qE "def test_" "$PROJECT_DIR/tests/test_helpers.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  test_helpers.py not found or has no test functions" >&2
            fi
            ;;
        pyproject-package)
            # Check 2: pyproject.toml exists with name and version
            if [ -f "$PROJECT_DIR/pyproject.toml" ] \
                && grep -qE 'name\s*=\s*"mathkit"' "$PROJECT_DIR/pyproject.toml" \
                && grep -qE 'version\s*=\s*"0\.1\.0"' "$PROJECT_DIR/pyproject.toml"; then
                PASSED=$((PASSED + 1))
            else
                echo "  pyproject.toml not found or missing name/version" >&2
            fi
            # Check 3: src/mathkit/__init__.py with add function and version
            if [ -f "$PROJECT_DIR/src/mathkit/__init__.py" ] \
                && grep -qE '__version__.*=.*"0\.1\.0"' "$PROJECT_DIR/src/mathkit/__init__.py" \
                && grep -qE "def add" "$PROJECT_DIR/src/mathkit/__init__.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  src/mathkit/__init__.py not found or missing add/version" >&2
            fi
            # Check 4: src/mathkit/ops.py with multiply function
            if [ -f "$PROJECT_DIR/src/mathkit/ops.py" ] && grep -qE "def multiply" "$PROJECT_DIR/src/mathkit/ops.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  src/mathkit/ops.py not found or missing multiply" >&2
            fi
            # Check 5: tests/ with test file
            if [ -f "$PROJECT_DIR/tests/test_math.py" ] && grep -qE "def test_" "$PROJECT_DIR/tests/test_math.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  test_math.py not found or has no test functions" >&2
            fi
            ;;
    esac

    # Check 6: Agent reported test output (all scenarios)
    if echo "$RESPONSE" | grep -qiE "passed|failed|error|ok"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Agent did not report test results" >&2
    fi

# ──────────────────────────────────────────────────────────────────────────────
# MODEL-EVAL MODE: response is text describing the project plan
# ──────────────────────────────────────────────────────────────────────────────
else

    case "$SCENARIO" in
        basic)
            if echo "$RESPONSE" | grep -qiE "mkdir.*$PROJECT_DIR|create.*$PROJECT_DIR|project.*$PROJECT_DIR"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response does not describe creating $PROJECT_DIR" >&2
            fi
            if echo "$RESPONSE" | grep -q '__version__.*=.*"1\.0\.0"'; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response does not include __version__ = '1.0.0'" >&2
            fi
            if echo "$RESPONSE" | grep -qE "class User" && echo "$RESPONSE" | grep -qE "name.*:.*str|email.*:.*str"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response missing User dataclass with required fields" >&2
            fi
            if echo "$RESPONSE" | grep -qiE "def is_valid_email|is_valid_email.*bool"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response missing is_valid_email function" >&2
            fi
            ;;
        api)
            if echo "$RESPONSE" | grep -qiE "mkdir.*$PROJECT_DIR|create.*$PROJECT_DIR|project.*$PROJECT_DIR"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response does not describe creating $PROJECT_DIR" >&2
            fi
            if echo "$RESPONSE" | grep -q '__version__.*=.*"2\.0\.0"'; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response does not include __version__ = '2.0.0'" >&2
            fi
            if echo "$RESPONSE" | grep -qE "class Product" && echo "$RESPONSE" | grep -qE "name.*:.*str|id.*:.*int|price.*:.*float"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response missing Product dataclass" >&2
            fi
            if echo "$RESPONSE" | grep -qiE "@app\.route|@app\.get|def.*route|/hello|/health"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response missing Flask routes" >&2
            fi
            ;;
        cross-imports)
            if echo "$RESPONSE" | grep -qiE "mkdir.*$PROJECT_DIR|create.*$PROJECT_DIR|validlib"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response does not describe creating validlib" >&2
            fi
            if echo "$RESPONSE" | grep -q '__version__.*=.*"3\.0\.0"'; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response does not include __version__ = '3.0.0'" >&2
            fi
            if echo "$RESPONSE" | grep -qE "class Contact" && echo "$RESPONSE" | grep -qE "is_email_valid|from.*validators.*import"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response missing Contact with cross-module import" >&2
            fi
            if echo "$RESPONSE" | grep -qiE "def is_valid_email|validators\.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response missing validators.py / is_valid_email" >&2
            fi
            ;;
        partial-scaffold)
            if echo "$RESPONSE" | grep -qiE "partialproj|existing|partial"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response does not reference the partial project" >&2
            fi
            if echo "$RESPONSE" | grep -qE "class Item" && echo "$RESPONSE" | grep -qE "id.*:.*int|price.*:.*float"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response missing Item dataclass" >&2
            fi
            if echo "$RESPONSE" | grep -qiE "greet|helpers\.py" && ! echo "$RESPONSE" | grep -qiE "delete|remove.*helpers|recreate.*helpers|overwrite"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response doesn't preserve existing helpers or mentions deleting it" >&2
            fi
            if echo "$RESPONSE" | grep -qiE "test_helpers|greet.*World|assert.*Hello"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response missing test for helpers" >&2
            fi
            ;;
        pyproject-package)
            if echo "$RESPONSE" | grep -qiE "mathkit|pyproject\.toml"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response does not reference mathkit or pyproject.toml" >&2
            fi
            if echo "$RESPONSE" | grep -qE 'name.*=.*"mathkit"' && echo "$RESPONSE" | grep -qE 'version.*=.*"0\.1\.0"'; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response missing pyproject.toml name/version" >&2
            fi
            if echo "$RESPONSE" | grep -qiE "src.*mathkit|src/mathkit" && echo "$RESPONSE" | grep -qiE "def add"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response missing src layout or add function" >&2
            fi
            if echo "$RESPONSE" | grep -qiE "def multiply|ops\.py"; then
                PASSED=$((PASSED + 1))
            else
                echo "  Response missing ops.py or multiply function" >&2
            fi
            ;;
    esac

    # Check 5: Response mentions test file / tests directory (all scenarios)
    if echo "$RESPONSE" | grep -qiE "test.*\.py|tests/|def test_"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Response does not mention tests" >&2
    fi

    # Check 6: Response mentions running/verifying tests (all scenarios)
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
