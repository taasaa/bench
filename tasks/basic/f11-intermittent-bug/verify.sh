#!/usr/bin/env bash
# verify.sh for f11-intermittent-bug
#
# Receives model response on stdin (text diagnosing intermittent test failures).
# Checks:
#   1. Response identifies timing issue / race condition / timing-dependent test
#   2. Response suggests polling, waiting for condition, time.monotonic, or
#      proper async — NOT 'increase sleep duration' or 'add more sleep'
#   3. Response does NOT suggest 'add more sleep' or 'increase timeout' as the fix
#
# Environment:
#   SAMPLE_ID - identifies which sample (determines expected patterns)
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

TOTAL_CHECKS=3
PASSED=0

# Map SAMPLE_ID to expected patterns
SAMPLE="${SAMPLE_ID:-f11-sleep-timestamp}"
case "$SAMPLE" in
    f11-sleep-timestamp)
        # Tests use time.sleep + fixed-duration assertions that are timing-dependent
        ROOT_PATTERNS="timing|race condition|flak.*timing|timing.*(dependent|sensitive|issue|problem)|time\\.time.*not.*reliable|sleep.*not.*deterministic|fragile.*time|non.deterministic.*time|CI.*(slow|slower|load)"
        # Proper fixes: polling, wait-for-condition, time.monotonic, mock time, retry
        FIX_PATTERNS="poll|wait.*(for|until|condition)|retry|time\\.monotonic|mock.*time|freeze.*time|freezegun|assert.*(eventually|retries)|subprocess.*wait|wait_for|thread.*join|event.*wait|while.*not.*complete|loop.*until|attempts"
        # Forbidden: just increase sleep or timeout (specific "increase X to Y" phrasing)
        FORBIDDEN_PATTERNS="increase.*sleep|add.*more.*sleep|longer.*sleep|bigger.*sleep|increase.*timeout|longer.*timeout|bump.*sleep|change.*sleep.*to|change.*to.*sleep|sleep.*to.*[0-9]|sleep.*[0-9]+.*instead"
        ;;
    f11-concurrent-file-access)
        # Race condition between writer process and reader
        ROOT_PATTERNS="race condition|timing|concurrent|synchroniz|writer.*(finish|complete)|process.*(complete|finish)|file.*(ready|written)|compete|not.*wait.*for"
        # Proper fixes: wait for process, poll for file, use subprocess.wait, check file
        FIX_PATTERNS="subprocess\\.wait|poll|wait.*(for|until|process|file)|communicate\\(\\)|while.*not.*os\\.path|retry|file.*(exist|ready)|lock|mutex|event|semaphore|check.*file.*exist|inotify|watchdog|join"
        # Forbidden: just increase sleep (specific "increase X to Y" phrasing)
        FORBIDDEN_PATTERNS="increase.*sleep|add.*more.*sleep|longer.*sleep|increase.*timeout|longer.*timeout|bump.*sleep|change.*sleep.*to|sleep.*to.*[0-9]|sleep.*[0-9]+.*instead"
        ;;
    f11-timeout-flaky)
        # Tests use hardcoded sleep durations that aren't enough on slow CI
        ROOT_PATTERNS="timing|race condition|hardcoded.*sleep|fixed.*sleep|sleep.*(not|isn).*reliable|timing.*(dependent|sensitive|issue|problem)|CI.*(slow|slower|load)|non.deterministic"
        # Proper fixes: polling, wait-for-condition, retry, event-based
        FIX_PATTERNS="poll|wait.*(for|until|condition)|retry|time\\.monotonic|thread.*join|while.*not.*complete|loop.*until|event.*wait|assert.*(eventually|retries)|attempts|backoff|exponential"
        # Forbidden: just increase sleep/timeout values (specific "increase X to Y" phrasing)
        FORBIDDEN_PATTERNS="increase.*sleep|add.*more.*sleep|longer.*sleep|increase.*timeout|longer.*timeout|bump.*sleep|change.*sleep.*to|sleep.*to.*[0-9]|sleep.*[0-9]+.*instead|set.*timeout.*to"
        ;;
    f11-datetime-mock)
        # Tests use datetime.now() / date.today() which change across midnight boundary
        ROOT_PATTERNS="timing|race condition|midnight|time.*(boundary|change|shift)|datetime.*now.*not.*safe|date.*today.*not.*safe|not.*deterministic|side.*effect.*time|time.*(dependent|sensitive)|capture.*time|freeze.*time|mock.*time|time.*of.*day"
        # Proper fixes: inject/freeze time, use freezegun, pass time as parameter
        FIX_PATTERNS="mock.*time|freeze.*time|freezegun|inject.*time|time.*parameter|fixed.*time|time\\.monotonic|patch.*datetime|dependency.*inject|pass.*now.*as|deterministic.*time|datetime.*stub|clock.*mock"
        # Forbidden: just add delay or sleep to avoid midnight
        FORBIDDEN_PATTERNS="increase.*sleep|add.*more.*sleep|sleep.*before|add.*delay|1.second.*sleep|add.*sleep"
        ;;
    *)
        ROOT_PATTERNS="timing|race"
        FIX_PATTERNS="poll|wait|retry"
        FORBIDDEN_PATTERNS="increase.*sleep"
        ;;
esac

# Check 1: Response identifies the timing issue / race condition
if grep -qEi "$ROOT_PATTERNS" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Timing/race issue not identified (pattern: ${ROOT_PATTERNS})" >&2
fi

# Check 2: Response suggests a proper fix (polling, waiting for condition, mock time, etc.)
if grep -qEi "$FIX_PATTERNS" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  No proper fix suggested (pattern: ${FIX_PATTERNS})" >&2
fi

# Check 3: Response does NOT suggest forbidden superficial fixes
# Only check if forbidden pattern appears prominently (in first half of response)
HALF_FILE="$WORK_DIR/response_half.txt"
TOTAL_LINES=$(wc -l < "$STDIN_FILE")
HALF_LINES=$((TOTAL_LINES / 2 + 1))
head -n "$HALF_LINES" "$STDIN_FILE" > "$HALF_FILE"

FORBIDDEN_FOUND=$(grep -cEi "$FORBIDDEN_PATTERNS" "$HALF_FILE" || true)

if [[ "$FORBIDDEN_FOUND" -eq 0 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Suggests superficial fix (more sleep / increase timeout) in first half" >&2
    grep -Ein "$FORBIDDEN_PATTERNS" "$HALF_FILE" >&2 || true
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
