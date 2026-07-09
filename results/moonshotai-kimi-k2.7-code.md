# moonshotai/kimi-k2.7-code

> `moonshotai/kimi-k2.7-code` | API | paid | Evaluated 2026-07-09 → 2026-07-09

## Summary

**moonshotai/kimi-k2.7-code** achieves an overall correctness of **94%** across 2 evaluation tasks.
This model demonstrates strong reliability across task categories, making it suitable for production use where accuracy is critical.
Token efficiency is below benchmark (ratio 0.43), tending toward verbose output.
Latency is competitive (ratio 1.01).
Cost is above the benchmark reference (ratio 0.32).

**Strengths:** Excels at execution tasks (q4-root-cause, q3-answer-the-question).

**Recommended for:** Assisted coding, prototyping, and tasks where a human reviews the output.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-07-09 → 2026-07-09 |
| **Tasks** | 2 eval tasks, 8 samples (1 smoke) |
| **Provider** | API |
| **Hosting** | API |
| **Context Window** | N/A tokens |
| **Pricing** | $0.7200/M in, $3.5000/M out |
| **Status** | paid |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.940 | excellent |
| **Token Efficiency** | 0.432 | weak |
| **Latency** | 1.014 | excellent |
| **Cost Efficiency** | 0.323 | weak |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| q3-answer-the-question | competence | verify_sh | 0.938 | 0.529 | 1.220 | 0.248 |
| q4-root-cause | execution | hybrid_scorer | 0.942 | 0.335 | 0.808 | 0.398 |

## Strengths & Weaknesses

### Top Tasks (by correctness)
1. **q4-root-cause** — 0.942
1. **q3-answer-the-question** — 0.938

## Token Usage

- Total input: 5,708
- Total output: 8,098
- Avg input/sample: 713
- Avg output/sample: 1,012

