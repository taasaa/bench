#!/usr/bin/env bash
# Run a custom task list one task at a time, with BREAK_SECS sleep between tasks.
# Per-task invocation gives ACTIVE inter-task cooling for rate-limited proxies.
#
# Usage:
#   scripts/run_eval_tasklist.sh <model-alias> <break-secs> <task-list-file> [out-tag]
#
# Behavior:
#   - Reads task names (one per line) from <task-list-file>
#   - For each: bench_cli run --task <name> with --no-resume (clean per-task run)
#   - --max-samples 1, --max-retries 2, -j 1
#   - Tail of run log printed after each task for active monitoring
#   - On any non-zero exit: log and continue (don't abort the loop)
set -uo pipefail

MODEL="${1:?model alias required}"
BREAK_SECS="${2:?break-secs required}"
TASK_LIST_FILE="${3:?task-list file required}"
TAG="${4:-$(echo "$MODEL" | tr '/' '-')-$(date +%Y%m%dT%H%M%S)}"

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$REPO/logs"
RUN_LOG="$LOG_DIR/_runs/${TAG}.out"
mkdir -p "$LOG_DIR/_runs"

cd "$REPO"

# Read task list (POSIX-portable)
TASKS=()
while IFS= read -r line; do
    line=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    [ -z "$line" ] && continue
    TASKS+=("$line")
done < "$TASK_LIST_FILE"
TOTAL=${#TASKS[@]}

echo "=== run_eval_tasklist ==="
echo "model=$MODEL  break_secs=$BREAK_SECS  tasks=$TOTAL"
echo "out=$RUN_LOG"
date
echo "task list:"; printf '  %s\n' "${TASKS[@]}"
echo

i=0
for TASK in "${TASKS[@]}"; do
    i=$((i+1))
    {
        echo "=== [$i/$TOTAL] $(date '+%H:%M:%S') task=$TASK ==="
        .venv/bin/python -m bench_cli run \
            --tier full \
            --model "$MODEL" \
            --task "$TASK" \
            --no-tui \
            --max-retries 2 \
            -j 1 \
            --max-samples 1 \
            --no-resume
        echo "=== [$i/$TOTAL] $(date '+%H:%M:%S') task=$TASK done exit=$? ==="
    } >> "$RUN_LOG" 2>&1

    # Print short progress summary (last 8 lines of the run log)
    echo "--- last 8 lines ---"
    tail -8 "$RUN_LOG" | sed 's/^/  /'

    # Snapshot the run log per task (optional but useful)
    cp "$RUN_LOG" "$LOG_DIR/_runs/${TAG}.task-${TASK}.out" 2>/dev/null

    if [ "$i" -lt "$TOTAL" ]; then
        echo ">>> sleeping ${BREAK_SECS}s before next task"
        sleep "$BREAK_SECS"
    fi
done

echo "=== all done at $(date) ==="
echo "final tail:"
tail -30 "$RUN_LOG"
