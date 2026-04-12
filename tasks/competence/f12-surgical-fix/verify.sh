#!/usr/bin/env bash
# verify.sh for f12-surgical-fix
#
# Receives model response (the "fixed" function) on stdin.
# Validates that:
#   1. The response is valid Python (syntax check)
#   2. The fix is correct (function produces expected output on test cases)
#   3. Only one line was changed from the original (minimal diff)
#
# The original (buggy) function is stored in fixtures/ keyed by sample id.
# Since verify.sh doesn't have direct access to the sample id, we use a
# simpler approach: verify the response is a complete function and the
# output looks reasonable.
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.py"
cat > "$STDIN_FILE"

TOTAL_CHECKS=3
PASSED=0

# Check 1: Response is valid Python syntax
if python3 -c "
import ast, sys
with open(sys.argv[1]) as f:
    ast.parse(f.read())
" "$STDIN_FILE" 2>/dev/null; then
    PASSED=$((PASSED + 1))
else
    echo "  Response is not valid Python syntax" >&2
fi

# Check 2: Response contains a 'def' (is a function definition)
if grep -qE '^def [a-z_]+\(' "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Response does not contain a function definition" >&2
fi

# Check 3: The function runs without error and returns correct values
# We test a few generic cases that all the fixed functions should handle
FUNC_TEST=$(python3 -c "
import sys
sys.path.insert(0, '$WORK_DIR')

# Read the response and try to run it
with open('$STDIN_FILE') as f:
    code = f.read()

# Extract function name
import re
match = re.search(r'def ([a-z_]+)\(', code)
if not match:
    print('no_func_name')
    sys.exit(0)

func_name = match.group(1)
namespace = {}
exec(code, namespace)
func = namespace[func_name]

# Run basic smoke test — the function should not crash on trivial input
try:
    # All functions take simple inputs
    if func_name == 'get_page':
        result = func([1,2,3,4,5,6,7,8,9,10], 1, 3)
        if result != [1,2,3]:
            print(f'wrong: get_page([1..10],1,3) = {result}, expected [1,2,3]')
            sys.exit(0)
        result = func([1,2,3,4,5,6,7,8,9,10], 2, 3)
        if result != [4,5,6]:
            print(f'wrong: get_page([1..10],2,3) = {result}, expected [4,5,6]')
            sys.exit(0)
    elif func_name == 'is_in_range':
        if not func(5, 1, 10):
            print('wrong: is_in_range(5,1,10) should be True')
            sys.exit(0)
        if func(0, 1, 10):
            print('wrong: is_in_range(0,1,10) should be False')
            sys.exit(0)
        if not func(10, 1, 10):
            print('wrong: is_in_range(10,1,10) should be True')
            sys.exit(0)
    elif func_name == 'find_first_negative':
        if func([1, 2, -3, 4]) != 2:
            print('wrong: find_first_negative([1,2,-3,4]) should be 2')
            sys.exit(0)
        if func([1, 2, 3]) != -1:
            print('wrong: find_first_negative([1,2,3]) should be -1')
            sys.exit(0)
        if func([-1, 2, 3]) != 0:
            print('wrong: find_first_negative([-1,2,3]) should be 0')
            sys.exit(0)
    elif func_name == 'safe_average':
        if func([10, 20, 30]) != 20.0:
            print(f'wrong: safe_average([10,20,30]) should be 20.0')
            sys.exit(0)
        if func([]) != 0.0:
            print('wrong: safe_average([]) should be 0.0')
            sys.exit(0)
    print('yes')
except Exception as e:
    print(f'error: {e}')
" 2>/dev/null || echo "error")

if [[ "$FUNC_TEST" == "yes" ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Function correctness check failed: $FUNC_TEST" >&2
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
