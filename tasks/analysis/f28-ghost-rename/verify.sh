#!/usr/bin/env bash
# verify.sh for f28-ghost-rename
set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi "sync_worker" "$STDIN_FILE"; then
    if grep -qi "owner_id" "$STDIN_FILE" && grep -qi "SELECT" "$STDIN_FILE"; then
        if grep -i "SELECT.*owner_id" "$STDIN_FILE" >/dev/null; then
            echo "PASS 1/1"
            exit 0
        fi
    fi
fi

echo "FAIL"
echo "  Did not update sync_worker.py to use owner_id in the SELECT statement." >&2
exit 0
