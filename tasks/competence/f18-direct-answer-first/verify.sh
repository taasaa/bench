#!/usr/bin/env bash
# verify.sh for f18-direct-answer-first
#
# Receives model response on stdin.
# Checks:
#   1. First sentence contains the expected port number
#   2. Total response is under 50 words
#   3. Port number appears before any context/explanation sentence
#
# Uses SAMPLE_ID to determine expected port.
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

# Determine expected port based on sample ID
case "${SAMPLE_ID:-}" in
    f18-postgres-port) EXPECTED_PORT="5432" ;;
    f18-redis-port)    EXPECTED_PORT="6379" ;;
    f18-mysql-port)    EXPECTED_PORT="3306" ;;
    f18-mongodb-port)  EXPECTED_PORT="27017" ;;
    *)                 EXPECTED_PORT="5432" ;;
esac

TOTAL_CHECKS=3
PASSED=0

# Check 1: First sentence contains the expected port number
FIRST_SENTENCE=$(head -1 "$STDIN_FILE" | sed 's/[.!?].*//' | head -c 500)
if echo "$FIRST_SENTENCE" | grep -qF "$EXPECTED_PORT"; then
    PASSED=$((PASSED + 1))
else
    echo "  check_1: failed — first sentence does not contain $EXPECTED_PORT" >&2
    echo "  first line: $(head -1 "$STDIN_FILE" | head -c 200)" >&2
fi

# Check 2: Total response is under 50 words
WORD_COUNT=$(wc -w < "$STDIN_FILE" | tr -d ' ')
if [[ "$WORD_COUNT" -le 50 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  check_2: failed — response has $WORD_COUNT words (max 50)" >&2
fi

# Check 3: Port number appears before any explanatory/contextual content
# Extract position of port number and position of common explanation markers
PORT_POS=$(grep -bo "$EXPECTED_PORT" "$STDIN_FILE" | head -1 | cut -d: -f1)
if [[ -n "$PORT_POS" ]] && [[ "$PORT_POS" -lt 30 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  check_3: failed — port number not found near start of response" >&2
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
