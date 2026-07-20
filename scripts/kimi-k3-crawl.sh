#!/usr/bin/env bash
# Crawl eval for kimi-k3 task-by-task with sleep between each.
# Pattern: --no-resume per task + --max-retries 4 (tight rate limit on Kimi Code).
# Pre-skips the 4 viability tasks already scored (q3/q4/f1/u17).
#
# Usage:
#   scripts/kimi-k3-crawl.sh <break-secs> [out-tag]
#
# Reads task names (one per line) from scripts/kimi-k3-crawl-tasks.txt.
# On non-zero per-task exit: log and continue (don't abort the loop).
set -uo pipefail

MODEL="openai/kimi-k3"
BREAK_SECS="${1:?break-secs required (e.g. 90)}"
TAG="${2:-kimi-k3-crawl-$(date +%Y%m%dT%H%M%S)}"

REPO="$(cd "$(dirname "$0")/.." && pwd)"
TASK_LIST="$REPO/scripts/kimi-k3-crawl-tasks.txt"
LOG_DIR="$REPO/logs"
RUN_LOG="$LOG_DIR/_runs/${TAG}.out"
mkdir -p "$LOG_DIR/_runs"

cd "$REPO"

TASKS=()
while IFS= read -r line; do
    line=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    [ -z "$line" ] && continue
    TASKS+=("$line")
done < "$TASK_LIST"
TOTAL=${#TASKS[@]}

echo "=== kimi-k3 crawl ==="
echo "model=$MODEL  break_secs=$BREAK_SECS  tasks=$TOTAL"
echo "out=$RUN_LOG"
echo "skipped (already-success): q3-answer-the-question, q4-root-cause, f1-multi-file-verify, u17-dirty-workspace-triage"
date
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
            --max-retries 4 \
            -j 1 \
            --max-samples 1 \
            --no-resume
        echo "=== [$i/$TOTAL] $(date '+%H:%M:%S') task=$TASK done exit=$? ==="
    } >> "$RUN_LOG" 2>&1

    echo "--- last 8 lines of $TASK ---"
    tail -8 "$RUN_LOG" | sed 's/^/  /'

    if [ "$i" -lt "$TOTAL" ]; then
        echo ">>> sleeping ${BREAK_SECS}s before next task"
        sleep "$BREAK_SECS"
    fi
done

echo "=== all done at $(date) ==="
tail -30 "$RUN_LOG"
