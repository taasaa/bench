#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi -E "DROP INDEX|ALTER TABLE" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL
  Did not drop the UNIQUE index in the database." >&2
exit 0
