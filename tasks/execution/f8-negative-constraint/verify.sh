#!/usr/bin/env bash
# verify.sh for f8-negative-constraint
#
# Receives model response on stdin (Python code implementing a function).
# Checks:
#   1. Uses the requests library (import requests)
#   2. Raises ValueError for non-positive ID input
#   3. Raises ConnectionError on network failure
#   4. Does NOT contain forbidden patterns (retry, cache, logging, time.sleep, ratelimit, backoff, tenacity)
#
# Environment:
#   SAMPLE_ID - identifies which sample (determines function name)
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

TOTAL_CHECKS=4
PASSED=0

# Map SAMPLE_ID to expected function name
SAMPLE="${SAMPLE_ID:-f8-fetch-user}"
case "$SAMPLE" in
    f8-fetch-user)
        FUNC_NAME="fetch_user"
        PARAM_NAME="user_id"
        ;;
    f8-fetch-product)
        FUNC_NAME="fetch_product"
        PARAM_NAME="product_id"
        ;;
    f8-fetch-order)
        FUNC_NAME="fetch_order"
        PARAM_NAME="order_id"
        ;;
    f8-fetch-article)
        FUNC_NAME="fetch_article"
        PARAM_NAME="article_id"
        ;;
    *)
        FUNC_NAME="fetch_user"
        PARAM_NAME="user_id"
        ;;
esac

# Check 1: Uses requests library
if grep -qE "import[[:space:]]+requests" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  'import requests' not found" >&2
fi

# Check 2: Raises ValueError for non-positive ID
if grep -qE "raise[[:space:]]+ValueError" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  ValueError not raised for invalid input" >&2
fi

# Check 3: Raises ConnectionError on network failure
if grep -qE "raise[[:space:]]+ConnectionError|raise[[:space:]]+requests\.exceptions\.|except[[:space:]]+requests" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  No ConnectionError handling for network failures" >&2
fi

# Check 4: Does NOT contain forbidden patterns
# Forbidden: retry, cache, logging, time.sleep, ratelimit, backoff, tenacity
FORBIDDEN_FOUND=$(grep -cEi "retry|cache|logging|time\.sleep|ratelimit|backoff|tenacity" "$STDIN_FILE" || true)

if [[ "$FORBIDDEN_FOUND" -eq 0 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Found forbidden patterns (retry, cache, logging, time.sleep, ratelimit, backoff, tenacity):" >&2
    grep -Ein "retry|cache|logging|time\.sleep|ratelimit|backoff|tenacity" "$STDIN_FILE" >&2 || true
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
