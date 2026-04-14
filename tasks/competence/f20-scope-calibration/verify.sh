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
    f20-index-title)   FIXTURE="index.html" ;;
    f20-footer-copyright) FIXTURE="footer.html" ;;
    f20-settings-debug) FIXTURE="settings.py" ;;
    *)                 # Fallback: detect from response content
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
    echo "  Old text still present: '$OLD_TEXT'" >&2
fi

# Check 2: The new text IS present
if grep -qF "$NEW_TEXT" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  New text not found: '$NEW_TEXT'" >&2
fi

# Check 3: Only the specific change was made — diff against fixture
# Normalize both files (strip trailing whitespace and ensure trailing newline) then diff
FIXTURE_NORM="$WORK_DIR/fixture_norm.txt"
RESPONSE_NORM="$WORK_DIR/response_norm.txt"

# Strip trailing whitespace per-line, then ensure both end with exactly one newline
sed 's/[[:space:]]*$//' "$FIXTURE_PATH" | perl -pe 'chomp if eof' > "$FIXTURE_NORM"
sed 's/[[:space:]]*$//' "$STDIN_FILE" | perl -pe 'chomp if eof' > "$RESPONSE_NORM"

# Count diff lines — should be exactly 1 (the one changed line)
DIFF_COUNT=$(diff "$FIXTURE_NORM" "$RESPONSE_NORM" | grep -c '^[<>]' || true)

if [[ "$DIFF_COUNT" -le 2 ]]; then
    # Up to 2 diff lines (one < old, one > new) = exactly 1 change
    PASSED=$((PASSED + 1))
else
    echo "  Too many changes: $DIFF_COUNT diff lines (expected 2)" >&2
    diff "$FIXTURE_NORM" "$RESPONSE_NORM" >&2 || true
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
