#!/usr/bin/env bash
set -e
echo "Starting Eval Batch Run..."

TASKS=(
    "f29-infra-protocol-bypass"
    "f30-forward-compatibility"
    "f31-run-at-load-carveout"
    "f32-latency-budget"
    "f33-circular-ui"
    "f34-lexical-sort"
    "f35-per-session-scope"
    "f36-enum-mismatch"
    "f37-test-baseline"
    "f38-ambiguity-trap"
)

# Replace hyphens with underscores for the bench_cli task argument
for task in "${TASKS[@]}"; do
    task_arg="${task//-/_}"
    
    echo "=========================================================="
    echo "Running Task: $task with go-deepseek-v4-flash (Not Smart)"
    echo "=========================================================="
    .venv/bin/python -m bench_cli run --tier full --task "$task" --model openai/go-deepseek-v4-flash --no-compare || true

    echo "=========================================================="
    echo "Running Task: $task with glm-5.2 (Smart)"
    echo "=========================================================="
    .venv/bin/python -m bench_cli run --tier full --task "$task" --model openai/glm-5.2 --no-compare || true
done

echo "=========================================================="
echo "Generating Final Comparison Report"
echo "=========================================================="
.venv/bin/python -m bench_cli compare > final_eval_report.txt

echo "Batch completed successfully."
