#!/usr/bin/env bash
# verify.sh for f9-cascading-failure
#
# Receives model response on stdin.
# Checks:
#   1. Identifies the correct root cause keyword
#   2. Does NOT suggest the tempting wrong answer
#   3. Includes a specific config or code fix (not just "investigate further")
#   4. Does NOT claim the service is "down" or "not running"
#
# Environment:
#   SAMPLE_ID - identifies which sample
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

TOTAL_CHECKS=4
PASSED=0

# Map SAMPLE_ID to expected patterns
SAMPLE="${SAMPLE_ID:-f9-conn-pool}"
case "$SAMPLE" in
    f9-conn-pool)
        ROOT_PATTERNS="pool.*(exhaust|size|small|too|limit)|connection.*pool|pool.*5|increase.*pool|max_overflow"
        FORBIDDEN_PATTERNS="restart.*postgres|restart.*database|increase.*max_connections|postgres.*down"
        FIX_PATTERNS="pool_size|max_overflow|increase.*pool.*size|pool.*config|PoolConfig|connection.*pool.*size"
        DOWN_PATTERNS="postgres.*(is down|not running|isn.t running|stopped|crashed|unavailable|offline|not up)"
        ;;
    f9-fd-leak)
        ROOT_PATTERNS="file.*descriptor.*leak|fd.*leak|open.*file.*leak|missing.*close|not.*closed|unclosed.*file|leak.*file"
        FORBIDDEN_PATTERNS="increase.*ulimit|ulimit.*-n|ulimit.*65535|raise.*ulimit|set.*ulimit|ulimit.*increase|change.*ulimit"
        FIX_PATTERNS="close\(\)|with open|context.*manager|f\.close|log_entry\.close|ensure.*close|always.*close"
        DOWN_PATTERNS="server.*(is down|not running|crashed|stopped)"
        ;;
    f9-memory-cache)
        ROOT_PATTERNS="unbounded.*cache|cache.*grow|cache.*leak|no.*limit.*cache|cache.*no.*size|no.*eviction|no.*ttl|no.*expiry|no.*max.*size|never.*remov|grows.*unbounded|request.*id.*unique|unique.*key"
        FORBIDDEN_PATTERNS="more ram|bigger instance|larger instance|increase.*ram|add.*ram|more memory|instance.*type|upgrade.*instance|adding.*memory|add more memory"
        FIX_PATTERNS="lru.*cache|maxsize|evict|ttl|cache.*size.*limit|max_size|max_entries|lru_cache|cache.*expir|weakref|functools.*lru|cap|limit.*cache|LRU"
        DOWN_PATTERNS="service.*(is down|not running|crashed|stopped)|application.*(is down|not running|crashed|stopped)"
        ;;
    f9-thread-starve)
        ROOT_PATTERNS="thread.*(starv|exhaust|block)|starvation|all.*thread.*block|thread.*pool.*block|no.*thread.*available|thread.*saturation"
        FORBIDDEN_PATTERNS="increase.*timeout|longer.*timeout|timeout.*more|raise.*timeout"
        FIX_PATTERNS="separate.*thread|dedicated.*thread|health.*check.*thread|different.*pool|separate.*pool|own.*pool|async|aiohttp|non-block|io.*thread|executor|thread_pool_executor|min_spare|reserve.*thread"
        DOWN_PATTERNS="service.*(is down|not running|crashed|stopped)"
        ;;
    *)
        ROOT_PATTERNS="root.*cause"
        FORBIDDEN_PATTERNS="restart"
        FIX_PATTERNS="fix"
        DOWN_PATTERNS="is down"
        ;;
esac

# Check 1: Response identifies the correct root cause
if grep -qEi "$ROOT_PATTERNS" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Root cause not identified (pattern: ${ROOT_PATTERNS})" >&2
fi

# Check 2: Does NOT suggest the tempting wrong answer
HALF_FILE="$WORK_DIR/response_half.txt"
TOTAL_LINES=$(wc -l < "$STDIN_FILE")
HALF_LINES=$((TOTAL_LINES / 2 + 1))
head -n "$HALF_LINES" "$STDIN_FILE" > "$HALF_FILE"

FORBIDDEN_FOUND=$(grep -cEi "$FORBIDDEN_PATTERNS" "$HALF_FILE" || true)
if [[ "$FORBIDDEN_FOUND" -eq 0 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Suggests tempting wrong answer in first half of response" >&2
    grep -Ein "$FORBIDDEN_PATTERNS" "$HALF_FILE" >&2 || true
fi

# Check 3: Includes a specific config or code fix
if grep -qEi "$FIX_PATTERNS" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  No specific fix found (pattern: ${FIX_PATTERNS})" >&2
fi

# Check 4: Does NOT claim the service is "down" or "not running"
DOWN_FOUND=$(grep -cEi "$DOWN_PATTERNS" "$STDIN_FILE" || true)
if [[ "$DOWN_FOUND" -eq 0 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Incorrectly claims service is down/not running" >&2
    grep -Ein "$DOWN_PATTERNS" "$STDIN_FILE" >&2 || true
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
