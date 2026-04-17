# PRD: OpenRouter Direct Pricing + Pre-flight Price Gate

**Scope:** feature
**Date:** 2026-04-17
**Tier:** standard

## Problem Statement

Bench's pricing infrastructure has two redundant layers: `KiloCode API → JSON cache → bench`. KiloCode is a thin markup wrapper around OpenRouter's `/v1/models` endpoint, which is publicly readable. Meanwhile, the LiteLLM config at `~/dev/litellm/config.yaml` already maps every `bench` model alias (e.g. `nvidia-mistral-small4`) to the real OpenRouter model ID — but the pricing code ignores this and relies on a hand-maintained `MODEL_ALIAS_MAP` that goes stale. When a model has no price, the scorer silently records `NaN` and cost scores are blank only after the run finishes, wasting time and money.

## Success Criteria

1. `bench run --model openai/nvidia-mistral-small4` fails before any model API calls if no price is known after cache refresh — verify by: run with no price in cache; expect exit code 1, stderr containing resolved OpenRouter ID and `bench prices add` command
2. `bench prices refresh` fetches from `GET https://openrouter.ai/api/v1/models` — verify by: `curl` the endpoint directly, compare cache before/after
3. New models added to LiteLLM config are automatically price-discoverable — verify by: add a new alias to `~/dev/litellm/config.yaml`, run `bench run`, observe correct real OpenRouter ID resolved from config
4. `COST_RATIO` and `AVG COST` columns populate for any model whose OpenRouter ID is in the cache — verify by: `bench compare` shows no `--` in cost columns for `nvidia-mistral-small4`
5. `_MANUAL_PRICES` fallback in `compare.py` still works — verify by: `bench compare` on `nvidia-mistral-small4` shows same values as before this change

## Implementation Approach

### Phase 1: Replace KiloCode with OpenRouter
- Change `price_cache.py` `_KILOCODE_API_URL` to `https://openrouter.ai/api/v1/models`
- Auth header: `Authorization: Bearer {OPENROUTER_API_KEY}` — authenticated requests get higher rate limits
- Response shape is `{data: [{id, pricing: {prompt, completion}, context_length}]}` — same structure as KiloCode, minimal parsing changes
- Rename `KiloCodeCache` → `OpenRouterCache`, `kilocode-models.json` → `openrouter-models.json`
- Add `OPENROUTER_API_KEY` to `.env` template; keep `KILOCODE_API_KEY` for backward compat until migration complete
- On first run: if `kilocode-models.json` exists but `openrouter-models.json` does not, copy it over with a migration notice

### Phase 2: LiteLLM Config as Source of Truth for Model IDs
- Add `LiteLLMConfig` class in `pricing/` that reads `~/dev/litellm/config.yaml` via `yaml.safe_load`
- Build a dict `{model_alias: real_openrouter_id}` from all `model_name:` + `litellm_params.model:` entries in the config
- Merge with `MODEL_ALIAS_MAP`: LiteLLM config takes priority, `MODEL_ALIAS_MAP` is fallback for models not in config
- The real OpenRouter ID is the `model:` value under `litellm_params:` (e.g. `openai/mistralai/mistral-small-4-119b-2603`)

### Phase 3: Pre-flight Price Gate

**Gating flow:**
1. Resolve model alias → real OpenRouter ID from LiteLLM config
2. Check OpenRouter cache — price found? proceed, no gate
3. Price not found? Refresh cache (one HTTP call to OpenRouter `/v1/models`)
4. Still not found? **Then** block — user must provide price via `bench prices add`

**Pre-flight block:**
- In `bench_cli/run.py`, after resolving alias and confirming it's not a local/proxy model
- Print to stderr:
  ```
  ERROR: No price found for openai/nvidia-mistral-small4
    Resolved OpenRouter ID: mistralai/mistral-small-4-119b-2603
    Add price with: bench prices add openai/nvidia-mistral-small4 0.15 0.60
  ```
- Exit code 1, zero tasks launched, zero API calls to the model
- **No interactive prompt** — user runs `bench prices add` in their own terminal, then re-runs `bench run`

**Local/proxy models exempt:** If alias is in `MODEL_ALIAS_MAP` but not in LiteLLM config and not in OpenRouter catalog (qwen-local, gemma-*-local), skip the price gate entirely — these are "managed models" with no public pricing.

### Phase 4: `bench prices add` CLI command
- `bench prices add openai/nvidia-mistral-small4 0.15 0.60`
- Parses args: `<alias>` (the LiteLLM alias), `<input_price>` ($/M tokens), `<output_price>` ($/M tokens)
- Uses LiteLLM config to resolve alias → real OpenRouter ID
- Writes entry to `logs/pricing/openrouter-models.json`
- Prints confirmation: `"Added: openai/nvidia-mistral-small4 ($0.15/M in, $0.60/M out) → mistralai/mistral-small-4-119b-2603"`

## Test Plan

- [ ] Unit test: `LiteLLMConfig` correctly parses `~/dev/litellm/config.yaml` and returns the expected alias→ID map
- [ ] Unit test: `OpenRouterCache.fetch_and_cache_prices()` makes the correct HTTP request and parses the response
- [ ] Integration test: `bench run` with no price → exit 1 + error message contains `bench prices add` command
- [ ] Integration test: `bench prices add openai/nvidia-mistral-small4 0.15 0.60` → cache updated
- [ ] Integration test: `bench run` after `bench prices add` → run succeeds, cost columns populated
- [ ] Regression test: `bench compare` output unchanged for models with existing prices
- [ ] Manual: `pytest`

## Docs to Update

- [ ] `CLAUDE.md` — update price source from KiloCode to OpenRouter; update `.env` template
- [ ] `bench_cli/pricing/price_cache.py` docstring — rename KiloCode to OpenRouter
- [ ] `docs/EVAL-GUIDE.md` — update pricing section with pre-flight gate and `bench prices add` usage

## Edge Cases & Gotchas

- **Local/proxy models (qwen-local, gemma-*-local)**: Not in OpenRouter's catalog. `MODEL_ALIAS_MAP` handles these as "managed models" — exempt from pre-flight gate.
- **LiteLLM config path**: Hardcoded to `~/dev/litellm/config.yaml`. Validate path exists; warn but don't block if missing (fall back to `MODEL_ALIAS_MAP` only).
- **Cache migration**: Copy old `kilocode-models.json` to `openrouter-models.json` on first run if new file absent — preserves manual price injections.
- **Platform fee**: OpenRouter charges ~5.5% on credit card purchases. Bench's cost scoring uses model provider prices (pre-fee) as a best-effort estimate. Flag this in the docs.

## Anti-Patterns to Avoid

- Don't remove `MODEL_ALIAS_MAP` — it's the only path for local/proxy models
- Don't block runs for local/proxy models just because they're absent from OpenRouter — use `MODEL_ALIAS_MAP` presence as the exemption signal
- Don't skip the cache refresh step before blocking — the gate only fires after a fresh cache lookup fails
- Don't reduce the cache TTL from 3 days

## Acceptance Checklist

- [ ] `bench run` blocks with exit 1 when price unknown after refresh — verify by: cache deliberately emptied, run attempted, no model API calls made
- [ ] Error message includes resolved OpenRouter ID and `bench prices add` command — verify by: stderr output
- [ ] `bench prices add` writes to cache and confirms — verify by: cache file updated, print confirmation
- [ ] `bench run` succeeds after `bench prices add` — verify by: eval starts and completes
- [ ] `bench compare` shows populated cost columns for `nvidia-mistral-small4` — verify by: `COST_RATIO` and `AVG COST` not `--`
- [ ] All 32 tasks still pass — verify by: `pytest`

## Open Questions

- Should `bench prices add` accept the OpenRouter ID directly, or always the alias? → Always the alias — resolves to OpenRouter ID internally. Less surface area for user error.
- Should we warn when `bench prices add` price differs significantly from OpenRouter's listed price? → No, not in v1.
- `OPENROUTER_API_KEY` vs `OR_API_KEY` naming? → Accept both; `OPENROUTER_API_KEY` canonical.

## Skill Integrations

- **Research**: OpenRouter `/v1/models` publicly readable; authenticated requests get higher rate limits. Response shape matches KiloCode — minimal parsing changes needed. LiteLLM config stores real model ID in `litellm_params.model` field.
- **Thinking/FirstPrinciples**: Hard constraint: eval runs cost real money — user must know before they run. Soft constraint: KiloCode as pricing source (replaced by OpenRouter directly). Soft constraint: `MODEL_ALIAS_MAP` for ID resolution (LiteLLM config is better source of truth). Assumption challenged: "KiloCode is necessary" — OpenRouter is the source; KiloCode adds no value here.
