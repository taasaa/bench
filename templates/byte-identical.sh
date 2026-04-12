#!/usr/bin/env bash
# byte-identical.sh — Compare model output (stdin) against expected content ($1)
#
# Usage:
#   model_output | ./byte-identical.sh expected.txt
#   ./byte-identical.sh expected.txt < model_output.txt
#
# Normalizes trailing whitespace and line endings before comparing.
# Outputs: PASS 1/1  or  FAIL with diagnostic diff
#
# Exit codes: 0 = PASS, 1 = FAIL, 2 = usage error

set -euo pipefail

# --- Argument validation ---
if [[ $# -lt 1 ]]; then
    echo "FAIL — usage: $0 <expected_file>" >&2
    echo "  Receives model output on stdin, compares against expected_file." >&2
    exit 2
fi

EXPECTED="$1"

if [[ ! -f "$EXPECTED" ]]; then
    echo "FAIL — expected file not found: $EXPECTED" >&2
    exit 2
fi

# --- Normalize and compare ---
# Read stdin into a temp file, normalizing trailing whitespace and line endings
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

# Normalize: strip CR, strip trailing spaces/tabs, ensure final newline
normalize() {
    local input_file="$1"
    local output_file="$2"
    sed 's/\r$//' "$input_file" | sed 's/[[:space:]]*$//' > "$output_file"
}

# Capture stdin
STDIN_FILE="$WORK_DIR/stdin.txt"
cat > "$STDIN_FILE"

NORM_STDIN="$WORK_DIR/stdin_norm.txt"
NORM_EXPECTED="$WORK_DIR/expected_norm.txt"

normalize "$STDIN_FILE" "$NORM_STDIN"
normalize "$EXPECTED" "$NORM_EXPECTED"

# Compare
if diff -q "$NORM_STDIN" "$NORM_EXPECTED" > /dev/null 2>&1; then
    echo "PASS 1/1"
    exit 0
else
    echo "FAIL"
    echo "--- diff (expected vs actual) ---" >&2
    diff "$NORM_EXPECTED" "$NORM_STDIN" >&2 || true
    echo "--- end diff ---" >&2
    exit 1
fi
