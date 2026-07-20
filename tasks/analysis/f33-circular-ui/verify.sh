#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi "tui.terminal.rows" "$STDIN_FILE"; then
    echo "FAIL"
    echo "  Used circular tui.terminal.rows." >&2
    exit 0
fi
if grep -qi -E "process.stdout.rows|circular" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL
  Did not fix the circular UI constraint properly." >&2
exit 0
