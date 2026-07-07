# deepseek-ai/deepseek-v4-flash

> `deepseek-ai/deepseek-v4-flash` | API | paid | Evaluated 2026-06-19 → 2026-06-19

## Summary

**deepseek-ai/deepseek-v4-flash** achieves an overall correctness of **82%** across 2 evaluation tasks.
Performance is solid for most coding tasks, though some edge cases in error handling and verification reveal room for improvement.
Token efficiency is below benchmark (ratio 0.41), tending toward verbose output.
Latency is slower than benchmark (ratio 0.87).
Cost efficiency is strong (ratio 40.31), cheaper than the benchmark reference.

**Strengths:** Excels at analysis tasks (f1-multi-file-verify, f10-env-mismatch).

**Recommended for:** General coding assistance, code review, and automated workflows where cost-efficiency matters.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-06-19 → 2026-06-19 |
| **Tasks** | 2 eval tasks, 8 samples |
| **Provider** | API |
| **Hosting** | API |
| **Context Window** | 1,000,000 tokens |
| **Pricing** | N/A |
| **Status** | paid |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.825 | good |
| **Token Efficiency** | 0.413 | weak |
| **Latency** | 0.870 | good |
| **Cost Efficiency** | 40.308 | excellent |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| f1-multi-file-verify | analysis | hybrid_scorer | 0.838 | 0.548 | 1.131 | 13.974 |
| f10-env-mismatch | analysis | hybrid_scorer | 0.812 | 0.278 | 0.609 | 66.641 |

## Strengths & Weaknesses

### Top Tasks (by correctness)
1. **f1-multi-file-verify** — 0.838
1. **f10-env-mismatch** — 0.812

## Token Usage

- Total input: 13,507
- Total output: 20,324
- Avg input/sample: 1,688
- Avg output/sample: 2,540

