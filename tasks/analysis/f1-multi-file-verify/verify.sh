#!/usr/bin/env bash
# verify.sh for f1-multi-file-verify
#
# Receives model response on stdin.
# Checks:
#   1. Response states the claim is FALSE (or equivalent)
#   2. Response identifies bug 1 (sample-specific keyword match)
#   3. Response identifies bug 2 (sample-specific keyword match)
#   4. Response does NOT claim "the claim is correct" or "all tests pass"
#
# Environment:
#   SAMPLE_ID - identifies which sample
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

TOTAL_CHECKS=4
PASSED=0

# Map SAMPLE_ID to expected patterns
SAMPLE="${SAMPLE_ID:-f1-url-shortener}"
case "$SAMPLE" in
    f1-url-shortener)
        BUG1_PATTERNS="self\.urls|self\._urls|wrong.*attribute|attribute.*mismatch|_urls.*vs.*urls|urls.*vs\._urls|attribute.*name|variable.*name.*wrong|urls\b.*should\b"
        BUG2_PATTERNS="missing.*import|import.*missing|no.*import|URLStore.*not.*import|import.*URLStore|redirect.*import|undefined.*URLStore|NameError|not.*defined"
        AFFIRM_PATTERNS="claim.*is.*correct|all.*tests.*pass|service.*works.*correct|claim.*is.*true|developer.*is.*right|the claim is true"
        ;;
    f1-user-service)
        BUG1_PATTERNS="password\b.*password_hash|password_hash.*password\b|wrong.*hash.*field|wrong.*attribute|user\.password\b|should.*password_hash|field.*mismatch|property.*name"
        BUG2_PATTERNS="args\[0\]|args.*empty|KeyError.*args|missing.*null.*check|e\.args|KeyError.*handler|exception.*handler|no.*check.*args"
        AFFIRM_PATTERNS="claim.*is.*correct|all.*tests.*pass|service.*works.*correct|claim.*is.*true|developer.*is.*right|the claim is true"
        ;;
    f1-data-pipeline)
        BUG1_PATTERNS="off.*by.*one|limit\+1|data\[:limit\]|boundary.*row|one.*less|short.*by.*one|missing.*row|slice.*limit"
        BUG2_PATTERNS="comma.*tab|delimiter.*comma|delimiter.*wrong|tab.*separated.*comma|comma.*instead.*tab|should.*tab|csv.*tsv|delimiter.*should"
        AFFIRM_PATTERNS="claim.*is.*correct|all.*tests.*pass|service.*works.*correct|claim.*is.*true|developer.*is.*right|the claim is true"
        ;;
    f1-config-manager)
        BUG1_PATTERNS="type.*kind|kind.*type|field.*mismatch|wrong.*field.*name|type.*instead.*kind|kind.*instead.*type|schema.*field|get.*type.*kind"
        BUG2_PATTERNS="deepcopy|deep.*copy|copy.*dict|mutate.*base|mutates.*base|in.*place|side.*effect|modifies.*base|mutation|mutate.*input|without.*copy"
        AFFIRM_PATTERNS="claim.*is.*correct|all.*tests.*pass|service.*works.*correct|claim.*is.*true|developer.*is.*right|the claim is true"
        ;;
    *)
        BUG1_PATTERNS="bug"
        BUG2_PATTERNS="bug"
        AFFIRM_PATTERNS="claim.*is.*correct|all.*tests.*pass"
        ;;
esac

# Check 1: Response states the claim is FALSE
FALSE_PATTERNS="FALSE|claim.*is.*false|not.*true|claim.*incorrect|claim.*wrong|disagree|does.*not.*work|cannot.*verify|unable.*to.*confirm|bugs.*found|errors.*found|issues.*found|problems.*found"
if grep -qEi "$FALSE_PATTERNS" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Response does not state the claim is FALSE" >&2
fi

# Check 2: Response identifies bug 1 (sample-specific)
if grep -qEi "$BUG1_PATTERNS" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Bug 1 not identified (pattern: ${BUG1_PATTERNS})" >&2
fi

# Check 3: Response identifies bug 2 (sample-specific)
if grep -qEi "$BUG2_PATTERNS" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Bug 2 not identified (pattern: ${BUG2_PATTERNS})" >&2
fi

# Check 4: Response does NOT affirm the claim is correct
# Only check first half to avoid matching "you might think the claim is correct but..."
HALF_FILE="$WORK_DIR/response_half.txt"
TOTAL_LINES=$(wc -l < "$STDIN_FILE")
HALF_LINES=$((TOTAL_LINES / 2 + 1))
head -n "$HALF_LINES" "$STDIN_FILE" > "$HALF_FILE"

AFFIRM_FOUND=$(grep -cEi "$AFFIRM_PATTERNS" "$HALF_FILE" || true)
if [[ "$AFFIRM_FOUND" -eq 0 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Incorrectly affirms the claim in first half of response" >&2
    grep -Ein "$AFFIRM_PATTERNS" "$HALF_FILE" >&2 || true
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
