# PRD: Cost-Aware Bench Scoring

**Scope:** feature
**Date:** 2026-04-16

## Problem Statement

Token count and cost are decoupled. A model that uses 10× fewer tokens at 10× the price per token scores the same as one that's genuinely cheap. Bench has correctness, token efficiency, and latency scoring — but no cost scoring. This is the gap.

## Success Criteria

1. `bench compare` shows a COST column alongside CORRECT/TOK_RATIO/TIME_RATIO for all scored models
2. Prices fetched from `https://api.kilo.ai/api/openrouter/models`, cached locally, refreshed on 3-day TTL
3. Per-sample cost = `(input_tokens × input_price) + (output_tokens × output_price)` in USD
4. COST_RATIO = `reference_cost / actual_cost` (higher = cheaper; same ratio semantics as TOK_RATIO)
5. Geometric mean of COST_RATIO across tasks in summary row
6. Cache miss → soft stop: anomaly flag in output, compare table continues, COST column shows `N/A` for affected model
7. Cache freshness visible in compare output header
8. Free models show `$0.00 (FREE)` in COST column

## Implementation Approach

### Price cache + alias map
- `logs/pricing/` directory for cached price JSON (bench/bench is a CLI script file, not a directory, so cache uses logs/pricing/ instead)
- `bench_cli/model_aliases.py` — static alias map: bench Litellm alias → KiloCode model ID
  - Covers the models bench actually uses (audit Litellm model list against KiloCode catalog)
  - Examples: `openai/qwen-local` → `qwen/qwen-local`, `openai/gemma-4-e2-local` → `google/gemma-4-26b-a4b-it`
  - Free model detection: any model with `$0` input and output price → flag as `FREE`
- `scorers/price_cache.py`:
  - `fetch_and_cache_prices()` — hits kilo API, writes `bench/pricing/kilocode-models.json`
  - `get_price(kilo_model_id)` — reads cache, returns `{"input": float, "output": float}` or raises `CacheMiss`
  - `CacheMiss` exception → caught by scorer, emits anomaly flag, returns `None`
- Cache format: `{ model_id: { "input": float, "output": float, "context": int|null }, fetched_at: ISO string }`
- TTL: 3 days, silent refresh if expired
- API key: reads from `.env` `KILOCODE_API_KEY` (already loaded by `bench_cli/main.py`)
- Cache freshness: `fetched_at` timestamp written to cache; compare output header shows `COST: cached YYYY-MM-DD (Nd ago)`
- Unknown aliases → `CacheMiss` → soft stop (not hard stop)

### price_ratio_scorer
- `scorers/price_ratio.py`: `price_ratio_scorer(state)`
- Reads token counts: `input_tokens = state.output.usage["prompt_tokens"]`, `output_tokens = state.output.usage["completion_tokens"]`
- Resolves model from `state.metadata.get("model")` → alias map → KiloCode ID → cache lookup
- Input/output priced separately per model
- Reference cost from `task_budgets.py` (add `reference_cost_usd` column per task)
- Returns `Score(value=cost_ratio, explanation=f"${actual:.6f} vs ref ${ref:.6f}")` if price available
- Returns `Score(value=NaN, explanation="price unavailable")` on `CacheMiss` — anomaly emitted
- Correctness gate: cost score only recorded for tasks where correctness scorer passed

### compare.py integration
- `PillarScores` gets `price_ratio: float` and `avg_cost_usd: float`
- `load_compare_data()` extracts `price_ratio_scorer` value from sample scores
- Table renders COST column after TIME column:
  - `COST_RATIO` shows `1.2×` (1.2× cheaper than reference)
  - `AVG COST` shows `$0.0042` per sample
  - `N/A` for models with no price data
- Geometric mean for COST_RATIO in summary row
- Cache freshness timestamp in output header
- Free models: `0.00 (FREE)` in COST column

### CLI + cache management
- `bench prices refresh` — force-refresh cache regardless of TTL
- `bench prices list` — show cached prices for known models

## Edge Cases & Gotchas

- **Free models** (price = 0): show `$0.00 (FREE)`; COST_RATIO = ∞ handled as special display
- **Kilo API key missing**: fail with message pointing to `.env` setup
- **Network failure on cache miss**: soft stop — anomaly flag, `N/A` in COST column, run continues
- **Token count unavailable**: skip price scoring for that sample, score not recorded
- **Alias not in map**: `CacheMiss` → soft stop → anomaly flag → `N/A`
- **Reference model not in cache**: skip with warning; don't interpolate
- **KiloCode model not in cache**: soft stop → `N/A`, run continues
- **Both model eval AND agent eval**: scorer reads `state.metadata["model"]` — works for both modes

## Anti-Patterns to Avoid

- Don't compute price post-hoc in `compare.py` from stored token counts — compute during scoring
- Don't hard-stop on cache miss — soft stop with anomaly flag
- Don't use KiloCode markdown output — fetch raw JSON API directly
- Don't skip input/output token split — they have different per-token prices
- Don't use a single flat token count for cost calculation

## Architecture Decisions (council-verified)

| Decision | Rationale |
|---|---|
| Correctness gates cost scoring | Prevents rewarding cheap-but-wrong solutions |
| Raw cost stored, ratio as display-time view | Eliminates denominator-dependency problem |
| HMAC-signed cache entries | Prevents local cache poisoning |
| SQLite warm-path over KiloCode | Eliminates KiloCode as runtime dependency |
| Geometric mean for task-conditional aggregation | Penalizes cross-task variance symmetrically; configurable to arithmetic mean |
| 3-day TTL accepted | General assessment tooling, not precision scalpel |
| Soft stop on cache miss | Preserves eval run integrity; anomaly flag surfaces the gap |

## Acceptance Checklist

- [x] `bench prices refresh` fetches fresh prices, writes `bench/pricing/kilocode-models.json`
- [x] 3-day TTL respected — no re-fetch within window
- [x] `bench prices list` shows cached model prices
- [x] `bench compare` shows COST column with COST_RATIO + AVG COST per model
- [x] `N/A` shown for models with no price data (soft stop, not crash)
- [x] Anomaly flag emitted when price unavailable
- [x] Free models show `$0.00 (FREE)`
- [x] Cache freshness timestamp in compare output header
- [x] 269 existing tests still pass
- [x] Geometric mean matches TOK_RATIO/TIME_RATIO format in summary row

## Out of Scope

- Cross-tokenizer cost normalization (benchmark typically compares models through the same proxy)
- Dynamic alias resolution (solve when alias map gaps surface)
- OpenRouter or other provider fallback
