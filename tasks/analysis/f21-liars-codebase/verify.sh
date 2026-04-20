#!/usr/bin/env bash
# verify.sh for f21-liars-codebase
#
# Receives model response on stdin.
# Checks:
#   1. Response states FALSE (or equivalent — the claim is always false)
#   2. Response lists at least 3 specific discrepancies
#   3. Response references actual code (not just documentation)
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

TOTAL_CHECKS=3
PASSED=0

# Check 1: States the claim is FALSE or incorrect
if grep -qiE '(FALSE|not true|incorrect|claim.*false|disagree|wrong|does not|doesn.t)' "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Does not state the claim is FALSE" >&2
fi

# Check 2: Lists at least 3 specific discrepancies
# Count numbered items, bullet points, or discrepancy markers
DISCREPANCY_COUNT=$(grep -cE '(^\s*[\d]+\.\s|^\s*[-*]\s|discrepancy|mismatch|contradict|false claim|wrong:)' "$STDIN_FILE" || true)
if [[ "$DISCREPANCY_COUNT" -ge 3 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Lists fewer than 3 discrepancies (found $DISCREPANCY_COUNT)" >&2
fi

# Check 3: References actual code behavior (not just docs)
if grep -qiE '(code.*does|actually uses|actually implements|real behavior|implementation|source|import|def |class )' "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Does not reference actual code behavior" >&2
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
