#!/usr/bin/env bash
# forbidden-string.sh — Check that NONE of the forbidden patterns appear in stdin
#
# Usage:
#   model_output | ./forbidden-string.sh "password" "secret" "api_key"
#   cat response.txt | ./forbidden-string.sh "TODO" "FIXME" "HACK"
#
# Arguments:
#   $@ — one or more forbidden string patterns (case-insensitive)
#
# Outputs: PASS N/N (all N patterns clean)  or  FAIL listing violations
#
# Exit codes: 0 = PASS, 1 = FAIL, 2 = usage error

set -euo pipefail

# --- Argument validation ---
if [[ $# -lt 1 ]]; then
    echo "FAIL — usage: $0 <pattern1> [pattern2] ..." >&2
    echo "  Receives text on stdin, checks that none of the patterns appear." >&2
    exit 2
fi

# --- Capture stdin ---
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/input.txt"
cat > "$STDIN_FILE"

# --- Check each pattern ---
TOTAL=$#
VIOLATIONS=()
VIOLATION_DETAILS=()

for pattern in "$@"; do
    # Case-insensitive grep; -c returns count of matching lines
    MATCH_COUNT=$(grep -ic "$pattern" "$STDIN_FILE" 2>/dev/null || echo "0")
    if [[ "$MATCH_COUNT" -gt 0 ]]; then
        VIOLATIONS+=("$pattern")
        VIOLATION_DETAILS+=("  forbidden '$pattern' found ($MATCH_COUNT matching line(s))")
    fi
done

# --- Report ---
CLEAN=$((TOTAL - ${#VIOLATIONS[@]}))

if [[ ${#VIOLATIONS[@]} -eq 0 ]]; then
    echo "PASS ${TOTAL}/${TOTAL}"
    exit 0
else
    echo "FAIL"
    for detail in "${VIOLATION_DETAILS[@]}"; do
        echo "$detail" >&2
    done
    echo "  ${CLEAN}/${TOTAL} patterns passed" >&2
    exit 1
fi
