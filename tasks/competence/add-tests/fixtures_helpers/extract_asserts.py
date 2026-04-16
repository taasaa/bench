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
