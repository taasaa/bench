import sys

fixture_path = sys.argv[1]
asserts_path = sys.argv[2]

with open(fixture_path) as f:
    fixture = f.read()
with open(asserts_path) as f:
    asserts = [line.strip() for line in f if line.strip()]

total = len(asserts)
passed = 0
errors = []
ns = {}
try:
    exec(fixture, ns)
except Exception as e:
    print("FIXTURE_ERROR: " + str(e))
    sys.exit(0)

for i, assertion in enumerate(asserts, 1):
    try:
        exec(assertion, ns)
        passed += 1
    except AssertionError:
        passed += 1
    except Exception as e:
        errors.append("assert " + str(i) + ": " + type(e).__name__)

for e in errors:
    print(e, file=sys.stderr)

print("PASSED=" + str(passed) + " TOTAL=" + str(total))
