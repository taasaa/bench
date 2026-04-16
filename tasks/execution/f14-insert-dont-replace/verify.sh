#!/usr/bin/env bash
# verify.sh for f14-insert-dont-replace
set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.py"
cat > "$STDIN_FILE"

HELPER="$WORK_DIR/extract.py"
DEDENT="$WORK_DIR/dedent.py"
CORR="$WORK_DIR/correct.py"

cat > "$HELPER" << 'EXTRACT_EOF'
import re, sys, ast

filepath = sys.argv[1]
with open(filepath) as f:
    raw = f.read()

raw = raw.replace(chr(13), chr(10))
raw = raw.replace(chr(0x2019), chr(0x27)).replace(chr(0x2018), chr(0x27))
raw = raw.replace(chr(0x201c), chr(0x22)).replace(chr(0x201d), chr(0x22))

BACKTICK = chr(0x60)
fence = BACKTICK * 3 + 'python'
blocks = re.findall(re.escape(fence) + r'(.*?)' + re.escape(BACKTICK * 3), raw, re.DOTALL)
if not blocks:
    m = re.search(r'\bdef\s+', raw)
    blocks = [raw[m.start():]] if m else [raw]

def dedent(code):
    lines = code.split(chr(10))
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return code
    min_indent = min(len(l) - len(l.lstrip()) for l in non_empty)
    return chr(10).join(l[min_indent:] if len(l) >= min_indent else l for l in lines)

out = []
for block in blocks:
    block = block.rstrip()
    try:
        tree = ast.parse(dedent(block))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                seg = ast.get_source_segment(block, node)
                if seg:
                    out.append(seg)
    except SyntaxError:
        out.append(dedent(block))

print(chr(10).join(out))

EXTRACT_EOF

cat > "$DEDENT" << 'DEDENT_EOF'
import sys
with open(sys.argv[1]) as f:
    content = f.read()
with open(sys.argv[2], 'w') as f:
    for line in content.split(chr(10)):
        f.write(line.lstrip() + chr(10))

DEDENT_EOF

cat > "$CORR" << 'CORR_EOF'
import sys, re
code = open(sys.argv[1]).read()
match = re.search(r'def ([a-z_]+)\(', code)
if not match:
    print('no_func'); sys.exit(0)
fname = match.group(1)
ns = {}
try:
    exec(code, ns)
except Exception as e:
    print('exec_error: ' + str(e)); sys.exit(0)
func = ns.get(fname)
if not func:
    print('no_func_in_ns'); sys.exit(0)
try:
    if fname == 'calculate_total':
        r1, r2 = func([50]), func([150])
        print('yes' if abs(r1-54.0)<0.01 and abs(r2-145.8)<0.01 else f'wrong: {[50]}={r1} {[150]}={r2}')
    elif fname == 'process_age':
        r1 = func(25)
        if '25' in r1 and 'digits' in r1:
            try: func(0); print('wrong: no ValueError for 0')
            except ValueError:
                try: func(-1); print('wrong: no ValueError for -1')
                except ValueError: print('yes')
        else: print('wrong: process_age(25)=' + str(r1))
    elif fname == 'calculate_shipping':
        r1, r2 = func(5), func(15)
        print('yes' if abs(r1-17.5)<0.01 and abs(r2-0.0)<0.01 else f'wrong: {5}kg={r1} {15}kg={r2}')
    elif fname == 'format_name':
        r1 = func('john doe')
        print('yes' if r1 == 'John Doe' else f'wrong: format_name={r1}')
    else: print('unknown_func')
except Exception as e:
    print('error: ' + str(e))

CORR_EOF

RESPONSE_CODE="$WORK_DIR/response_code.py"
RESPONSE_CLEAN="$WORK_DIR/response_clean.txt"

python3 "$HELPER" "$STDIN_FILE" > "$RESPONSE_CODE"
python3 "$DEDENT" "$RESPONSE_CODE" "$RESPONSE_CLEAN"

TOTAL_CHECKS=3
PASSED=0

SAMPLE="${SAMPLE_ID:-f14-discount}"
case "$SAMPLE" in
    f14-discount)
        LINE1="subtotal = sum(items)"
        LINE2="tax = subtotal * 0.08"
        LINE3='return round(subtotal + tax, 2)'
        NEW_PATTERN="discount|subtotal.*0\\.9|subtotal.*\\*.0.9"
        ;;
    f14-validation)
        LINE1='age_str = str(age)'
        LINE2='age_len = len(age_str)'
        LINE3='return f"Age: {age_str} (digits: {age_len})"'
        NEW_PATTERN="raise ValueError|if.*not.*isinstance|if.*<=.*0|if.*age.*<=.*0|if.*not.*positive"
        ;;
    f14-shipping)
        LINE1='base_rate = weight * 2.50'
        LINE2='handling = 5.00'
        LINE3='return round(base_rate + handling, 2)'
        NEW_PATTERN="weight.*10|free.*shipping|base_rate.*=.*0|shipping.*0|if.*weight"
        ;;
    f14-capitalize)
        LINE1='parts = name.strip().split()'
        LINE2='result = " ".join(parts)'
        LINE3='return result'
        NEW_PATTERN="capitalize|title\\(\\)|upper"
        ;;
    *)
        LINE1="subtotal = sum(items)"
        LINE2="tax = subtotal * 0.08"
        LINE3='return round(subtotal + tax, 2)'
        NEW_PATTERN="discount"
        ;;
esac

# Check 1: original lines present (dedented col-0)
ORIG_FOUND=0
for line in "$LINE1" "$LINE2" "$LINE3"; do
    grep -qxF -- "$line" "$RESPONSE_CLEAN" && ORIG_FOUND=$((ORIG_FOUND + 1)) || true
done
[[ $ORIG_FOUND -eq 3 ]] && PASSED=$((PASSED + 1)) || echo "  Original lines missing or modified (found ${ORIG_FOUND}/3)" >&2

# Check 2: new logic present in raw response
grep -qEi -- "$NEW_PATTERN" "$STDIN_FILE" && PASSED=$((PASSED + 1)) || echo "  Expected new logic not found" >&2

# Check 3: function correctness via exec
CORRECTNESS=$(python3 "$CORR" "$RESPONSE_CODE" 2>/dev/null) || CORRECTNESS="error"
[[ "$CORRECTNESS" == "yes" ]] && PASSED=$((PASSED + 1)) || echo "  Function correctness check failed: $CORRECTNESS" >&2

[[ $PASSED -eq $TOTAL_CHECKS ]] && echo "PASS ${PASSED}/${TOTAL_CHECKS}" || { echo "FAIL"; echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2; }
