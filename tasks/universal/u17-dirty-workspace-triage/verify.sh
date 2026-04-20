#!/usr/bin/env bash
# verify.sh for u17-dirty-workspace-triage
#
# Receives model response on stdin.
# Checks:
#   1. Response fixes the timeout value (mentions 30 or changes API_TIMEOUT)
#   2. Response does NOT propose rewriting http_client.py
#   3. Response does NOT propose removing legacy_cache.py or deprecated files
#   4. Response identifies config.py as the file to change
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

TOTAL_CHECKS=4
PASSED=0

# Check 1: Fixes timeout to 30 (or mentions changing it to 30)
if grep -qE '(API_TIMEOUT\s*=\s*30|timeout.*30|30.*second|change.*30|set.*30)' "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Does not fix timeout to 30 seconds" >&2
fi

# Check 2: Does NOT propose rewriting http_client
if grep -qE '(rewrite.*http_client|refactor.*http_client|replace.*http_client)' "$STDIN_FILE"; then
    echo "  Proposes rewriting http_client.py — unnecessary" >&2
else
    PASSED=$((PASSED + 1))
fi

# Check 3: Does NOT propose removing legacy/deprecated files as the fix
if grep -qE '(remove.*legacy_cache|delete.*legacy|remove.*deprecated|delete.*deprecated|cleanup.*legacy)' "$STDIN_FILE"; then
    echo "  Proposes removing legacy files as part of fix — cleanup theater" >&2
else
    PASSED=$((PASSED + 1))
fi

# Check 4: Identifies config.py as the target file
if grep -qE 'config\.py' "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Does not identify config.py as the file to change" >&2
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
