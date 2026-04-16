#!/usr/bin/env bash
# verify.sh for f17-config-migration (agent-mode task)
# Agent migrates python-dotenv project to pydantic-settings

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

cat > "$WORK_DIR/response.txt"
RESPONSE=$(cat "$WORK_DIR/response.txt")

TOTAL_CHECKS=5
PASSED=0

# Detect project directory
if [ -d "/tmp/migration_proj" ]; then
    PROJ_DIR="/tmp/migration_proj"
elif [ -d "/tmp/multifile_proj" ]; then
    PROJ_DIR="/tmp/multifile_proj"
else
    PROJ_DIR=""
fi

# Check 1: No os.environ.get remaining
if [ -n "$PROJ_DIR" ]; then
    OS_ENV_COUNT=$(grep -r "os.environ" "$PROJ_DIR" --include="*.py" 2>/dev/null | grep -v "import" | wc -l || echo "0")
    if [[ "$OS_ENV_COUNT" -eq 0 ]]; then
        PASSED=$((PASSED + 1))
    else
        echo "  os.environ.get still present in $OS_ENV_COUNT places" >&2
    fi
else
    # Fall back to response-based check
    if ! echo "$RESPONSE" | grep -qi "os.environ"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Response mentions os.environ (may still be in code)" >&2
    fi
fi

# Check 2: No python-dotenv imports
if [ -n "$PROJ_DIR" ]; then
    DOTENV_COUNT=$(grep -r "python-dotenv\|dotenv" "$PROJ_DIR" --include="*.py" 2>/dev/null | wc -l || echo "0")
    if [[ "$DOTENV_COUNT" -eq 0 ]]; then
        PASSED=$((PASSED + 1))
    else
        echo "  python-dotenv references still present" >&2
    fi
else
    if ! echo "$RESPONSE" | grep -qi "python-dotenv\|dotenv"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Response mentions python-dotenv" >&2
    fi
fi

# Check 3: Settings class exists (mentioned in response or in code)
if echo "$RESPONSE" | grep -qiE "class.*Settings|Settings.*pydantic|pydantic.*Settings"; then
    PASSED=$((PASSED + 1))
else
    echo "  No Settings class found" >&2
fi

# Check 4: Agent describes the migration
if echo "$RESPONSE" | grep -qiE "migrated|changed|replaced|updated|removed"; then
    PASSED=$((PASSED + 1))
else
    echo "  Agent did not describe migration changes" >&2
fi

# Check 5: No behavior change (agent says business logic unchanged)
if echo "$RESPONSE" | grep -qiE "business logic|behavior unchanged|no change|API.*behavior|same.*behavior"; then
    PASSED=$((PASSED + 1))
else
    echo "  Agent did not verify behavior preservation" >&2
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi