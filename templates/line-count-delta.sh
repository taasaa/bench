#!/usr/bin/env bash
# line-count-delta.sh — Compare line-count delta of edited file (stdin) vs original ($1)
#
# Usage:
#   edited_output | ./line-count-delta.sh original.txt "+3-1"
#   cat new_version.py | ./line-count-delta.sh old_version.py "+5-2"
#
# Arguments:
#   $1 — path to original file (before edits)
#   $2 — expected delta in format "+N-M" (N additions, M removals)
#         Examples: "+3-0" (3 lines added, none removed)
#                   "+1-2" (1 added, 2 removed)
#                   "+0-3" (none added, 3 removed)
#
# Outputs: PASS 1/1  or  FAIL with actual vs expected delta
#
# Note: Delta is computed as: additions = new_lines - common, removals = old_lines - common
#       where common = lines present in both files (set intersection, order-independent).
#       For simple cases this matches diff(1) stat output.
#
# Exit codes: 0 = PASS, 1 = FAIL, 2 = usage error

set -euo pipefail

# --- Argument validation ---
if [[ $# -lt 2 ]]; then
    echo "FAIL — usage: $0 <original_file> <expected_delta>" >&2
    echo "  Receives edited file on stdin, compares line count delta." >&2
    echo "  Delta format: \"+N-M\" (N additions, M removals)" >&2
    exit 2
fi

ORIGINAL="$1"
EXPECTED_DELTA="$2"

if [[ ! -f "$ORIGINAL" ]]; then
    echo "FAIL — original file not found: $ORIGINAL" >&2
    exit 2
fi

# --- Parse expected delta ---
if ! [[ "$EXPECTED_DELTA" =~ ^\+([0-9]+)-([0-9]+)$ ]]; then
    echo "FAIL — invalid delta format: $EXPECTED_DELTA (expected +N-M)" >&2
    exit 2
fi

EXPECTED_ADD="${BASH_REMATCH[1]}"
EXPECTED_REM="${BASH_REMATCH[2]}"

# --- Capture stdin ---
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

NEW_FILE="$WORK_DIR/new.txt"
cat > "$NEW_FILE"

# --- Compute delta using diff ---
# Count added lines (lines starting with + in unified diff, excluding header)
# Count removed lines (lines starting with - in unified diff, excluding header)
DIFF_OUTPUT=$(diff "$ORIGINAL" "$NEW_FILE" 2>&1 || true)

if [[ -z "$DIFF_OUTPUT" ]]; then
    # Files are identical
    ACTUAL_ADD=0
    ACTUAL_REM=0
else
    # In diff output: '<' = lines from old file (removals), '>' = lines from new file (additions)
    ACTUAL_REM=$(echo "$DIFF_OUTPUT" | grep -c '^<' || echo "0")
    ACTUAL_ADD=$(echo "$DIFF_OUTPUT" | grep -c '^>' || echo "0")
    # Strip whitespace (macOS grep -c may include trailing newline)
    ACTUAL_ADD=${ACTUAL_ADD//[$'\t\r\n']/}
    ACTUAL_REM=${ACTUAL_REM//[$'\t\r\n']/}
fi

# --- Compare ---
ACTUAL_DELTA="+${ACTUAL_ADD}-${ACTUAL_REM}"

if [[ "$ACTUAL_ADD" -eq "$EXPECTED_ADD" && "$ACTUAL_REM" -eq "$EXPECTED_REM" ]]; then
    echo "PASS 1/1"
    exit 0
else
    echo "FAIL"
    echo "  expected delta: $EXPECTED_DELTA" >&2
    echo "  actual delta:   $ACTUAL_DELTA" >&2
    echo "  original lines: $(wc -l < "$ORIGINAL" | tr -d ' ')" >&2
    echo "  new lines:      $(wc -l < "$NEW_FILE" | tr -d ' ')" >&2
    exit 1
fi
