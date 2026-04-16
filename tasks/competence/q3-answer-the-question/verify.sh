#!/usr/bin/env bash
# verify.sh for q3-answer-the-question
#
# Checks that model response:
#   1. Contains the correct command (uv venv / pip venv / etc.)
#   2. Is under 200 words total
#   3. Does NOT contain explanation phrases

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

TOTAL_CHECKS=4
PASSED=0

RESPONSE=$(cat "$STDIN_FILE")

# Determine which scenario based on SAMPLE_ID or content
if echo "$RESPONSE" | grep -qi "uv"; then
    COMMAND_PATTERN="uv.*venv"
elif echo "$RESPONSE" | grep -qi "python.*venv\|py.*m.*venv\|venv"; then
    COMMAND_PATTERN="python.*-m.*venv|uv.*venv"
elif echo "$RESPONSE" | grep -qi "npm.*init"; then
    COMMAND_PATTERN="npm.*init"
elif echo "$RESPONSE" | grep -qi "cargo.*init"; then
    COMMAND_PATTERN="cargo.*init"
else
    # Generic: look for any venv/create pattern
    COMMAND_PATTERN=".*"
fi

# Check 1: Contains the correct command keyword
# Look for the actual command in the response
HAS_CMD=0
if echo "$RESPONSE" | grep -qiE "uv.*venv"; then
    HAS_CMD=1
elif echo "$RESPONSE" | grep -qiE "python.*-m.*venv"; then
    HAS_CMD=1
elif echo "$RESPONSE" | grep -qiE "npm.*init"; then
    HAS_CMD=1
elif echo "$RESPONSE" | grep -qiE "cargo.*init"; then
    HAS_CMD=1
fi

if [[ $HAS_CMD -eq 1 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Response does not contain expected command" >&2
fi

# Check 2: Is under 200 words
WORD_COUNT=$(echo "$RESPONSE" | wc -w)
if [[ $WORD_COUNT -lt 200 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Response has $WORD_COUNT words (must be < 200)" >&2
fi

# Check 3: Does NOT contain "virtual environment is"
if ! echo "$RESPONSE" | grep -qiE "virtual environment is|virtual environments are|what a virtual"; then
    PASSED=$((PASSED + 1))
else
    echo "  Response explains what virtual environments are (not requested)" >&2
fi

# Check 4: Does NOT contain "why you should" or "alternatives"
if ! echo "$RESPONSE" | grep -qiE "why you should|alternatives include|you might also|you could also"; then
    PASSED=$((PASSED + 1))
else
    echo "  Response mentions alternatives or 'why' (not requested)" >&2
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi