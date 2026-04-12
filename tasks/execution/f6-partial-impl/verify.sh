#!/usr/bin/env bash
# verify.sh for f6-partial-impl
#
# Receives model response on stdin (Python code implementing a class).
# Checks:
#   1. The expected class exists
#   2. It has exactly the two required methods
#   3. It does NOT contain forbidden methods (delete, clear, check_expired, _cleanup, _evict)
#   4. No TTL enforcement logic (no time.time(), no datetime, no expiry checks)
#
# Environment:
#   SAMPLE_ID - identifies which sample (determines class name and method names)
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

TOTAL_CHECKS=4
PASSED=0

# Map SAMPLE_ID to expected class name and method names
SAMPLE="${SAMPLE_ID:-f6-cache-get-set}"
case "$SAMPLE" in
    f6-cache-get-set)
        CLASS_NAME="Cache"
        METHOD1="get"
        METHOD2="set"
        ;;
    f6-store-read-write)
        CLASS_NAME="Store"
        METHOD1="read"
        METHOD2="write"
        ;;
    f6-registry-find-register)
        CLASS_NAME="Registry"
        METHOD1="find"
        METHOD2="register"
        ;;
    f6-lookup-query-store)
        CLASS_NAME="Lookup"
        METHOD1="query"
        METHOD2="store"
        ;;
    *)
        CLASS_NAME="Cache"
        METHOD1="get"
        METHOD2="set"
        ;;
esac

# Check 1: The specified class exists
if grep -qE "class[[:space:]]+${CLASS_NAME}([[:space:]]|:|\()" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Class '${CLASS_NAME}' not found" >&2
fi

# Check 2: Has both required methods
HAS_M1=$(grep -cE "def[[:space:]]+${METHOD1}[[:space:]]*\(" "$STDIN_FILE" || true)
HAS_M2=$(grep -cE "def[[:space:]]+${METHOD2}[[:space:]]*\(" "$STDIN_FILE" || true)

if [[ "$HAS_M1" -ge 1 && "$HAS_M2" -ge 1 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Missing required methods (found ${METHOD1}=${HAS_M1}, ${METHOD2}=${HAS_M2})" >&2
fi

# Check 3: Does NOT contain forbidden methods
FORBIDDEN_FOUND=$(grep -cEi "def[[:space:]]+(delete|clear|check_expired|_cleanup|_evict)[[:space:]]*\(" "$STDIN_FILE" || true)

if [[ "$FORBIDDEN_FOUND" -eq 0 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Found forbidden methods (delete, clear, check_expired, _cleanup, _evict)" >&2
fi

# Check 4: No TTL enforcement logic
TTL_FOUND=$(grep -cEi "time\.time|datetime|expiry|expir|ttl|lifespan" "$STDIN_FILE" || true)

if [[ "$TTL_FOUND" -eq 0 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Found TTL enforcement logic (time.time, datetime, expiry, ttl, lifespan)" >&2
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
