# nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free

> `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | NVIDIA NIM | FREE | Evaluated 2026-07-07 → 2026-07-07

## Summary

**nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free** achieves an overall correctness of **84%** across 3 evaluation tasks.
Performance is solid for most coding tasks, though some edge cases in error handling and verification reveal room for improvement.
Token efficiency is below benchmark (ratio 0.49), tending toward verbose output.
Latency is competitive (ratio 1.19).
This is a **currently free model** (normal price $0.2500/M in, $0.5000/M out), making it cost-optimal for any use case.

**Strengths:** Excels at competence tasks (q3-answer-the-question, q4-root-cause, f1-multi-file-verify).

**Recommended for:** General coding assistance, code review, and automated workflows where cost-efficiency matters.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-07-07 → 2026-07-07 |
| **Tasks** | 3 eval tasks, 12 samples |
| **Provider** | NVIDIA NIM |
| **Hosting** | NVIDIA NIM |
| **Context Window** | 256,000 tokens |
| **Pricing** | $0.2500/M in, $0.5000/M out (currently free) |
| **Status** | FREE |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.838 | good |
| **Token Efficiency** | 0.489 | weak |
| **Latency** | 1.187 | excellent |
| **Cost Efficiency** | FREE | excellent |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| f1-multi-file-verify | analysis | hybrid_scorer | 0.750 | 0.732 | 1.473 | FREE |
| q3-answer-the-question | competence | verify_sh | 0.938 | 0.538 | 1.608 | FREE |
| q4-root-cause | execution | hybrid_scorer | 0.825 | 0.199 | 0.480 | FREE |

## Strengths & Weaknesses

### Top Tasks (by correctness)
1. **q3-answer-the-question** — 0.938
1. **q4-root-cause** — 0.825
1. **f1-multi-file-verify** — 0.750

## Token Usage

- Total input: 13,738
- Total output: 19,854
- Avg input/sample: 1,144
- Avg output/sample: 1,654

