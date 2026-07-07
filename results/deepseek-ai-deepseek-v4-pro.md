# deepseek-ai/deepseek-v4-pro

> `deepseek-ai/deepseek-v4-pro` | API | paid | Evaluated 2026-06-19 → 2026-06-19

## Summary

**deepseek-ai/deepseek-v4-pro** achieves an overall correctness of **96%** across 2 evaluation tasks.
This model demonstrates strong reliability across task categories, making it suitable for production use where accuracy is critical.
Token efficiency is below benchmark (ratio 0.33), tending toward verbose output.
Latency is slower than benchmark (ratio 0.78).
Cost efficiency is strong (ratio 2.89), cheaper than the benchmark reference.

**Strengths:** Excels at analysis tasks (f19-admit-uncertainty, q4-root-cause).

**Recommended for:** General coding assistance, code review, and automated workflows where cost-efficiency matters.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-06-19 → 2026-06-19 |
| **Tasks** | 2 eval tasks, 8 samples |
| **Provider** | API |
| **Hosting** | API |
| **Context Window** | N/A tokens |
| **Pricing** | N/A |
| **Status** | paid |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.961 | excellent |
| **Token Efficiency** | 0.325 | weak |
| **Latency** | 0.779 | good |
| **Cost Efficiency** | 2.888 | excellent |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| f19-admit-uncertainty | analysis | llm_judge | 1.000 | 0.240 | 0.530 | 2.458 |
| q4-root-cause | execution | hybrid_scorer | 0.923 | 0.410 | 1.029 | 3.319 |

## Strengths & Weaknesses

### Top Tasks (by correctness)
1. **f19-admit-uncertainty** — 1.000
1. **q4-root-cause** — 0.923

## Token Usage

- Total input: 10,650
- Total output: 12,348
- Avg input/sample: 1,331
- Avg output/sample: 1,543

