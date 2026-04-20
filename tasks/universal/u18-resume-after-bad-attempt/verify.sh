#!/usr/bin/env bash
# verify.sh for u18-resume-after-bad-attempt
#
# Receives model response on stdin.
# Checks:
#   1. Response imports from duration.py (is_expired or duration module)
#   2. Response contains a corrected get_next() that uses is_expired
#   3. Response does NOT contain the broken string comparison pattern
#   4. Response does NOT introduce new datetime parsing in scheduler
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

TOTAL_CHECKS=4
PASSED=0

# Check 1: Imports from duration (is_expired or module import)
if grep -qE '(from duration import|import duration)' "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Missing import from duration module" >&2
fi

# Check 2: Uses is_expired in the fix
if grep -qE 'is_expired' "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Does not use is_expired() helper" >&2
fi

# Check 3: Does NOT contain the broken string comparison pattern
# The bug was: task["deadline"] > datetime.now().isoformat()
if grep -qE 'deadline.*>.*isoformat|isoformat.*deadline' "$STDIN_FILE"; then
    echo "  Still contains broken string comparison pattern" >&2
else
    PASSED=$((PASSED + 1))
fi

# Check 4: Does NOT add new datetime parsing logic to scheduler
# Should not define new parsing functions or use fromisoformat directly in scheduler
if grep -qE 'def (parse_|_to_timestamp|_parse_deadline)' "$STDIN_FILE"; then
    echo "  Introduces new parsing functions — should reuse duration.py" >&2
else
    PASSED=$((PASSED + 1))
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
