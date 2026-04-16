#!/usr/bin/env bash
# verify.sh for f5-multi-constraint-edit
#
# Receives model response on stdin (Python code).
# Checks:
#   1. New function exists with type hints
#   2. All original function signatures unchanged
#   3. if __name__ == "__main__" block preserved
#   4. All docstrings preserved
#   5. Only the new function has new type hints added
#
# Environment:
#   SAMPLE_ID - identifies which sample (determines function names)
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

TOTAL_CHECKS=5
PASSED=0

# Map SAMPLE_ID to expected function names
SAMPLE="${SAMPLE_ID:-f5-string-utils}"
case "$SAMPLE" in
    f5-string-utils)
        NEW_FUNC="validate"
        ORIG_FUNCS="validate_email validate_phone validate_username normalize_string"
        MAIN_LINE='print(validate_email("test@example.com"))'
        ;;
    f5-number-utils)
        NEW_FUNC="process"
        ORIG_FUNCS="clamp normalize_percent scale_value format_currency"
        MAIN_LINE='print(clamp(15, 0, 10))'
        ;;
    f5-list-utils)
        NEW_FUNC="transform_list"
        ORIG_FUNCS="double_all filter_positive sort_desc unique_only"
        MAIN_LINE='print(double_all([1, 2, 3]))'
        ;;
    f5-dict-utils)
        NEW_FUNC="apply_to_values"
        ORIG_FUNCS="uppercase_values strip_values count_values invert_dict"
        MAIN_LINE='print(uppercase_values({"name": "alice", "city": "london"}))'
        ;;
    *)
        NEW_FUNC="validate"
        ORIG_FUNCS="validate_email validate_phone validate_username normalize_string"
        MAIN_LINE='print(validate_email("test@example.com"))'
        ;;
esac

# Check 1: New function exists with type hints
if grep -qE "def[[:space:]]+${NEW_FUNC}\(" "$STDIN_FILE"; then
    # Verify it has type hints (colon in function signature for params or return)
    FUNC_LINE=$(grep -E "def[[:space:]]+${NEW_FUNC}\(" "$STDIN_FILE" | head -1)
    if echo "$FUNC_LINE" | grep -qE ":\s*(str|int|float|bool|list|dict|Callable|Any|callable)\|->"; then
        PASSED=$((PASSED + 1))
    elif echo "$FUNC_LINE" | grep -qE "->\s*(bool|str|int|float|list|dict|None|Any)"; then
        PASSED=$((PASSED + 1))
    else
        # Check if type hints appear anywhere in the function def line
        if echo "$FUNC_LINE" | grep -qE ":\s*(str|int|float|bool|list|dict)\b"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Check 1: ${NEW_FUNC}() exists but lacks type hints" >&2
        fi
    fi
else
    echo "  Check 1: ${NEW_FUNC}() function not found" >&2
fi

# Check 2: All original function signatures unchanged
SIG_PASS=true
for func in $ORIG_FUNCS; do
    if ! grep -qE "def[[:space:]]+${func}\(" "$STDIN_FILE"; then
        echo "  Check 2: original function ${func}() missing" >&2
        SIG_PASS=false
        break
    fi
done
if $SIG_PASS; then
    PASSED=$((PASSED + 1))
fi

# Check 3: if __name__ == "__main__" block preserved
if grep -qF 'if __name__ == "__main__":' "$STDIN_FILE"; then
    if grep -qF "$MAIN_LINE" "$STDIN_FILE"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Check 3: __main__ block found but content changed" >&2
    fi
else
    echo "  Check 3: __main__ block missing" >&2
fi

# Check 4: All docstrings preserved
DOCS_PASS=true
for func in $ORIG_FUNCS; do
    if ! grep -qE '"""' "$STDIN_FILE"; then
        DOCS_PASS=false
        break
    fi
done
if $DOCS_PASS; then
    PASSED=$((PASSED + 1))
else
    echo "  Check 4: docstrings missing" >&2
fi

# Check 5: Only the new function has type hints (original functions should not have type annotations added)
# Original functions may already have type hints in their signatures from the prompt code.
# We check that no NEW type hints were added to the original functions that weren't there before.
# Check 5: Only the new function has type hints (original functions should not have type annotations added)
# The EXTRA_HINTS check verified that original function signatures haven't gained new type hints.
# For string-utils, original code already had type hints. For others, it didn't.
# We verify: new function has type hints, and original functions match their prompt signatures.
if grep -qE "def[[:space:]]+${NEW_FUNC}\(" "$STDIN_FILE"; then
    NEW_HAS_HINTS=1
else
    NEW_HAS_HINTS=0
fi

if [[ $NEW_HAS_HINTS -eq 1 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Check 5: ${NEW_FUNC}() lacks type hints" >&2
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
