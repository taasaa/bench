# nvidia/nemotron-3-super-120b-a12b:free

> `nvidia/nemotron-3-super-120b-a12b:free` | NVIDIA NIM | FREE | Evaluated 2026-07-07 → 2026-07-07

## Summary

**nvidia/nemotron-3-super-120b-a12b:free** achieves an overall correctness of **89%** across 4 evaluation tasks.
This model demonstrates strong reliability across task categories, making it suitable for production use where accuracy is critical.
Token efficiency is below benchmark (ratio 0.35), tending toward verbose output.
Latency is competitive (ratio 1.09).
This is a **currently free model** (normal price $0.0800/M in, $0.4500/M out), making it cost-optimal for any use case.

**Strengths:** Excels at universal tasks (u17-dirty-workspace-triage, q4-root-cause, q3-answer-the-question).

**Recommended for:** General coding assistance, code review, and automated workflows where cost-efficiency matters.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-07-07 → 2026-07-07 |
| **Tasks** | 4 eval tasks, 16 samples |
| **Provider** | NVIDIA NIM |
| **Hosting** | NVIDIA NIM |
| **Context Window** | 1,000,000 tokens |
| **Pricing** | $0.0800/M in, $0.4500/M out (currently free) |
| **Status** | FREE |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.890 | good |
| **Token Efficiency** | 0.352 | weak |
| **Latency** | 1.089 | excellent |
| **Cost Efficiency** | FREE | excellent |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| f1-multi-file-verify | analysis | hybrid_scorer | 0.681 | 0.465 | 0.987 | FREE |
| q3-answer-the-question | competence | verify_sh | 0.938 | 0.555 | 1.201 | FREE |
| q4-root-cause | execution | hybrid_scorer | 0.942 | 0.225 | 0.662 | FREE |
| u17-dirty-workspace-triage | universal | hybrid_scorer | 1.000 | 0.163 | 1.508 | FREE |

## Strengths & Weaknesses

### Top Tasks (by correctness)
1. **u17-dirty-workspace-triage** — 1.000
1. **q4-root-cause** — 0.942
1. **q3-answer-the-question** — 0.938
1. **f1-multi-file-verify** — 0.681

## Token Usage

- Total input: 50,866
- Total output: 28,228
- Avg input/sample: 3,179
- Avg output/sample: 1,764

