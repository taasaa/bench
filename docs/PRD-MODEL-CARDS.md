**Status:** draft
**Project:** Bench
**Owner:** Michael Mazyar

## Problem Statement

7 models have been evaluated (32+ tasks, 4-pillar scoring) but results exist only as binary `.eval` log files and `bench compare` terminal output. There is no human-readable, per-model summary that shows what was tested, how the model performed, and key tradeoffs at a glance. Results need a `results/` directory with one markdown model card per model.

## Models with eval data

| # | Bench Alias | Real Model | Provider | Eval Date |
|---|-------------|-----------|----------|-----------|
| 1 | `openai/default` | MiniMax M2.7 | MiniMax direct | 2026-04-16 → 04-18 |
| 2 | `openai/qwen-local` | Qwen 3.5 35B-A3B (abliterated, LM Studio) | Local | 2026-04-17 → 04-20 |
| 3 | `openai/gemma-4-26-local` | Gemma 4 26B-A4B (LM Studio) | Local | 2026-04-20 |
| 4 | `openai/nvidia-devstral` | Devstral 2 123B (NVIDIA NIM) | NVIDIA | 2026-04-18 → 04-19 |
| 5 | `openai/nvidia-mistral-small4` | Mistral Small 4 119B (NVIDIA NIM) | NVIDIA | 2026-04-17 → 04-19 |
| 6 | `openai/nvidia-nemotron-30b` | Nemotron 3 Nano 30B-A3B (NVIDIA NIM) | NVIDIA | 2026-04-18 → 04-19 |
| 7 | `openai/nvidia-qwen-next` | Qwen 3 Next 80B-A3B (NVIDIA NIM) | NVIDIA | 2026-04-18 → 04-19 |

## Success Criteria

1. **`results/` directory created** with 7 markdown model card files — verify by: `ls results/*.md | wc -l` returns 7
2. **Cards named by OpenRouter model slug** (e.g. `results/minimax-minimax-m2.7.md`, `results/qwen-qwen3.5-35b-a3b.md`) — verify by: file listing
3. **Each card includes all 4 pillar averages** (correctness, token efficiency, latency, cost) — verify by: grep for pillar names in each file
4. **Each card includes per-task breakdown table** with task name, pillar, scorer type, and score — verify by: each file contains a markdown table with 30+ rows
5. **Each card includes model metadata** (provider, hosting, context window, pricing, free/paid) — verify by: grep for metadata fields
6. **Each card includes an LLM-written summary** describing strengths, weaknesses, and recommended use cases — verify by: `## Summary` section present with substantive prose (not boilerplate)
7. **Cards auto-generated after model eval run** — verify by: `bench run` triggers card generation as a post-run step
8. **Existing cards updated on re-run** — verify by: run eval twice, card file timestamp changes, scores reflect latest run
9. **Data sourced from eval logs** (not hardcoded) — verify by: script reads `.eval` files programmatically

## Implementation Approach

### Part A: Card generation logic (`bench_cli/results.py`)

A module that:

1. Scans `logs/*.eval` files, groups by model
2. For each model, deduplicates to latest run per task (by filename date prefix)
3. Resolves bench alias → OpenRouter model ID via LiteLLM config
4. Computes 4-pillar averages across tasks
5. Builds per-task table with pillar classification
6. Generates LLM summary via the judge model (`openai/judge`) describing the model's profile
7. Generates a markdown model card
8. Writes to `results/{openrouter-slug}.md`

### Part B: Auto-generation hook in `bench_cli/run.py`

After eval completes (in the `run` command's post-run phase):

1. Call `generate_model_cards(model=evaluated_model)` from `results.py`
2. If card already exists: overwrite with latest data (card is always a snapshot of latest run)
3. If card doesn't exist: create new card

### Part C: CLI command for manual generation

`python -m bench_cli results generate` — regenerates all cards from all eval logs.

### Model card structure

```markdown
# {OpenRouter Model Name}

> `openai/{alias}` | {Provider} | {free/paid} | Evaluated {date}

## Summary

{2-3 paragraph LLM-generated summary covering: what this model is good at,
where it struggles, what use cases it's recommended for, how it compares
to peers at similar price points. Written by the judge model based on
per-task scores.}

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | {date range} |
| **Tasks** | {n} tasks, {n} samples |
| **Provider** | {provider} |
| **Hosting** | {local/NVIDIA NIM/API} |
| **Context Window** | {tokens} |
| **Pricing** | ${in}/M in, ${out}/M out |
| **Status** | {free/paid} |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | {0.xx} | {excellent/good/fair/weak} |
| **Token Efficiency** | {ratio} | {excellent/good/fair/weak} |
| **Latency** | {ratio} | {excellent/good/fair/weak} |
| **Cost Efficiency** | {ratio or FREE} | {excellent/good/fair/weak} |

> Rating bands: excellent ≥0.90, good ≥0.75, fair ≥0.60, weak <0.60
> Ratio interpretation: >1.0 = better than benchmark, <1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| ... | ... | ... | ... | ... | ... | ... |

## Strengths & Weaknesses

### Top 5 Tasks (by correctness)
1. {task} — {score}

### Bottom 5 Tasks (by correctness)
1. {task} — {score}

## Token Usage

- Total input: {tokens:,}
- Total output: {tokens:,}
- Avg input/sample: {tokens}
- Avg output/sample: {tokens}
```

### File naming convention

Named by OpenRouter slug (not bench alias):
- `openai/default` → `results/minimax-minimax-m2.7.md`
- `openai/qwen-local` → `results/qwen-qwen3.5-35b-a3b.md`
- `openai/gemma-4-26-local` → `results/google-gemma-4-26b-a4b-it.md`
- `openai/nvidia-devstral` → `results/mistralai-devstral-2-123b-instruct-2512.md`
- `openai/nvidia-mistral-small4` → `results/mistralai-mistral-small-4-119b-2603.md`
- `openai/nvidia-nemotron-30b` → `results/nvidia-nemotron-3-nano-30b-a3b.md`
- `openai/nvidia-qwen-next` → `results/qwen-qwen3-next-80b-a3b-instruct.md`

## Edge Cases

- **Free models** (qwen-local, gemma-4-26-local): cost ratio shows "FREE", pricing shows "$0.00"
- **Smoke tasks** (smoke, agent_smoke): no scorer data — omit from per-task table, note in overview
- **NaN scores**: time_ratio_scorer sometimes NaN for fast tasks — show "—" in table
- **Multiple runs of same task**: keep latest only (by filename date prefix)
- **Card already exists**: overwrite entirely — card is always a fresh snapshot of latest data
- **LLM summary generation failure**: fall back to a mechanical summary (top/bottom tasks + pillar ratings), don't block card generation
- **Model not in OpenRouter catalog** (local models): use LiteLLM config model name as fallback slug

## Anti-Patterns

- Don't hardcode any scores or model data — the script must read from `.eval` files
- Don't duplicate the compare.py logic — import from `bench_cli.compare` or `bench_cli.pricing` where possible
- Don't create a static HTML viewer — markdown files only
- Don't make LLM summary a hard dependency — card generation must work even if judge model is down

## Test Plan

1. Run `python -m bench_cli results generate` — verify 7 `.md` files in `results/`
2. Spot-check one card against `bench compare` output — pillar averages must match within ±0.01
3. Verify all 32 tasks appear in per-task table for models that ran full suite
4. Verify free models show "FREE" for cost
5. Verify `## Summary` section has substantive prose in each card
6. Re-run generation — card timestamps update, content reflects latest data
7. Run `bench run --tier quick --model openai/qwen-local` — verify card auto-generated after run
8. Run `pytest` — no regressions from new code

## Docs to Update

- `CLAUDE.md` — add `results/` directory description to Architecture section, add `bench results generate` to CLI Usage
