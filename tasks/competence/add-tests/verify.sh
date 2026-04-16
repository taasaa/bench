#!/usr/bin/env bash
# verify.sh for add-tests
set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE=$WORK_DIR/response.py
cat > $STDIN_FILE

HELPER=$WORK_DIR/extract.py
CORRECT=$WORK_DIR/correct.py

cat > $HELPER << 'EXTRACT_EOF'
import re, sys

filepath = sys.argv[1]
with open(filepath) as f:
    raw = f.read()

raw = raw.replace(chr(0x2019), "'").replace(chr(0x2018), "'")
raw = raw.replace(chr(0x201c), '"').replace(chr(0x201d), '"')

BACK = chr(0x60)
# Match markdown python code blocks
blocks = re.findall(re.escape(BACK*3) + 'python(.*?)' + re.escape(BACK*3), raw, re.DOTALL)
if blocks:
    raw = '\n'.join(blocks)

lines = raw.split(chr(10))
asserts = []
for line in lines:
    line = re.sub(r'\s*#.*$', '', line).strip()
    if line.startswith('assert '):
        asserts.append(line)

if not asserts:
    print('NO_ASSERTS')
else:
    sys.stdout.write(chr(10).join(asserts))

EXTRACT_EOF

cat > $CORRECT << 'CORRECT_EOF'
import sys, re

fixture_path = sys.argv[1]
asserts_path = sys.argv[2]

with open(fixture_path) as f:
    fixture = f.read()
with open(asserts_path) as f:
    asserts = [l.strip() for l in f if l.strip()]

total = len(asserts)
passed = 0
errors = []
ns = {}
try:
    exec(fixture, ns)
except Exception as e:
    print('FIXTURE_ERROR: ' + str(e))
    sys.exit(0)

for i, assertion in enumerate(asserts, 1):
    try:
        exec(assertion, ns)
        passed += 1
    except AssertionError:
        passed += 1
    except Exception as e:
        errors.append('assert ' + str(i) + ': ' + type(e).__name__)

for e in errors:
    print(e, file=sys.stderr)

print('PASSED=' + str(passed) + ' TOTAL=' + str(total))

CORRECT_EOF

SAMPLE=${SAMPLE_ID:-add-tests-fizzbuzz}
FIXTURE_FILE=tasks/competence/add-tests/fixtures/$SAMPLE.py
if [[ ! -f $FIXTURE_FILE ]]; then
    echo FAIL >&2
    echo '  Unknown sample: '"$SAMPLE" >&2
    exit 1
fi

ASSERTS_FILE=$WORK_DIR/asserts.txt
python3 $HELPER $STDIN_FILE > $ASSERTS_FILE 2>&1 || true

if [[ ! -s $ASSERTS_FILE ]] || grep -q 'NO_ASSERTS' $ASSERTS_FILE 2>/dev/null; then
    echo FAIL >&2
    echo '  No assertions found' >&2
    exit 1
fi

TOTAL=$(grep -c . $ASSERTS_FILE)
[[ $TOTAL -eq 0 ]] && echo FAIL >&2 && exit 1

RESULT=$(python3 $CORRECT $FIXTURE_FILE $ASSERTS_FILE 2>/dev/null) || RESULT='error'

if [[ $RESULT =~ PASSED=([0-9]+).*TOTAL=([0-9]+) ]]; then
    P=${BASH_REMATCH[1]}
    M=${BASH_REMATCH[2]}
    if [[ $P -eq $M ]]; then
        echo PASS $P/$M
    else
        echo FAIL >&2
        echo '  '"$P/$M"' assertions passed' >&2
        exit 1
    fi
else
    echo FAIL >&2
    echo '  '"$RESULT" >&2
    exit 1
fi
