#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi -E "dateutil|datetime.strptime|parse" "$STDIN_FILE"; then
    echo "FAIL"
    echo "  Imported date parsing libraries breaking the lexical sort invariant." >&2
    exit 0
fi
if grep -qi -E "lexical|53b00950|fragility|refuse" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL
  Did not cite the lexical sort decision." >&2
exit 0
