# xiaomi/mimo-v2.5-pro

> `xiaomi/mimo-v2.5-pro` | API | paid | Evaluated 2026-07-09 → 2026-07-09

## Summary

**xiaomi/mimo-v2.5-pro** achieves an overall correctness of **93%** across 4 evaluation tasks.
This model demonstrates strong reliability across task categories, making it suitable for production use where accuracy is critical.
Token efficiency is below benchmark (ratio 0.36), tending toward verbose output.
Latency is competitive (ratio 1.27).
Cost efficiency is strong (ratio 1.78), cheaper than the benchmark reference.

**Strengths:** Excels at execution tasks (q4-root-cause, u17-dirty-workspace-triage, q3-answer-the-question).

**Recommended for:** General coding assistance, code review, and automated workflows where cost-efficiency matters.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-07-09 → 2026-07-09 |
| **Tasks** | 4 eval tasks, 16 samples |
| **Provider** | API |
| **Hosting** | API |
| **Context Window** | N/A tokens |
| **Pricing** | $0.4350/M in, $0.8700/M out |
| **Status** | paid |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.934 | excellent |
| **Token Efficiency** | 0.363 | weak |
| **Latency** | 1.267 | excellent |
| **Cost Efficiency** | 1.779 | excellent |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| f1-multi-file-verify | analysis | hybrid_scorer | 0.819 | 0.440 | 0.777 | 1.885 |
| q3-answer-the-question | competence | verify_sh | 0.938 | 0.410 | 1.620 | 1.595 |
| q4-root-cause | execution | hybrid_scorer | 1.000 | 0.356 | 0.940 | 2.019 |
| u17-dirty-workspace-triage | universal | hybrid_scorer | 0.981 | 0.246 | 1.732 | 1.617 |

## Strengths & Weaknesses

### Top Tasks (by correctness)
1. **q4-root-cause** — 1.000
1. **u17-dirty-workspace-triage** — 0.981
1. **q3-answer-the-question** — 0.938
1. **f1-multi-file-verify** — 0.819

## Token Usage

- Total input: 28,147
- Total output: 22,166
- Avg input/sample: 1,759
- Avg output/sample: 1,385

