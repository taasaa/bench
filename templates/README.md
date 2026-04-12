# verify.sh Pattern Reference

Reference verify.sh scripts for scoring model output in bench tasks. Copy and adapt these for individual evaluation tasks.

## Scripts

### byte-identical.sh
Compare model output against expected content byte-for-byte.

**When to use:** Code generation tasks where the output must exactly match a known-good file (function body, config snippet, etc.).

**Usage:**
```bash
model_output | ./byte-identical.sh expected.txt
```

**Customization:**
- Adjust normalization in the `normalize()` function if your task needs stricter or looser comparison
- Remove the trailing-whitespace stripping if whitespace is significant

**Example:**
```bash
# Known-good: output matches expected exactly
echo "hello world" | ./byte-identical.sh <(echo "hello world")
# → PASS 1/1

# Known-bad: output differs
echo "hello world" | ./byte-identical.sh <(echo "goodbye world")
# → FAIL (with diff)
```

---

### json-parse.sh
Parse JSON output and evaluate a jq expression against an expected value.

**When to use:** Tasks where the model returns structured JSON and you need to check specific fields, counts, or nested values.

**Usage:**
```bash
model_output | ./json-parse.sh '.answer' '42'
echo '{"items":[1,2,3]}' | ./json-parse.sh '.items | length' '3'
```

**Customization:**
- Change the jq expression for any JSON structure
- For numeric comparisons, wrap expected in quotes: `'42'`
- For null checks: `./json-parse.sh '.error' 'null'`

**Example:**
```bash
# Known-good: value matches
echo '{"name":"alice","score":95}' | ./json-parse.sh '.name' 'alice'
# → PASS 1/1

# Known-bad: value mismatch
echo '{"name":"alice"}' | ./json-parse.sh '.name' 'bob'
# → FAIL (shows expected vs actual)
```

---

### forbidden-string.sh
Check that none of the forbidden patterns appear in the output.

**When to use:** Safety or style checks — verify the model doesn't output API keys, TODO comments, hardcoded values, or specific anti-patterns.

**Usage:**
```bash
model_output | ./forbidden-string.sh "password" "secret" "api_key"
cat code.py | ./forbidden-string.sh "TODO" "FIXME" "HACK"
```

**Customization:**
- Pass any number of patterns as arguments
- Matching is case-insensitive by default (uses `grep -i`)
- To make case-sensitive, edit the script to remove the `-i` flag

**Example:**
```bash
# Known-good: no forbidden strings
echo "function add(a, b) { return a + b; }" | ./forbidden-string.sh "password" "secret"
# → PASS 2/2

# Known-bad: contains forbidden string
echo "const secret = 'abc123';" | ./forbidden-string.sh "password" "secret"
# → FAIL (reports which pattern matched)
```

---

### line-count-delta.sh
Compare line-count changes between an original file and the model's edited version.

**When to use:** Editing/refactoring tasks where you need to verify the model added and/or removed a specific number of lines (not exact content).

**Usage:**
```bash
edited_output | ./line-count-delta.sh original.txt "+3-1"
```

**Delta format:** `+N-M` where N = lines added, M = lines removed.

**Customization:**
- Use `+0-0` to verify the file is unchanged
- Use `+N-0` to verify only additions (pure insertion tasks)
- Combine with byte-identical.sh for exact change verification

**Example:**
```bash
# Setup
echo -e "line1\nline2\nline3" > /tmp/original.txt

# Known-good: added 1 line, removed 1 line
echo -e "line1\nreplaced\nline3" | ./line-count-delta.sh /tmp/original.txt "+1-1"
# → PASS 1/1

# Known-bad: wrong delta
echo -e "line1\nreplaced\nline3" | ./line-count-delta.sh /tmp/original.txt "+2-0"
# → FAIL (shows actual vs expected delta)
```

## General Notes

- All scripts output `PASS N/M` or `FAIL` (uppercased) for easy parsing by scorers
- All scripts read model output from **stdin** and take file paths/arguments as parameters
- Exit codes: 0 = pass, 1 = fail, 2 = usage error
- Scripts create temp files and clean up via trap on EXIT
- Scripts are self-contained with no external dependencies beyond bash, coreutils, and (for json-parse.sh) jq
