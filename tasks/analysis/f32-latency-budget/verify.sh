#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi "fetch_pack" "$STDIN_FILE"; then
    echo "FAIL"
    echo "  Used fetch_pack causing N+1 queries." >&2
    exit 0
fi
if grep -qi "recall_body" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL
  Did not use recall_body metadata." >&2
exit 0
