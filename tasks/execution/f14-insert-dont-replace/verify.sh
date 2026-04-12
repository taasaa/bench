#!/usr/bin/env bash
# verify.sh for f14-insert-dont-replace
#
# Receives model response on stdin (a Python function with inserted logic).
# Checks:
#   1. Original 3 lines are present and unmodified
#   2. The expected new logic exists between the correct lines
#   3. The function returns correct values for test inputs
#
# Environment:
#   SAMPLE_ID - identifies which sample (determines expected behavior)
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.py"
cat > "$STDIN_FILE"

TOTAL_CHECKS=3
PASSED=0

# Map SAMPLE_ID to expected original lines and test cases
SAMPLE="${SAMPLE_ID:-f14-discount}"
case "$SAMPLE" in
    f14-discount)
        # Original: subtotal = sum(items) / tax = subtotal * 0.08 / return round(subtotal + tax, 2)
        # Insert: discount logic between subtotal and tax
        LINE1="subtotal = sum(items)"
        LINE2="tax = subtotal * 0.08"
        LINE3='return round(subtotal + tax, 2)'
        # Must have discount logic (10% off if subtotal > 100)
        NEW_PATTERN="discount|subtotal.*0\\.9|subtotal.*\\*.*0.9"
        # Test: calculate_total([50]) → 54.0, calculate_total([150]) → 141.2
        FUNC_NAME="calculate_total"
        ;;
    f14-validation)
        # Original: age_str = str(age) / age_len = len(age_str) / return f"Age: ..."
        # Insert: validation before age_str
        LINE1='age_str = str(age)'
        LINE2='age_len = len(age_str)'
        LINE3='return f"Age: {age_str} (digits: {age_len})"'
        NEW_PATTERN="raise ValueError|if.*not.*isinstance|if.*<=.*0|if.*age.*<=.*0|if.*not.*positive"
        FUNC_NAME="process_age"
        ;;
    f14-shipping)
        # Original: base_rate = weight * 2.50 / handling = 5.00 / return round(base_rate + handling, 2)
        # Insert: free shipping between handling and return
        LINE1='base_rate = weight * 2.50'
        LINE2='handling = 5.00'
        LINE3='return round(base_rate + handling, 2)'
        NEW_PATTERN="weight.*10|free.*shipping|base_rate.*=.*0|shipping.*0|if.*weight"
        FUNC_NAME="calculate_shipping"
        ;;
    f14-capitalize)
        # Original: parts = name.strip().split() / result = " ".join(parts) / return result
        # Insert: capitalization between parts and result
        LINE1='parts = name.strip().split()'
        LINE2='result = " ".join(parts)'
        LINE3='return result'
        NEW_PATTERN="capitalize|title\\(\\)|upper"
        FUNC_NAME="format_name"
        ;;
    *)
        LINE1="subtotal = sum(items)"
        LINE2="tax = subtotal * 0.08"
        LINE3='return round(subtotal + tax, 2)'
        NEW_PATTERN="discount"
        FUNC_NAME="calculate_total"
        ;;
esac

# Check 1: Original 3 lines are present and unmodified (full-line match)
# We strip leading whitespace from response lines and compare literally
ORIG_FOUND=0
RESPONSE_CLEAN="$WORK_DIR/response_clean.txt"
sed 's/^[[:space:]]*//' "$STDIN_FILE" > "$RESPONSE_CLEAN"

LINE1_CLEAN=$(echo "$LINE1" | sed 's/^[[:space:]]*//')
LINE2_CLEAN=$(echo "$LINE2" | sed 's/^[[:space:]]*//')
LINE3_CLEAN=$(echo "$LINE3" | sed 's/^[[:space:]]*//')

grep -qxF "$LINE1_CLEAN" "$RESPONSE_CLEAN" && ORIG_FOUND=$((ORIG_FOUND + 1)) || true
grep -qxF "$LINE2_CLEAN" "$RESPONSE_CLEAN" && ORIG_FOUND=$((ORIG_FOUND + 1)) || true
grep -qxF "$LINE3_CLEAN" "$RESPONSE_CLEAN" && ORIG_FOUND=$((ORIG_FOUND + 1)) || true

if [[ $ORIG_FOUND -eq 3 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Original lines missing or modified (found ${ORIG_FOUND}/3)" >&2
fi

# Check 2: New logic exists in the response
if grep -qEi "$NEW_PATTERN" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Expected new logic not found (pattern: ${NEW_PATTERN})" >&2
fi

# Check 3: Function correctness — test with actual inputs
CORRECTNESS=$(python3 -c "
import sys, re

with open('$STDIN_FILE') as f:
    code = f.read()

# Extract function name
match = re.search(r'def ([a-z_]+)\(', code)
if not match:
    print('no_func')
    sys.exit(0)

fname = match.group(1)
ns = {}
try:
    exec(code, ns)
except Exception as e:
    print(f'exec_error: {e}')
    sys.exit(0)

func = ns.get(fname)
if not func:
    print('no_func_in_ns')
    sys.exit(0)

try:
    if fname == 'calculate_total':
        # 50 -> 54.00 (no discount), 150 -> 145.80 (10% discount then tax)
        r1 = func([50])
        r2 = func([150])
        if abs(r1 - 54.0) < 0.01 and abs(r2 - 145.8) < 0.01:
            print('yes')
        else:
            print('wrong: [50]=' + str(r1) + ' [150]=' + str(r2))
    elif fname == 'process_age':
        # Should work for 25, should raise ValueError for 0 or -1 or 'abc'
        r1 = func(25)
        if '25' in r1 and 'digits' in r1:
            try:
                func(0)
                print('wrong: no ValueError for 0')
            except ValueError:
                try:
                    func(-1)
                    print('wrong: no ValueError for -1')
                except ValueError:
                    print('yes')
        else:
            print('wrong: process_age(25)=' + str(r1))
    elif fname == 'calculate_shipping':
        # 5kg = 5*2.5+5 = 17.50, 15kg = free = 0.00
        r1 = func(5)
        r2 = func(15)
        if abs(r1 - 17.5) < 0.01 and abs(r2 - 0.0) < 0.01:
            print('yes')
        else:
            print('wrong: 5kg=' + str(r1) + ' 15kg=' + str(r2))
    elif fname == 'format_name':
        r1 = func('john doe')
        if r1 == 'John Doe':
            print('yes')
        else:
            print('wrong: format_name(john doe)=' + str(r1))
    else:
        print('unknown_func')
except Exception as e:
    print('error: ' + str(e))
" 2>/dev/null || echo "error")

if [[ "$CORRECTNESS" == "yes" ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Function correctness check failed: $CORRECTNESS" >&2
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
