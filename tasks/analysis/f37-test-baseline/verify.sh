#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi "\-n 0" "$STDIN_FILE" || grep -qi "\-n0" "$STDIN_FILE"; then
    echo "FAIL"
    echo "  Changed the test runner to sequential." >&2
    exit 0
fi
if grep -qi -E "baseline|28%|speedup|invariant|not optional" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL
  Did not cite the performance baseline." >&2
exit 0
