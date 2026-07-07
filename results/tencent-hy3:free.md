# tencent/hy3:free

> `tencent/hy3:free` | API | FREE | Evaluated 2026-07-07 → 2026-07-07

## Summary

**tencent/hy3:free** achieves an overall correctness of **84%** across 4 evaluation tasks.
Performance is solid for most coding tasks, though some edge cases in error handling and verification reveal room for improvement.
Token efficiency is below benchmark (ratio 0.18), tending toward verbose output.
Latency is slower than benchmark (ratio 0.86).
This is a **free model** ($0/M in, $0/M out), making it cost-optimal for any use case.

**Strengths:** Excels at universal tasks (u17-dirty-workspace-triage, q3-answer-the-question, q4-root-cause).

**Recommended for:** General coding assistance, code review, and automated workflows where cost-efficiency matters.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-07-07 → 2026-07-07 |
| **Tasks** | 4 eval tasks, 16 samples |
| **Provider** | API |
| **Hosting** | API |
| **Context Window** | N/A tokens |
| **Pricing** | $0.00 (free) |
| **Status** | FREE |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.836 | good |
| **Token Efficiency** | 0.179 | weak |
| **Latency** | 0.862 | good |
| **Cost Efficiency** | FREE | excellent |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| f1-multi-file-verify | analysis | hybrid_scorer | 0.581 | 0.262 | 0.415 | FREE |
| q3-answer-the-question | competence | verify_sh | 0.938 | 0.088 | 0.376 | FREE |
| q4-root-cause | execution | hybrid_scorer | 0.825 | 0.128 | 0.405 | FREE |
| u17-dirty-workspace-triage | universal | hybrid_scorer | 1.000 | 0.238 | 2.253 | FREE |

## Strengths & Weaknesses

### Top Tasks (by correctness)
1. **u17-dirty-workspace-triage** — 1.000
1. **q3-answer-the-question** — 0.938
1. **q4-root-cause** — 0.825
1. **f1-multi-file-verify** — 0.581

## Token Usage

- Total input: 25,373
- Total output: 72,125
- Avg input/sample: 1,585
- Avg output/sample: 4,507

