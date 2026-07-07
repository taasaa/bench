# z-ai/glm-5.1

> `z-ai/glm-5.1` | API | paid | Evaluated 2026-06-16 → 2026-06-16

## Summary

**z-ai/glm-5.1** achieves an overall correctness of **41%** across 4 evaluation tasks.
This model struggles with complex multi-step reasoning and should be paired with strong verification layers in any production pipeline.
Token efficiency is reasonable (ratio 1.26), producing concise responses. 
Latency is fast (ratio 16.11).
Cost efficiency is strong (ratio 1.35), cheaper than the benchmark reference.

**Strengths:** Excels at analysis tasks (f10-env-mismatch, f21-liars-codebase, f1-multi-file-verify).

**Recommended for:** Basic code generation with human oversight. Not suitable for autonomous agent use.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-06-16 → 2026-06-16 |
| **Tasks** | 4 eval tasks, 18 samples |
| **Provider** | API |
| **Hosting** | API |
| **Context Window** | 131,072 tokens |
| **Pricing** | $0.9660/M in, $3.0360/M out |
| **Status** | paid |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.410 | weak |
| **Token Efficiency** | 1.259 | excellent |
| **Latency** | 16.106 | excellent |
| **Cost Efficiency** | 1.347 | excellent |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| f1-multi-file-verify | analysis | hybrid_scorer | 0.525 | 1.467 | 13.147 | 0.738 |
| f10-env-mismatch | analysis | hybrid_scorer | 0.569 | 1.265 | 15.861 | 2.943 |
| f19-admit-uncertainty | analysis | llm_judge | 0.000 | 0.856 | 11.609 | 0.655 |
| f21-liars-codebase | analysis | hybrid_scorer | 0.544 | 1.448 | 23.809 | 1.050 |

## Strengths & Weaknesses

### Top Tasks (by correctness)
1. **f10-env-mismatch** — 0.569
1. **f21-liars-codebase** — 0.544
1. **f1-multi-file-verify** — 0.525
1. **f19-admit-uncertainty** — 0.000

## Token Usage

- Total input: 9,366
- Total output: 14,558
- Avg input/sample: 520
- Avg output/sample: 808

