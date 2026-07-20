#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi "def retire_governed_record(store, revision_id)" "$STDIN_FILE"; then
    echo "FAIL"
    echo "  Modified signature breaking Task 3 parity." >&2
    exit 0
fi
if grep -qi -E "parity|Task 3|architecture_plan" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL
  Did not mention parity or Task 3 block." >&2
exit 0
