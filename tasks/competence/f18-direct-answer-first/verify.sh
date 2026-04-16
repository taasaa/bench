#!/usr/bin/env bash
# verify.sh for f18-direct-answer-first
#
# Receives model response on stdin.
# Checks:
#   1. First non-blank sentence contains the expected port number
#   2. Total response is under 50 words
#   3. Port number appears near the start of the response
#
# Uses SAMPLE_ID to determine expected port.
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

# Strip leading/trailing whitespace for all checks
# (models often output leading newlines or extra whitespace)
STRIPPED_FILE="$WORK_DIR/stripped.txt"
sed 's/^[[:space:]]*//;s/[[:space:]]*$//' "$STDIN_FILE" > "$STRIPPED_FILE"

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

# Check 1: First non-blank line contains the expected port number
# (strip blank lines first, then take first line)
FIRST_LINE=$(sed '/^[[:space:]]*$/d' "$STRIPPED_FILE" | head -1)
if echo "$FIRST_LINE" | grep -qF "$EXPECTED_PORT"; then
    PASSED=$((PASSED + 1))
else
    echo "  check_1: failed — first line does not contain $EXPECTED_PORT" >&2
    echo "  first line: ${FIRST_LINE:0:200}" >&2
fi

# Check 2: Total response is under 50 words
WORD_COUNT=$(wc -w < "$STRIPPED_FILE" | tr -d ' ')
if [[ "$WORD_COUNT" -le 50 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  check_2: failed — response has $WORD_COUNT words (max 50)" >&2
fi

# Check 3: Port number appears near the start of the stripped response
# (byte position < 80 in whitespace-stripped content)
PORT_POS=$(grep -bo "$EXPECTED_PORT" "$STRIPPED_FILE" | head -1 | cut -d: -f1)
if [[ -n "$PORT_POS" ]] && [[ "$PORT_POS" -lt 80 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  check_3: failed — port number not near start (pos=${PORT_POS:-not found})" >&2
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
