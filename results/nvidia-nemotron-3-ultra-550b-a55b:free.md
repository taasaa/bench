# nvidia/nemotron-3-ultra-550b-a55b:free

> `nvidia/nemotron-3-ultra-550b-a55b:free` | NVIDIA NIM | FREE | Evaluated 2026-07-07 → 2026-07-07

## Summary

**nvidia/nemotron-3-ultra-550b-a55b:free** achieves an overall correctness of **90%** across 4 evaluation tasks.
This model demonstrates strong reliability across task categories, making it suitable for production use where accuracy is critical.
Token efficiency is below benchmark (ratio 0.53), tending toward verbose output.
Latency is slower than benchmark (ratio 0.42).
This is a **free model** ($0/M in, $0/M out), making it cost-optimal for any use case.

**Strengths:** Excels at universal tasks (u17-dirty-workspace-triage, q4-root-cause, q3-answer-the-question).

**Recommended for:** General coding assistance, code review, and automated workflows where cost-efficiency matters.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-07-07 → 2026-07-07 |
| **Tasks** | 4 eval tasks, 16 samples |
| **Provider** | NVIDIA NIM |
| **Hosting** | NVIDIA NIM |
| **Context Window** | N/A tokens |
| **Pricing** | $0.00 (free) |
| **Status** | FREE |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.895 | good |
| **Token Efficiency** | 0.528 | weak |
| **Latency** | 0.423 | weak |
| **Cost Efficiency** | FREE | excellent |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| f1-multi-file-verify | analysis | hybrid_scorer | 0.700 | 0.474 | 0.232 | FREE |
| q3-answer-the-question | competence | verify_sh | 0.938 | 1.089 | 0.583 | FREE |
| q4-root-cause | execution | hybrid_scorer | 0.942 | 0.460 | 0.490 | FREE |
| u17-dirty-workspace-triage | universal | hybrid_scorer | 1.000 | 0.088 | 0.385 | FREE |

## Strengths & Weaknesses

### Top Tasks (by correctness)
1. **u17-dirty-workspace-triage** — 1.000
1. **q4-root-cause** — 0.942
1. **q3-answer-the-question** — 0.938
1. **f1-multi-file-verify** — 0.700

## Token Usage

- Total input: 74,503
- Total output: 21,054
- Avg input/sample: 4,656
- Avg output/sample: 1,315

