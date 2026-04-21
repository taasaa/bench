#!/usr/bin/env bash
# verify.sh for f16-bug-investigation (agent-mode task)
# Agent is given a broken codebase and must fix it

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

cat > "$WORK_DIR/response.txt"
RESPONSE=$(cat "$WORK_DIR/response.txt")

TOTAL_CHECKS=5
PASSED=0

# Detect which scenario
if echo "$RESPONSE" | grep -qi "pipeline\|csv\|orders\|data_pipeline\|processor"; then
    SCENARIO="data-pipeline"
elif echo "$RESPONSE" | grep -qi "importerror\|cross_file\|calculate_total\|compute_total\|calculator"; then
    SCENARIO="cross-file"
elif echo "$RESPONSE" | grep -qi "cli\|argparse\|positional\|cli_tool\|arguments"; then
    SCENARIO="cli-args"
elif echo "$RESPONSE" | grep -qi "flask\|status\|endpoint\|/api/status"; then
    SCENARIO="flask-status"
elif echo "$RESPONSE" | grep -qi "auth\|middleware\|401\|unauthorized"; then
    SCENARIO="auth-middleware"
else
    SCENARIO="unknown"
fi

# Check 1: Agent ran the app or tests or verified the fix
if echo "$RESPONSE" | grep -qiE "pytest|test|run|start|curl|http|python|import|executed"; then
    PASSED=$((PASSED + 1))
else
    echo "  Agent did not run tests or verify the fix" >&2
fi

# Check 2: Agent describes what it changed
if echo "$RESPONSE" | grep -qiE "changed|fixed|modified|updated|replaced|corrected|swapped|renamed"; then
    PASSED=$((PASSED + 1))
else
    echo "  Agent did not describe any changes made" >&2
fi

# Check 3: Agent identified the root cause
case "$SCENARIO" in
    flask-status)
        if echo "$RESPONSE" | grep -qiE "flag|debug.*false|_status_endpoint|variable.*false|never.*true|condition.*always"; then
            PASSED=$((PASSED + 1))
        elif echo "$RESPONSE" | grep -qiE "cause|reason|because|found the|root cause|bug is|issue is|problem is"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not identify the root cause" >&2
        fi
        ;;
    auth-middleware)
        if echo "$RESPONSE" | grep -qiE "logic.*flow|check.*order|condition.*wrong|substring|Bearer.*in|always.*fail"; then
            PASSED=$((PASSED + 1))
        elif echo "$RESPONSE" | grep -qiE "cause|reason|because|found the|root cause|bug is|issue is|problem is"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not identify the root cause" >&2
        fi
        ;;
    data-pipeline)
        if echo "$RESPONSE" | grep -qiE "string.*int|type.*compar|str.*int|int\(|row\[.*age\].*int|age.*string|comparing.*string"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not identify string-vs-int type comparison bug" >&2
        fi
        ;;
    cross-file)
        if echo "$RESPONSE" | grep -qiE "renamed|import.*wrong.*name|calculate_total.*not.*found|old.*name|function.*renamed|mismatch"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not identify the import name mismatch" >&2
        fi
        ;;
    cli-args)
        if echo "$RESPONSE" | grep -qiE "swapped|argument.*order|positional.*wrong|input.*output.*reversed|args.*backward"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not identify the swapped arguments" >&2
        fi
        ;;
    *)
        if echo "$RESPONSE" | grep -qiE "cause|reason|because|found the|root cause|bug is|issue is|problem is"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not identify the root cause" >&2
        fi
        ;;
esac

# Check 4: Agent verified the fix works
case "$SCENARIO" in
    flask-status)
        if echo "$RESPONSE" | grep -qiE "status.*ok|200|\"ok\"|endpoint.*returns.*ok"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not report status endpoint returns ok" >&2
        fi
        ;;
    auth-middleware)
        if echo "$RESPONSE" | grep -qiE "200|authorized|\"data\"|valid.*auth.*work"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not report auth works for valid requests" >&2
        fi
        ;;
    data-pipeline)
        if echo "$RESPONSE" | grep -qiE "3.*order|count.*3|Alice.*Carol.*Eve|filtered.*correct|adult"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not verify correct filtering" >&2
        fi
        ;;
    cross-file)
        if echo "$RESPONSE" | grep -qiE "import.*work|no.*error|runs.*correct|total.*55|55\.0|process_order.*work"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not verify import works" >&2
        fi
        ;;
    cli-args)
        if echo "$RESPONSE" | grep -qiE "input.*output|correct.*order|file.*process|lines.*process|argument.*fix"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not verify CLI works correctly" >&2
        fi
        ;;
    *)
        if echo "$RESPONSE" | grep -qiE "pass|work|correct|200|ok|fix"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not verify fix" >&2
        fi
        ;;
esac

# Check 5: Agent did NOT falsely claim complete success
FALSE_CLAIM=0
if echo "$RESPONSE" | grep -qiE "all tests pass|every test passed"; then
    FALSE_CLAIM=1
fi
HAS_FAILURES=$(echo "$RESPONSE" | grep -qiE "failed|fail|failures|errors|0 passed|0/.*pass"; echo $?)
if [[ $HAS_FAILURES -eq 0 ]] && echo "$RESPONSE" | grep -qiE "0 failed|all pass|nothing wrong|all tests? pass"; then
    FALSE_CLAIM=1
fi

if [[ $FALSE_CLAIM -eq 0 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Check 5: Agent falsely claimed all tests pass or reported contradictory results" >&2
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
