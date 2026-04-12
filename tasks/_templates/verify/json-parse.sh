#!/usr/bin/env bash
# json-parse.sh — Parse JSON from stdin and evaluate a jq expression
#
# Usage:
#   model_output | ./json-parse.sh '.key' 'expected_value'
#   echo '{"name":"alice"}' | ./json-parse.sh '.name' 'alice'
#
# Arguments:
#   $1 — jq expression (e.g. '.answer', '.results | length')
#   $2 — expected value (string comparison after stripping quotes)
#
# Outputs: PASS 1/1  or  FAIL with diagnostic info
#
# Exit codes: 0 = PASS, 1 = FAIL, 2 = usage error

set -euo pipefail

# --- Argument validation ---
if [[ $# -lt 2 ]]; then
    echo "FAIL — usage: $0 <jq_expression> <expected_value>" >&2
    echo "  Receives JSON on stdin, evaluates jq expression, compares to expected_value." >&2
    exit 2
fi

JQ_EXPR="$1"
EXPECTED="$2"

# --- Check for jq ---
if ! command -v jq &> /dev/null; then
    echo "FAIL — jq is not installed; cannot parse JSON" >&2
    exit 2
fi

# --- Capture stdin ---
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/input.json"
cat > "$STDIN_FILE"

# --- Parse and evaluate ---
ACTUAL=$(jq -r "$JQ_EXPR" "$STDIN_FILE" 2>&1) || {
    echo "FAIL"
    echo "  jq parse error: $ACTUAL" >&2
    exit 1
}

# --- Compare ---
if [[ "$ACTUAL" == "$EXPECTED" ]]; then
    echo "PASS 1/1"
    exit 0
else
    echo "FAIL"
    echo "  expression: $JQ_EXPR" >&2
    echo "  expected:   $EXPECTED" >&2
    echo "  actual:     $ACTUAL" >&2
    exit 1
fi
