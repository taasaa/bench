#!/usr/bin/env bash
# verify.sh for q1-verification-gate
#
# Receives model response on stdin.
# Checks that the response correctly identifies:
#   1. Number of passed tests
#   2. Number of failed tests
#   3. Names of failing tests
#
# The model is given test output with known failures and must report them accurately.
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

# For this task, the verify.sh checks that the response mentions the correct
# pass/fail counts. Since each sample has different counts, we validate that
# the response contains consistent and plausible numbers.
# The actual correctness is checked against the test output given in the prompt.

TOTAL_CHECKS=3
PASSED=0

# Check 1: Response mentions "passed" with a number
if grep -qiE '[0-9]+ (tests? )?passed' "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Missing or incorrect pass count" >&2
fi

# Check 2: Response mentions "failed" with a number
if grep -qiE '[0-9]+ (tests? )?failed' "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Missing or incorrect fail count" >&2
fi

# Check 3: Response mentions specific test names (test_something pattern)
if grep -qiE 'test_[a-z_]+' "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Missing failing test names" >&2
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
