#!/usr/bin/env bash
# Run a full eval one task at a time, with BREAK_SECS sleep between tasks.
# Per-task invocation gives ACTIVE inter-task cooling for rate-limited proxies.
#
# Usage:
#   scripts/run_eval_with_breaks.sh <model-alias> <break-secs> [out-tag]
#
# Behavior:
#   - Lists tier=full tasks once, then for each: bench_cli run --task <name>
#   - --no-resume only on first task per name (clear stale partial from prior run)
#   - --max-samples 1, --max-retries 4, -j 1
#   - Tail of run log printed after each task for active monitoring
#   - On any non-zero exit: log and continue (don't abort the loop)
set -uo pipefail

MODEL="${1:?model alias required (e.g. openai/deepseek-v4-flash)}"
BREAK_SECS="${2:?break-secs required (e.g. 180)}"
TAG="${3:-$(echo "$MODEL" | tr '/' '-')-$(date +%Y%m%dT%H%M%S)}"

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$REPO/logs"
RUN_LOG="$LOG_DIR/_runs/${TAG}.out"
mkdir -p "$LOG_DIR/_runs"

cd "$REPO"

# Collect task names from --list-tasks.  Each line is 'tasks/<cat>/<name>/task.py'.
# Strip the trailing /task.py and the leading tasks/<cat>/ to get the task name.
TASKS=$(
    .venv/bin/python -m bench_cli run --list-tasks --tier full 2>/dev/null \
    | awk '/tasks\//{print $1}' \
    | sed -E 's|^tasks/[a-z]+/||; s|/task\.py$||'
)

TOTAL=$(echo "$TASKS" | wc -l | tr -d ' ')
echo "=== run_eval_with_breaks ==="
echo "model=$MODEL  break_secs=$BREAK_SECS  tasks=$TOTAL"
echo "out=$RUN_LOG"
date
echo "task list:"; echo "$TASKS" | sed 's/^/  /'
echo

i=0
for TASK in $TASKS; do
    i=$((i+1))
    # Per-task log so we can tail one task's output without losing earlier context
    TASK_LOG="$LOG_DIR/_runs/${TAG}.task-${TASK}.out"
    {
        echo "=== [$i/$TOTAL] $(date '+%H:%M:%S') task=$TASK ==="
        .venv/bin/python -m bench_cli run \
            --tier full \
            --model "$MODEL" \
            --task "$TASK" \
            --no-tui \
            --max-retries 4 \
            -j 1 \
            --max-samples 1 \
            --no-resume
        echo "=== [$i/$TOTAL] $(date '+%H:%M:%S') task=$TASK done exit=$? ==="
    } >> "$RUN_LOG" 2>&1

    # Print short progress summary (last 12 lines of the per-task tail)
    echo "--- last 12 lines of $TASK ---"
    tail -12 "$RUN_LOG" | sed 's/^/  /'

    # Per-task log mirror (just the tail of the run log so far)
    cp "$RUN_LOG" "$TASK_LOG"

    if [ "$i" -lt "$TOTAL" ]; then
        echo ">>> sleeping ${BREAK_SECS}s before next task"
        sleep "$BREAK_SECS"
    fi
done

echo "=== all done at $(date) ==="
echo "final tail:"
tail -30 "$RUN_LOG"
