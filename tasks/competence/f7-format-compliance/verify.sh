#!/usr/bin/env bash
# verify.sh for f7-format-compliance
#
# Receives model response on stdin.
# Validates that the output is:
#   1. Valid JSON (parseable)
#   2. A JSON array
#   3. Each element is an object with exactly 3 keys: name, score, passed
#   4. No extra keys, correct types (name=string, score=number, passed=boolean)
#   5. No markdown fences or text outside the JSON
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

TOTAL_CHECKS=5
PASSED=0

# Strip leading/trailing whitespace for analysis
RAW=$(cat "$STDIN_FILE")
TRIMMED=$(echo "$RAW" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

# Check 1: No markdown code fences
if echo "$TRIMMED" | grep -qvE '^\s*```'; then
    PASSED=$((PASSED + 1))
else
    echo "  Output contains markdown code fences" >&2
fi

# Check 2: Valid JSON
if python3 -c "import json, sys; json.loads(sys.stdin.read())" <<< "$TRIMMED" 2>/dev/null; then
    PASSED=$((PASSED + 1))
else
    echo "  Output is not valid JSON" >&2
fi

# Check 3: It's a JSON array (not object or other type)
IS_ARRAY=$(python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print('yes' if isinstance(data, list) else 'no')
" <<< "$TRIMMED" 2>/dev/null || echo "no")

if [[ "$IS_ARRAY" == "yes" ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Output is not a JSON array" >&2
fi

# Check 4: Each element has exactly the required keys (name, score, passed)
KEYS_OK=$(python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
required = {'name', 'score', 'passed'}
for i, item in enumerate(data):
    if not isinstance(item, dict):
        print(f'no: element {i} is not an object')
        sys.exit(0)
    keys = set(item.keys())
    if keys != required:
        print(f'no: element {i} has keys {keys}, expected {required}')
        sys.exit(0)
print('yes')
" <<< "$TRIMMED" 2>/dev/null || echo "no")

if [[ "$KEYS_OK" == "yes" ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Objects have wrong keys" >&2
fi

# Check 5: Correct types (name=string, score=number, passed=boolean)
TYPES_OK=$(python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
for i, item in enumerate(data):
    if not isinstance(item.get('name'), str):
        print(f'no: element {i} name is not a string')
        sys.exit(0)
    if not isinstance(item.get('score'), (int, float)):
        print(f'no: element {i} score is not a number')
        sys.exit(0)
    if not isinstance(item.get('passed'), bool):
        print(f'no: element {i} passed is not a boolean')
        sys.exit(0)
print('yes')
" <<< "$TRIMMED" 2>/dev/null || echo "no")

if [[ "$TYPES_OK" == "yes" ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Value types are incorrect" >&2
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
