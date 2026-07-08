# nvidia/nemotron-3-super-120b-a12b:free

> `nvidia/nemotron-3-super-120b-a12b:free` | NVIDIA NIM | FREE | Evaluated 2026-07-07 → 2026-07-08

## Summary

**nvidia/nemotron-3-super-120b-a12b:free** achieves an overall correctness of **84%** across 4 evaluation tasks.
Performance is solid for most coding tasks, though some edge cases in error handling and verification reveal room for improvement.
Token efficiency is below benchmark (ratio 0.36), tending toward verbose output.
Latency is competitive (ratio 1.54).
This is a **currently free model** (normal price $0.0800/M in, $0.4500/M out), making it cost-optimal for any use case.

**Strengths:** Excels at competence tasks (q3-answer-the-question, q4-root-cause, f1-multi-file-verify).

**Recommended for:** General coding assistance, code review, and automated workflows where cost-efficiency matters.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-07-07 → 2026-07-08 |
| **Tasks** | 4 eval tasks, 16 samples |
| **Provider** | NVIDIA NIM |
| **Hosting** | NVIDIA NIM |
| **Context Window** | 1,000,000 tokens |
| **Pricing** | $0.0800/M in, $0.4500/M out (currently free) |
| **Status** | FREE |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.841 | good |
| **Token Efficiency** | 0.364 | weak |
| **Latency** | 1.542 | excellent |
| **Cost Efficiency** | 2.357 | excellent |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| f1-multi-file-verify | analysis | hybrid_scorer | 0.794 | 0.526 | 1.290 | 4.231 |
| q3-answer-the-question | competence | verify_sh | 0.938 | 0.540 | 2.802 | 1.907 |
| q4-root-cause | execution | hybrid_scorer | 0.883 | 0.195 | 0.648 | 1.282 |
| u17-dirty-workspace-triage | universal | hybrid_scorer | 0.750 | 0.195 | 1.426 | 2.008 |

## Strengths & Weaknesses

### Top Tasks (by correctness)
1. **q3-answer-the-question** — 0.938
1. **q4-root-cause** — 0.883
1. **f1-multi-file-verify** — 0.794
1. **u17-dirty-workspace-triage** — 0.750

## Token Usage

- Total input: 45,725
- Total output: 27,642
- Avg input/sample: 2,857
- Avg output/sample: 1,727

