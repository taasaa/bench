# Clean-Slate Test Suite Audit

**Scope:** `/tmp/bench-clean-slate/tests/` only. 38 test files. 766 tests. **All passing today** — audit looks for tests whose logic is correct *today* but silently depends on LiteLLM proxy state or the live OpenRouter price cache, and will rot when those drift.

**Skipped (already audited/fixed per task scope):**
- `test_pricing.py::TestResolveAliasMapTier` (already uses mocks)
- `test_recorded_model_identity.py` (already rewritten with fixtures)
- `test_inspect_recorded_name.py` (already rewritten)

---

## Summary

| Severity | Count | What breaks |
|----------|------:|-------------|
| **HIGH**   | **6** | Assertion directly pins a live proxy/cache value; will fail on next drift with a noisy but **confusing** error (e.g. `rut -> zai/glm-5.2` becomes `'z-ai/glm-5.2' == 'zai/glm-5.2': False`), or with a class of "value changed but my invariant still holds" false-negatives |
| **MEDIUM** | **11** | Test reads live state to set up its own fixture (real_id, m2.7 reference, log file presence); fails silently when state is missing (cost/time cap never rebuilt, test skipped without notice, etc.) |
| **LOW**    | **2**  | Uses `openai/does-not-exist-xyz789`-style strings; tiny risk that a real proxy alias collides |

**Top 3 files by finding count:**

1. **`tests/test_pricing.py`** — 6 findings (3 HIGH: H1/H2/H3, 3 MEDIUM: M1/M2/M3). The pricing/resolver test module — the place where one would *least* expect silent rotation bugs.
2. **`tests/test_results.py`** — 4 findings (2 HIGH: H4/H5, 2 MEDIUM: M8/M9). `TestContextWindowFix` and `TestFreeModelPricingFix` are pinned to the live cache; `TestMonikerSkip` and `TestDeterministicCardIdentity` have stale assumptions.
3. **`tests/test_run_recorded_name.py`** — 2 findings (1 MEDIUM: M10, 1 LOW: L1). One real live-resolve call, one symlink that just happens to work.

Other affected files (1 finding each, mostly MEDIUM):
`test_scorers.py` (H6 — TestTaskBudgets, 3 drift-pinned values), `test_cli.py` (M4), `test_compare.py` (M5), `test_resolver.py` (M6), `test_results_slug.py` (M7), `test_discriminative_perf.py` (M11), `test_inspect_recorded_name.py` (L2).

The post-audit pattern is **the more invasive the test's interaction with pricing/routing, the more it pins live state** — `test_provider.py` is the gold standard (full synthetic LiteLLM YAML in `tmp_path`); `test_pricing.py` and `test_scorers.py::TestTaskBudgets` violate the rule most often.

---

## HIGH

### H1 · `test_pricing.py:155–161` — pins `rut → z-ai/glm-5.2` to current proxy routing

```python
def test_resolve_openrouter_id_litellm_name_without_prefix(self):
    """Config-calibrated (LiteLLM routing changes over time): 'rut' currently -> glm-5.2."""
    result = resolve_openrouter_id("rut")
    # 'rut' -> 'zai/glm-5.2' per current ~/dev/litellm/config.yaml; cache reverse-lookup
    assert result == "z-ai/glm-5.2"
```

**Why it rots:** This is a live call to `resolve_openrouter_id("rut")` that asserts a specific OpenRouter ID that resolves via the `_build_reverse_lookup()` cache. The comment admits it. Any of these are enough to break it:
- `rut` alias is renamed in `~/dev/litellm/config.yaml`
- The reverse-lookup target `glm-5.2` is rebound to a different upstream model
- The OpenRouter cache drops `z-ai/glm-5.2`

**Rewrite:** Skip this test entirely — the resolver's logic is covered by `TestResolveAliasMapTier` (already mocked). The class header comment for `TestLiteLLMConfig` is misleading; it's not testing resolver logic, it's testing what the live resolver returns for one specific input. Either delete or `@pytest.mark.xfail(reason="config-calibrated, see audit H1")` it with a clear note.

**Finding class:** Hardcoded live proxy/cache entry.

---

### H2 · `test_pricing.py:215–238` — uses live OpenRouter cache as test fixture

```python
def test_save_and_load_override(self, tmp_path, monkeypatch):
    ...
    cache = OpenRouterCache()
    all_prices = cache.get_all_prices()
    real_id = next(iter(all_prices))   # <- live cache
    save_override("openai/test-model", real_id)
    ...
```

**Why it rots:** `OpenRouterCache()` (no path arg) uses the default `cache_path` which points at the live `/tmp/bench-clean-slate/logs/pricing/openrouter-models.json`. Any iteration order or first-entry drift silently breaks the test. Even worse, the test ships `openai/test-model` → `<whichever-model-is-first-today>`, which has zero diagnostic value when it eventually fails.

**Rewrite:** Synthesize a temp cache like the other tests in this module:
```python
cache_path = tmp_path / "cache.json"
cache_path.write_text(json.dumps({"fake/vendor-model": {"input": 0.1, "output": 0.2, "context": 4096}}))
monkeypatch.setattr(OpenRouterCache, "__init__", lambda self, **kw: self.__dict__.update(_cache_path=cache_path, _data=None))
```

**Finding class:** Reads live `OpenRouterCache` as fixture.

---

### H3 · `test_pricing.py:240–258` — same pattern, different name

```python
def test_override_used_when_litellm_slug_not_in_cache(self, tmp_path, monkeypatch):
    ...
    cache = OpenRouterCache()
    all_prices = cache.get_all_prices()
    real_id = next(iter(all_prices))   # <- live cache
    save_override("openai/fake-test-model", real_id)
```

**Same issue, same fix as H2.**

---

### H4 · `test_results.py:TestContextWindowFix` (lines ~528–556) — pins `ctx_window = 1_000_000` to live proxy

The class has an explicit tell:
```python
class TestContextWindowFix:
    """_get_model_metadata should find max_input_tokens from LiteLLM config.

    NOTE: these tests currently depend on specific LiteLLM proxy entries
    (nemotron) and are scheduled for rewrite in the clean-slate review to
    decouple from proxy state. Left as-is here for the scope of the quick
    fixes; full review pass will synthesize a temp config fixture.
    """
```

…and the assertions:
```python
meta = _get_model_metadata("nvidia/nemotron-3-super-120b-a12b:free")
assert meta["ctx_window"] == 1_000_000

meta = _get_model_metadata("openai/nemotron-super-120b-free")
assert meta["ctx_window"] == 1_000_000
```

`ctx_window` is sourced from `bench_cli/results/core.py:_get_model_metadata` which reads `~/dev/litellm/config.yaml` directly (`Path.home() / "dev" / "litellm" / "config.yaml"`). The test breaks the moment someone changes `model_info.max_input_tokens` for any of the nemotron-3-super-120b aliases — which is exactly the kind of drift the rule targets.

**Rewrite:** Monkeypatch `Path.home() / "dev" / "litellm" / "config.yaml"` to a tmp YAML (mirroring `test_provider.py` pattern), or pass `litellm_path` directly into `_get_model_metadata` if you don't want to mutate source. The author's NOTE in the docstring acknowledges this is owed.

**Finding class:** Reads live LiteLLM proxy config as fixture.

---

### H5 · `test_results.py:TestFreeModelPricingFix` (lines ~559–595) — pins specific dollar amounts

```python
def test_free_model_meta_has_paid_prices(self):
    meta = _get_model_metadata("nvidia/nemotron-3-super-120b-a12b:free")
    assert meta["free"] is True
    assert meta["has_price"] is True
    assert meta["input_price"] > 0.0
    assert meta["output_price"] > 0.0

def test_free_model_card_shows_real_price(self, tmp_path, monkeypatch):
    ...
    path = generate_card("nvidia/nemotron-3-super-120b-a12b:free", model_data, tmp_path)
    content = path.read_text()
    overview_section = content.split("## Overview")[1].split("##")[0]
    assert "(currently free)" in overview_section
    assert "$0.0800/M in" in overview_section        # <- hardcoded price
    assert "$0.4500/M out" in overview_section       # <- hardcoded price
```

`$0.08/M` and `$0.45/M` are prices on `nvidia/nemotron-3-super-120b-a12b` (current OR cache today). Any pricing drift on this model breaks the assertion. Two more findings in the same class:
- The first test gates "price > 0" on a live cache containing the model — fails when the OR cache loses the model OR its paid variant.
- The card-generation test's input model `nvidia/nemotron-3-super-120b-a12b:free` triggers a live `_get_model_metadata` call that walks the proxy config to strip `:free` and look up the paid variant. Silent breakage everywhere.

**Rewrite:** Same fixture pattern as the other `TestGenerateCard` tests in this file (it already patches `_RESULTS_DIR` to `tmp_path`); add a `_get_model_metadata` patch returning a synthetic dict with `input_price=0.08, output_price=0.45, free=True` so the assertions check the formatter, not pricing drift.

**Finding class:** Specific historical values; live cache read.

---

### H6 · `test_scorers.py:TestTaskBudgets` (lines ~488–537) — pins reference cost to current m3 baseline

```python
class TestTaskBudgets:
    """Pin the cost reference to the current benchmark (m3 as of 2026-06-18).
    ...
    Tolerance is loose (within 1%) because the source of truth is the live m3
    eval logs; small drift across re-evaluations is OK.
    """
    def test_u17_reference_is_m3_baseline(self):
        b = get_task_budget("u17_dirty_workspace_triage")
        assert b.reference_cost_usd == pytest.approx(0.000737, rel=0.01), (
            f"u17 reference drifted to {b.reference_cost_usd}; "
            "expected m3 baseline (~0.000737), not m2.7 (0.007419)"
        )

    def test_u18_reference_is_m3_baseline(self):
        ...
        assert b.reference_cost_usd == pytest.approx(0.003001, rel=0.01), (
            f"u18 reference drifted to {b.reference_cost_usd}; ..."
        )

    def test_add_tests_reference_is_m3_baseline(self):
        ...
        assert b.reference_cost_usd == pytest.approx(0.000735, rel=0.01), ...
```

This is a regression guard for the m2.7 → m3 re-baseline. The class docstring announces it explicitly: "Pin the cost reference to the current benchmark". Three tests, three pinned values: `0.000737`, `0.003001`, `0.000735`. Every m3 re-eval will eventually drift past the `rel=0.01` tolerance; the assertions will fail with the *exact* value-then-message the author debug-commented for ("drifted to ..."), which is convenient for the author and a hazard for the next maintainer.

**Rewrite:** Add a `task_budgets` regression test that does NOT pin specific numbers — instead assert that `get_task_budget(X)` returns the same value across two calls (deterministic), that the reference is sourced from a named reference model (`_REFERENCE_FILE` via `monkeypatch`), and that the ratio-recompute path uses it. Keep the rejection-toward-m2.7 behavior as a separate test that asserts the *direction* without pinning the magnitude.

**Finding class:** Specific historical entries (rule #4).

---

## MEDIUM

### M1 · `test_pricing.py:73–93` — TestModelAliases::test_catch_all_fires... uses live cache for real_id

```python
def test_catch_all_fires_when_live_proxy_returns_none(self, tmp_path, monkeypatch):
    from bench_cli.pricing.price_cache import OpenRouterCache
    all_prices = OpenRouterCache().get_all_prices()
    real_id = next(iter(all_prices))
    ...
```

The test mocks `_resolve_from_litellm`, but the `real_id` target comes from the live cache. If the cache is empty (fresh checkout after `bench prices refresh` hasn't run), the test fails on `next(iter(...))` raising `StopIteration`. Silent breakage when a new contributor forgets to refresh, which is the most common path to running the suite.

**Rewrite:** Same `tmp_path` cache fixture as H2.

---

### M2 · `test_pricing.py:188–201` — TestModelOverrides::test_save_override_rejects_unknown_id

```python
def test_save_override_rejects_unknown_id(self, tmp_path, monkeypatch):
    ...
    with pytest.raises(ValueError, match="not found in OpenRouter cache"):
        save_override("openai/test-model", "provider/does-not-exist")
```

`save_override` opens `OpenRouterCache()` (live cache) to validate. Test passes today because `provider/does-not-exist` is not in the cache. If anyone ever adds `provider/does-not-exist` as an OpenRouter ID the test fails. The "fake" string is too short to be reliably fake; pick something containinizing-friendly like `nonexistent-aaaaaaaaaaaaaa/no-such-model`.

**Rewrite:** Patch `OpenRouterCache.__init__` to point at `tmp_path/cache.json` containing only known models; synthesize `provider/does-not-exist` not in the synthesized cache. Same shape as M1.

---

### M3 · `test_pricing.py:118–130` — TestLiteLLMConfig name-collapse tests

```python
def test_resolve_openrouter_id_from_litellm_config_only(self):
    """Alias not in LiteLLM config returns None — no MODEL_ALIAS_MAP fallback."""
    result = resolve_openrouter_id("openai/does-not-exist-xyz789")
    assert result is None

def test_resolve_openrouter_id_unknown_alias(self):
    result = resolve_openrouter_id("openai/this-does-not-exist-xyz789")
    assert result is None
```

Tiny but real collision risk: someone adds `does-not-exist-xyz789` to the proxy as a model_name. Vanishingly unlikely but the test has zero diagnostic value as written — it doesn't test "lookup miss path" (which is already covered by `TestResolveAliasMapTier::test_alias_not_in_proxy_no_map_falls_through`), it tests "this specific string isn't a proxy model_name". These can be deleted with no coverage loss.

**Rewrite:** Delete or fold the assertion into `TestResolveAliasMapTier`.

---

### M4 · `test_cli.py:409–429` — TestPricesAdd::test_prices_add_success pins openai/nvidia-mistral-small4

```python
def test_prices_add_success(self, tmp_path):
    ...
    ["prices", "add", "openai/nvidia-mistral-small4", "0.15", "0.60"],
    obj={"cache": isolated_cache},
    ...
    resolved_id = resolve_openrouter_id("openai/nvidia-mistral-small4")   # <- live proxy
    info = isolated_cache.get_price(resolved_id)
    assert info.input_price == 0.15
```

The verification step calls `resolve_openrouter_id("openai/nvidia-mistral-small4")` which goes to the live proxy. If the alias is removed, `resolved_id` is None and `get_price(None)` raises `CacheMiss`. The actual `prices add` step uses the isolated cache and would pass — but the post-assertion breaks.

**Rewrite:** Synthesize the resolution like the gate test in the same file (`mock litellm_config._resolve_from_litellm`); keep the rest.

---

### M5 · `test_compare.py:240–253` — TestRatioReferenceLabelsDefaultAndRegistered pins qwen-local and minimax-m2.7

```python
def test_ratio_reference_labels_default_and_registered(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")
    labels = _ratio_reference_labels()
    assert "qwen-local" in labels["efficiency_latency"]    # SYSTEM_DEFAULT
    assert "minimax-m2.7" in labels["cost"]                # task_budgets reference
```

When `task_budgets` re-baselines from m2.7 → (next model) and `reference_model`'s `SYSTEM_DEFAULT` shifts, both embedded strings break. The test is checking "default label is set" — fine — but the strings are tight to module constants, not the test premise.

**Rewrite:** Assert the *shape* of the labels (keys present, values non-empty), not the exact strings. Or pin against a sentinel model the test registers itself.

---

### M6 · `test_resolver.py` — TestResolveModel depends on live proxy aliases

Four tests use live `_SUFFIX_MAP` from the proxy:

```python
def test_exact_suffix_match(self):                      # qwen-local
    assert resolve_model("qwen-local") == "openai/qwen-local"

def test_exact_suffix_match_opus(self):                 # opus
    assert resolve_model("opus") == "openai/opus"

def test_unique_prefix_match(self):                     # minimax (unique prefix)
    result = resolve_model("minimax")
    assert result == "openai/minimax"

def test_default_alias(self):                           # default
    assert resolve_model("default") == "openai/default"
```

Each one passes today. The moment `qwen-local`, `opus`, `minimax`, or `default` is renamed in the proxy or dropped from `_load_litellm_alias_map()`, that test goes red. None of these tests cover new resolver logic — they cover "the proxy has these aliases", which is the proxy's job to test, not the resolver's.

**Rewrite:** Patch `_load_litellm_alias_map` to return a dict with `{"qwen-local", "opus", "minimax", "default"}-like` keys to test resolver logic, then add one parameterised test that asserts the suite derives the suffix map from whatever `_load_litellm_alias_map` returns (already covered indirectly). Most of these tests can be deleted or replaced with a single fixture-driven one.

---

### M7 · `test_results_slug.py:37–55` — TestGetModelMetadata reads live cache

```python
def test_get_model_metadata_provider_for_nvidia_or_id(self):
    meta = _get_model_metadata("nvidia/nemotron-3-ultra-550b-a55b")
    assert meta["provider"] == "NVIDIA NIM"
    assert meta["free"] is False

def test_get_model_metadata_pricing_for_direct_or_id(self):
    meta = _get_model_metadata("nvidia/nemotron-3-ultra-550b-a55b")
    assert meta["has_price"] is True
    assert meta["input_price"] > 0
    assert meta["output_price"] > 0
```

Both call `_get_model_metadata("nvidia/nemotron-3-ultra-550b-a55b")` which reads the LiteLLM config (for `ctx_window`, `litellm_path`) and the cache (for `has_price`, prices). Double dependency: rename in proxy → fail; delisted from OR cache → fail `has_price=True`. The third test in this file (`test_get_model_metadata_pricing_for_bench_alias_still_works`) already does the right thing (mocks resolution + cache). Apply the same pattern here.

**Rewrite:** Same patch pattern as `test_get_model_metadata_pricing_for_bench_alias_still_works` (lines 56–80 of same file).

---

### M8 · `test_results.py::TestMonikerSkip` (lines ~628–639) — pins router moniker names

```python
@pytest.mark.parametrize("moniker", ["default", "thinking", "heavy", "background", "smart-router"])
def test_is_moniker_alias(self, moniker):
    from bench_cli.results.core import is_moniker_alias
    assert is_moniker_alias(f"openai/{moniker}") is True
```

`is_moniker_alias` looks up `bench_cli/results/core.py:_ROUTER_MONIKERS` (a hardcoded `{"default", "thinking", "heavy", "background", "smart-router"}` — constant, not proxy-derived). Today this test is fine because the constant is the same. If the router tier list adds a new moniker (`"deep"` etc.) this test still passes (it doesn't assert exclusivity). It's MEDIUM-low risk: rots if someone deletes one of these from the constant. Worth a guard rail but not urgent.

**Rewrite:** Keep, but add a `test_no_extra_unknown_monikers_registered` that reads `_ROUTER_MONIKERS` directly (the source constant) and asserts the parametrize list matches it — that way both directions are covered.

---

### M9 · `test_results.py:111–134` — TestDeterministicCardIdentity depends on live proxy remap

```python
def test_two_distinct_models_never_collide(self, tmp_path, monkeypatch):
    monkeypatch.setattr("bench_cli.results.core._RESULTS_DIR", tmp_path)
    a = "openai/nvidia-nemotron-30b"        # -> nvidia/nemotron-3-nano-30b-a3b
    b = "openai/fabric"                      # -> nvidia/nemotron-3-super-120b-a12b
    # 1. derivation-level distinctness
    assert _slug_from_alias(a) != _slug_from_alias(b)
    assert _real_model_name(a) != _real_model_name(b)
```

The comments reveal the live proxy bindings (`fabric → nemotron-super-120b`). If either alias is rebroken the test silently reassigns to the same target and the "never collide" assertion fails for the wrong reason. The intent is "two distinct `openai/X` aliases always get distinct slugs" — that can be tested with synthetic OR IDs and a mocked resolver.

**Rewrite:** Use `openai/test-a` → `fake/a-v1` and `openai/test-b` → `fake/b-v1` patterns; mock `resolve_openrouter_id` to map each test alias to a distinct OR id.

---

### M10 · `test_run_recorded_name.py:65–88` — TestNoAsFlagRecordsOpenrouterId

```python
def test_no_as_flag_records_openrouter_id(monkeypatch, tmp_path):
    expected_recorded = resolve_recorded_name("openai/thinking", None)
    assert expected_recorded != "openai/thinking", (
        "test premise broken: openai/thinking must resolve to a backing model "
        "(not the routing alias itself) for the round-trip to be meaningful"
    )
    ...
```

Live `resolve_recorded_name("openai/thinking", None)` is asserted to be `!= "openai/thinking"` and stored as the expected recorded name. The docstring on the test openly says "the test follows the proxy by design". When the proxy rebinds `thinking` to a different backing model, the recorded name changes — and the test silently asserts whatever new value. It passes today but propagates any drift to the comparison below.

**Rewrite:** Same pattern as `test_recorded_model_identity.py::test_recognizable_alias_resolves_to_openrouter_id` (the scope-skipped file): mock `resolve_backing_model_id` to return a known OR id, assert equality.

---

### M11 · `test_discriminative_perf.py` — `test_get_all_log_paths_per_subject_filter_stable` + `test_bench_compare_matrix_4_subjects_under_60s`

```python
# 4 known subjects
targets = {"xiaomi/mimo-v2.5-pro", "minimax/minimax-m3",
           "z-ai/glm-5.2", "deepseek-ai/deepseek-v4-pro"}
```

Both tests gate on presence of eval logs for these 4 specific models (via `pytest.skip` if none found). The skip is graceful BUT it means the perf regression guard vanishes the moment any of these models' logs are pruned or rotated out. The test then silently skips instead of catching perf regressions.

**Rewrite:** Find any 4 eval logs in `logs/` (any model) and assert scan time over those. Perf regression is independent of which specific models exist.

---

## LOW

### L1 · `test_run_recorded_name.py:34–63` — TestAsFlagRecordsCustomNameAndRoutesThroughModel

```python
result = runner.invoke(
    run_cmd,
    [
        "--model", "openai/thinking",
        ...
    ],
)
```

Passes `--model openai/thinking`, but `run()` paths that depend on proxy resolution (`_check_price_gate`, `resolve_provider`) are all mocked. The only live dependency is the run loop discovering tasks for tier=quick, task=smoke — that doesn't touch the proxy. Classed LOW because the test will keep working even if `thinking` is removed from the proxy, since `inspect_ai.eval` is mocked and never resolves anything.

**Recommendation:** No change required; flag in case of confusion in the future.

---

### L2 · `test_inspect_recorded_name.py::test_resolve_query_name_passes_recorded_through` (line ~62)

```python
alias = "openai/thinking"
assert _resolve_query_name(alias) == resolve_recorded_name(alias, None)
```

Already noted by the author — the test is technically in the "already rewritten" scope, but this one assertion still calls `resolve_recorded_name("openai/thinking", None)` live. It's an invariant check (both functions return the same thing), so when the proxy rebinds `thinking`, both sides move together and the test still passes. Genuinely LOW because the assertion is symmetric.

**Recommendation:** Mock `resolve_recorded_name` and `_resolve_query_name` to both return `"fake/test-or-id"` to make the invariant explicit.

---

## Notes on the skip-list

The task scope asked me to skip three tests:
- `test_pricing.py::TestResolveAliasMapTier` — confirmed fully mocked ✓
- `test_recorded_model_identity.py` — confirmed fixture-synth ✓
- `test_inspect_recorded_name.py` — confirmed `test_resolve_query_name_passes_recorded_through` (L2) still has residual live-call; consider it as a residual note rather than a finding.
