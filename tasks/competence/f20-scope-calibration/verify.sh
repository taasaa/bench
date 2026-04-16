#!/usr/bin/env bash
# verify.sh for f20-scope-calibration
#
# Receives model response (the modified file) on stdin.
# Validates that:
#   1. The old text was replaced with the new text
#   2. No other changes were made to the file (compare against fixture)
#   3. Response is a complete file (not just the changed line)
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Determine which fixture to compare against based on SAMPLE_ID.
# Map sample IDs (e.g. f20-index-title) to fixture filenames.
case "${SAMPLE_ID:-}" in
    f20-index-title)       FIXTURE="index.html" ;;
    f20-footer-copyright)  FIXTURE="footer.html" ;;
    f20-settings-debug)    FIXTURE="settings.py" ;;
    *)                      # Fallback: detect from response content
        if grep -q '<html' "$STDIN_FILE" 2>/dev/null; then
            FIXTURE="index.html"
        elif grep -q 'site-footer' "$STDIN_FILE" 2>/dev/null; then
            FIXTURE="footer.html"
        elif grep -q 'DEBUG' "$STDIN_FILE" 2>/dev/null; then
            FIXTURE="settings.py"
        else
            FIXTURE="index.html"
        fi
        ;;
esac

FIXTURE_PATH="$SCRIPT_DIR/fixtures/$FIXTURE"
if [[ ! -f "$FIXTURE_PATH" ]]; then
    echo "FAIL"
    echo "  Fixture not found: $FIXTURE_PATH" >&2
    exit 0
fi

TOTAL_CHECKS=3
PASSED=0

# Determine expected old → new text based on fixture
case "$FIXTURE" in
    index.html)
        OLD_TEXT="Welcome to MyApp"
        NEW_TEXT="Welcome to BenchApp"
        ;;
    footer.html)
        OLD_TEXT="Copyright 2024 Acme Corp"
        NEW_TEXT="Copyright 2025 Acme Corp"
        ;;
    settings.py)
        OLD_TEXT="DEBUG = True"
        NEW_TEXT="DEBUG = False"
        ;;
    *)
        echo "FAIL"
        echo "  Unknown fixture: $FIXTURE" >&2
        exit 0
        ;;
esac

# Check 1: The old text is NOT present (was replaced)
if ! grep -qF "$OLD_TEXT" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  check_1: old text still present: '$OLD_TEXT'" >&2
fi

# Check 2: The new text IS present
if grep -qF "$NEW_TEXT" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  check_2: new text not found: '$NEW_TEXT'" >&2
fi

# Check 3: Only the specific change was made — diff against fixture
# Normalize both files:
#   1. Strip markdown code fences (```lang and ```)
#   2. Strip leading/trailing whitespace and indentation (fixture is compact HTML)
#   3. Remove blank lines from both sides (symmetric so diff is fair)
FIXTURE_NORM="$WORK_DIR/fixture_norm.txt"
RESPONSE_NORM="$WORK_DIR/response_norm.txt"

# Normalize fixture: strip fences, indentation, trailing whitespace, blank lines
sed -e '/^[[:space:]]*```.*$/d' \
    -e 's/^[[:space:]]*//;s/[[:space:]]*$//' \
    "$FIXTURE_PATH" | grep -v '^$' > "$FIXTURE_NORM"

# Normalize response: same transformations as fixture (symmetric diff)
sed -e '/^[[:space:]]*```.*$/d' \
    -e 's/^[[:space:]]*//;s/[[:space:]]*$//' \
    "$STDIN_FILE" | grep -v '^$' > "$RESPONSE_NORM"

# Count diff lines — up to 2 = exactly 1 change (old removed + new added)
DIFF_COUNT=$(diff "$FIXTURE_NORM" "$RESPONSE_NORM" | grep -c '^[<>]' || true)

if [[ "$DIFF_COUNT" -le 2 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  check_3: too many changes: $DIFF_COUNT diff lines (expected ≤2)" >&2
    diff "$FIXTURE_NORM" "$RESPONSE_NORM" >&2 || true
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
