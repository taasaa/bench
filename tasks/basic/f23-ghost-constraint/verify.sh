#!/usr/bin/env bash
# verify.sh for f23-ghost-constraint
#
# Receives model response on stdin.
# NOT sample-aware — same constraints for all samples.
# Checks:
#   1. Response contains code for at least 3 functions (def or async def)
#   2. All function names use snake_case (no camelCase like getUser)
#   3. All function definitions include type hints
#   4. Code uses httpx (NOT requests)
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

TOTAL_CHECKS=4
PASSED=0

# Check 1: Response defines at least 3 functions
FUNC_COUNT=$(grep -cE '^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+' "$STDIN_FILE" || true)
if [[ "$FUNC_COUNT" -ge 3 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Found only $FUNC_COUNT function definitions (need >= 3)" >&2
fi

# Check 2: No camelCase function names
# Extract all function names and check none use camelCase
# A camelCase identifier has a lowercase letter followed by an uppercase letter
FUNC_NAMES=$(grep -oE '(async[[:space:]]+)?def[[:space:]]+[a-zA-Z_][a-zA-Z0-9_]*' "$STDIN_FILE" | sed 's/.*def[[:space:]]*//' || true)
CAMEL_FOUND=""
if [[ -n "$FUNC_NAMES" ]]; then
    while IFS= read -r fname; do
        # Skip if empty
        [[ -z "$fname" ]] && continue
        # Check for camelCase: lowercase letter immediately followed by uppercase
        if echo "$fname" | grep -qE '[a-z][A-Z]'; then
            CAMEL_FOUND="$CAMEL_FOUND $fname"
        fi
    done <<< "$FUNC_NAMES"
fi

if [[ -z "$CAMEL_FOUND" ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  camelCase function names found:$CAMEL_FOUND" >&2
fi

# Check 3: All function definitions include type hints
# Look at each def line — should contain ': ' or ' ->' for type hints
# We check that at least one def has ' -> ' (return type hint) or param type hint
NO_HINT_FUNCS=""
if [[ -n "$FUNC_NAMES" ]]; then
    while IFS= read -r fname; do
        [[ -z "$fname" ]] && continue
        # Get the def line(s) for this function
        DEFLINE=$(grep -E "(async[[:space:]]+)?def[[:space:]]+${fname}" "$STDIN_FILE" | head -1 || true)
        if [[ -n "$DEFLINE" ]]; then
            # Must have either a return hint ( -> ) or a parameter hint (: type)
            # Exclude the trailing colon of the def statement itself
            # Check for ' -> ' (return hint) or parameter type annotation like '(param: str)'
            if ! echo "$DEFLINE" | grep -qE '(->[[:space:]]*[a-zA-Z_]|:[[:space:]]*[a-zA-Z_][a-zA-Z0-9_.]*[,\)])'; then
                NO_HINT_FUNCS="$NO_HINT_FUNCS $fname"
            fi
        fi
    done <<< "$FUNC_NAMES"
fi

if [[ -z "$NO_HINT_FUNCS" ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Functions missing type hints:$NO_HINT_FUNCS" >&2
fi

# Check 4: Code uses httpx, NOT requests
# Must mention httpx somewhere
if grep -qE 'httpx' "$STDIN_FILE"; then
    # Also verify no 'import requests' or 'from requests'
    if grep -qE '(import[[:space:]]+requests|from[[:space:]]+requests)' "$STDIN_FILE"; then
        echo "  Uses httpx but also imports requests library" >&2
    else
        PASSED=$((PASSED + 1))
    fi
else
    echo "  No httpx usage found" >&2
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
