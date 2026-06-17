# Recorded Model Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Load subagent-driven-development/SKILL.md (recommended) or executing-plans/SKILL.md to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `bench run` route a model through one LiteLLM alias (e.g. `openai/thinking`) while recording a recognizable identity (the OpenRouter id `minimaxai/minimax-m3`, or a custom `--as` label) in eval logs, so resume/compare/cards/pricing/discriminative all key off the recognizable name instead of a time-varying moniker.

**Architecture:** Add a `--as` flag to `bench run`. Compute a `recorded_name` from `--model` (routed) using `resolve_openrouter_id` (reused from pricing) with a managed-model short-circuit and an `--as` override. Pass the routed name to `inspect_eval`; after each log writes, rewrite `el.eval.model` to the recorded name (read→mutate→write, non-fatal). Rework the ~6 `openai/`-prefix assumptions behind one `bare_model_name()` helper; fix `bench_cli/inspect` exact-match filters and the discriminative subject source field.

**Tech Stack:** Python 3.10+ (running on 3.14 in the project `.venv`), Inspect AI 0.3.210, Click 8, pytest.

**Spec:** `docs/superpowers/specs/2026-06-17-recorded-model-identity-design.md`

## Global Constraints

- Use the project `.venv`: `.venv/bin/python` and `.venv/bin/pytest`. No system python. (AGENTS.md)
- Scorers live in `scorers/` at repo root, imported as `from scorers import ...`. `bench_cli/scorers/` does NOT exist. (AGENTS.md)
- Models route through a LiteLLM proxy as `openai/<alias>`; `.env` holds credentials. (SB Operating Rules)
- Router monikers (`default`/`thinking`/`heavy`/`background`/`smart-router`) are NOT fixed models and must not be treated as subjects. (SB Operating Rules)
- Recorded name = raw OR id (e.g. `minimaxai/minimax-m3`), carries creating entity. `--as` values stored literally, no prefix.
- Log rewrite is **non-fatal**: on any exception, warn and leave the routed name; never lose a long run.
- Reuse `resolve_openrouter_id` (in `bench_cli/pricing/litellm_config.py`) as the single recognizable-name resolver. No parallel system. The `[bracket]` pricing override stays separate.
- Pricing scorer is **untouched** — it runs during eval against the routed name and stores name-independent USD cost.

---

## File Structure

| File | Responsibility | Status |
|---|---|---|
| `bench_cli/run/core.py` | Add pure helpers `resolve_recorded_name()` and `rewrite_log_model_name()`. The `inspect_eval` call is NOT here. | Modify |
| `bench_cli/run/cli.py` | Add `--as` option; compute `recorded_name`; thread it through eval + resume + price-gate + status + summary + card-gen. | Modify |
| `bench_cli/resolver.py` | Add `bare_model_name()`; delegate `bare_name()` to it. | Modify |
| `bench_cli/compare/core.py` | `_short_model()` → `bare_model_name`. | Modify |
| `bench_cli/show.py`, `bench_cli/dashboard.py`, `bench_cli/score.py` | No code change; display updates via delegated `bare_name`. (In scope/known.) | No change |
| `bench_cli/inspect/core.py` | Resolve user `--model` to recorded name before the 3 `el.eval.model != model_alias` filters. | Modify |
| `bench_cli/discriminative/subject.py` | `resolve_subject_from_log()` reads `el.eval.model` (recorded) as primary, `model_usage` key as fallback; `_normalize_model()` → `bare_model_name`. | Modify |
| `bench_cli/results/core.py` | `_slug_from_alias`/`_real_model_name`: slug=full `/`→`-`, display=`bare_model_name`; remove redundant static `MODEL_ALIAS_MAP` lookup; `is_moniker_alias` checks bare name; verify `_get_model_metadata` provider/free detection works on OR ids. | Modify |
| `tests/test_recorded_model_identity.py` | New test module for `resolve_recorded_name`, `bare_model_name`, `rewrite_log_model_name`. | Create |
| `tests/test_*.py` (existing) | Extend for discriminative, results slug, inspect resolution. | Modify |

Helpers live in `bench_cli/run/core.py` (pure, testable) and are imported into `run/cli.py`. `resolve_recorded_name` does NOT depend on Inspect; `rewrite_log_model_name` does.

---

## Task 1: `bare_model_name()` helper + delegate `bare_name`

**Files:**
- Modify: `bench_cli/resolver.py` (add `bare_model_name` at ~line 12, after imports; rewrite `bare_name` body at line ~60)
- Test: `tests/test_bare_model_name.py` (create)

**Interfaces:**
- Produces: `bare_model_name(model: str) -> str` — "everything after the first `/`, else the whole string". Consumed by Tasks 4, 6, 7.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bare_model_name.py`:

```python
from bench_cli.resolver import bare_model_name, bare_name


def test_bare_model_name_strips_first_segment():
    assert bare_model_name("openai/thinking") == "thinking"
    assert bare_model_name("minimaxai/minimax-m3") == "minimax-m3"
    assert bare_model_name("nvidia/nemotron-3-ultra-550b-a55b") == "nemotron-3-ultra-550b-a55b"


def test_bare_model_name_no_slash_returns_whole():
    assert bare_model_name("nemotron-ultra-550b") == "nemotron-ultra-550b"


def test_bare_name_delegates_to_bare_model_name():
    # bare_name should now strip the first segment, not just the openai/ prefix
    assert bare_name("openai/thinking") == "thinking"
    assert bare_name("minimaxai/minimax-m3") == "minimax-m3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_bare_model_name.py -v`
Expected: FAIL — `ImportError: cannot import name 'bare_model_name'`.

- [ ] **Step 3: Write minimal implementation**

In `bench_cli/resolver.py`, add after the imports (top of file, before `def _build_suffix_map`):

```python
def bare_model_name(model: str) -> str:
    """Everything after the first '/' segment, or the whole string if no '/'.

    Handles both proxy-alias form ('openai/thinking' -> 'thinking') and raw
    OpenRouter ids ('minimaxai/minimax-m3' -> 'minimax-m3'). This is the single
    source of truth for display/moniker-check/slug derivation.
    """
    return model.split("/", 1)[1] if "/" in model else model
```

Replace the existing `bare_name` function body (currently `return canonical.removeprefix("openai/")`) with:

```python
def bare_name(canonical: str) -> str:
    """Return display name: openai/qwen-local -> qwen-local, minimaxai/minimax-m3 -> minimax-m3."""
    return bare_model_name(canonical)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_bare_model_name.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Verify no regressions in bare_name consumers**

Run: `.venv/bin/pytest tests/ -k "bare or short_model or resolver" -v 2>&1 | tail -20`
Expected: PASS — any existing tests that exercise `bare_name`/`_short_model` still pass (they stripped `openai/` before; now they strip the first segment, identical for `openai/`-prefixed inputs).

- [ ] **Step 6: Commit**

```bash
git add bench_cli/resolver.py tests/test_bare_model_name.py
git commit -m "feat(resolver): add bare_model_name helper, delegate bare_name to it"
```

---

## Task 2: `resolve_recorded_name()` (with managed-model short-circuit)

**Files:**
- Modify: `bench_cli/run/core.py` (add `resolve_recorded_name` after `parse_model_arg`, ~line 175)
- Test: `tests/test_recorded_model_identity.py` (create)

**Interfaces:**
- Consumes: `bench_cli.pricing.litellm_config.is_managed_model`, plus a NEW override-excluding resolver path (see B4 fix below).
- Produces: `resolve_recorded_name(routed_name: str, as_name: str | None) -> str` — the identity to write into logs. Consumed by Task 5 (run/cli.py) and Task 7 (inspect, via re-resolution).

**B4 fix — the pricing `[bracket]` override must NOT leak into the recorded name.** `resolve_openrouter_id` reads the persistent override map (`logs/pricing/model_overrides.json`, e.g. `openai/minimax-m3 → minimax/minimax-m3`) as its FIRST step. If `resolve_recorded_name` reused it directly, `--model openai/minimax-m3` would record `minimax/minimax-m3` (the OpenRouter-API provider id from the override file) instead of the actual NIM backing model — non-deterministic across runs and contradicting the spec Non-Goal (bracket is pricing-only, orthogonal to recorded identity). So we add a sibling resolver that skips step 1.

- [ ] **Step 1: Write the failing test**

Create `tests/test_recorded_model_identity.py`:

```python
"""Tests for resolve_recorded_name and rewrite_log_model_name."""
from bench_cli.run.core import resolve_recorded_name


def test_as_override_used_literal():
    assert resolve_recorded_name("openai/thinking", "nemotron-ultra-550b") == "nemotron-ultra-550b"


def test_as_override_literal_full_name():
    assert resolve_recorded_name("openai/thinking", "nvidia/nemotron-3-ultra-550b-a55b") == \
        "nvidia/nemotron-3-ultra-550b-a55b"


def test_moniker_resolves_to_openrouter_id():
    # thinking currently backs minimax-m3 on the NIM endpoint
    assert resolve_recorded_name("openai/thinking", None) == "minimaxai/minimax-m3"


def test_recognizable_alias_resolves_to_openrouter_id():
    assert resolve_recorded_name("openai/nemotron-ultra-550b", None) == \
        "nvidia/nemotron-3-ultra-550b-a55b"


def test_managed_model_short_circuits_not_resolved():
    # CRITICAL: resolve_openrouter_id returns a non-None LiteLLM id for qwen-local;
    # managed models must record their alias unchanged.
    assert resolve_recorded_name("openai/qwen-local", None) == "openai/qwen-local"
    assert resolve_recorded_name("openai/gemma-4-26-local", None) == "openai/gemma-4-26-local"


def test_unknown_alias_falls_back_to_model():
    # An alias not in LiteLLM config and not managed -> unchanged
    assert resolve_recorded_name("openai/totally-unknown-xyz", None) == "openai/totally-unknown-xyz"


def test_as_overrides_managed_short_circuit():
    # --as wins even for managed models (user's explicit choice)
    assert resolve_recorded_name("openai/qwen-local", "my-local") == "my-local"


def test_bracket_pricing_override_does_not_leak_into_recorded_name():
    # B4: logs/pricing/model_overrides.json has openai/minimax-m3 -> minimax/minimax-m3
    # (a pricing-only correction for the OpenRouter-API provider). The recorded
    # name must be the actual NIM backing model, NOT the override target.
    # resolve_recorded_name must bypass the override map.
    assert resolve_recorded_name("openai/minimax-m3", None) == "minimaxai/minimax-m3", (
        "bracket pricing override leaked into recorded name"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_recorded_model_identity.py -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_recorded_name'`.

- [ ] **Step 3: Write minimal implementation**

First, add an override-excluding resolver to `bench_cli/pricing/litellm_config.py` (a thin sibling of `resolve_openrouter_id` that skips the override-map step — B4). Add this new function after `resolve_openrouter_id`:

```python
def resolve_backing_model_id(alias: str) -> str | None:
    """Resolve a bench alias to its actual backing OpenRouter id, IGNORING the
    pricing override map.

    Use this (not resolve_openrouter_id) when you need the *real* backing model
    for identity/recording, not the pricing correction. The bracket pricing
    override (logs/pricing/model_overrides.json) is pricing-only and must not
    leak into the recorded model identity (spec Non-Goal).

    Resolution order (no step 1 override lookup):
      1. MODEL_ALIAS_MAP — static alias -> OpenRouter id (if in cache).
      2. LiteLLM config -> verify slug in cache (or return slug for caller to decide).
    """
    from bench_cli.pricing.price_cache import OpenRouterCache
    from bench_cli.pricing.model_aliases import MODEL_ALIAS_MAP

    cache = OpenRouterCache()
    all_prices = cache.get_all_prices()

    # 1. MODEL_ALIAS_MAP (deterministic static), verified in cache
    if not is_managed_model(alias):
        mapped_id = MODEL_ALIAS_MAP.get(alias)
        if mapped_id is not None and mapped_id in all_prices:
            return mapped_id

    # 2. LiteLLM config resolution
    litellm_id = _resolve_from_litellm(alias)
    return litellm_id  # may be None; caller decides
```

Then in `bench_cli/run/core.py`, add after the `parse_model_arg` function (end of the "Parse" area, ~line 175):

```python
def resolve_recorded_name(routed_name: str, as_name: str | None) -> str:
    """Compute the model identity to record in eval logs.

    Order (first match wins):
      1. --as given -> the literal --as value (no prefix applied).
      2. Managed/local model (is_managed_model) -> routed_name unchanged.
         MUST short-circuit before the resolver: the pricing resolver returns
         non-None LiteLLM ids for some managed models (e.g. qwen-local ->
         huihui-qwen3.5-35b-a3b-claude-4.6-opus-abliterated), which would
         silently corrupt local-model identity.
      3. resolve_backing_model_id(routed_name) -> raw OpenRouter id of the actual
         backing model (B4: bypasses the pricing override map, so e.g.
         openai/minimax-m3 records minimaxai/minimax-m3, NOT the override target
         minimax/minimax-m3).
      4. Resolver returns None -> routed_name unchanged (unknown alias).

    Args:
      routed_name: the --model value sent to the proxy (e.g. "openai/thinking").
      as_name: the --as value, or None.

    Returns:
      The recorded identity (full OR id, or --as literal, or routed fallback).
    """
    from bench_cli.pricing.litellm_config import is_managed_model, resolve_backing_model_id

    if as_name is not None:
        return as_name
    if is_managed_model(routed_name):
        return routed_name
    or_id = resolve_backing_model_id(routed_name)
    if or_id is not None:
        return or_id
    return routed_name
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_recorded_model_identity.py -v`
Expected: PASS (8 tests). If `test_moniker_resolves_to_openrouter_id` fails, check the live LiteLLM config — `thinking` may have rebound. Update the expected value to match the actual current resolution and note it in the commit message (the test asserts current resolution, which is the point).

- [ ] **Step 5: Commit**

```bash
git add bench_cli/pricing/litellm_config.py bench_cli/run/core.py tests/test_recorded_model_identity.py
git commit -m "feat(run): resolve_recorded_name — routing-vs-recorded (bypasses bracket override)

B4: uses new resolve_backing_model_id, not resolve_openrouter_id, so the
pricing [bracket] override map never leaks into the recorded model identity.
Managed models short-circuit before resolution."
```

---

## Task 3: `rewrite_log_model_name()` (non-fatal log rewrite)

**Files:**
- Modify: `bench_cli/run/core.py` (add `rewrite_log_model_name` after `resolve_recorded_name`)
- Test: `tests/test_recorded_model_identity.py` (extend; add fixture log if none exists)

**Interfaces:**
- Consumes: `inspect_ai.log.read_eval_log`, `write_eval_log` (existing).
- Produces: `rewrite_log_model_name(log_path: Path | str, recorded_name: str) -> bool` — True if log now holds `recorded_name` (or already did); False on non-fatal error. Consumed by Task 5.

**Note on fixture log:** Use the committed fixture at `tests/fixtures/eval-logs/sample_success.eval` (a real 22KB 4-sample success log, model `openai/deepseek-4-pro`, with all 4 scorers). Copy it into a temp dir for each test so the real logs/ tree is never mutated. This keeps the test portable (no dependency on `logs/` existing — R4). The rewrite has been verified against inspect-ai 0.3.210 to preserve samples + all 4 scorers.

**Fixture already committed** (before this task runs): `tests/fixtures/eval-logs/sample_success.eval`. If it is missing, regenerate from a real log:
```bash
.venv/bin/python -c "from inspect_ai.log import list_eval_logs, read_eval_log; from pathlib import Path; [print(Path(i.name.replace('file://','')).stat().st_size, i.name) for i in __import__('inspect_ai.log',fromlist=['list_eval_logs']).list_eval_logs(log_dir='logs')[:5]]"
```
and copy the smallest success `.eval` to `tests/fixtures/eval-logs/sample_success.eval`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_recorded_model_identity.py`:

```python
import shutil
import tempfile
from pathlib import Path

from inspect_ai.log import read_eval_log

from bench_cli.run.core import rewrite_log_model_name


_FIXTURE = Path(__file__).parent / "fixtures" / "eval-logs" / "sample_success.eval"


def _copy_fixture(dest_dir: Path) -> Path:
    """Copy the committed fixture log into dest_dir; return its path."""
    assert _FIXTURE.is_file(), f"fixture missing: {_FIXTURE}"
    dest = dest_dir / _FIXTURE.name
    shutil.copy2(_FIXTURE, dest)
    return dest


def test_rewrite_changes_eval_model_and_preserves_samples():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        log_path = _copy_fixture(td)
        before = read_eval_log(str(log_path))
        before_samples = len(before.samples or [])
        before_scorers = [s.name for s in (before.results.scores if before.results and before.results.scores else [])]
        original_model = before.eval.model

        ok = rewrite_log_model_name(log_path, "minimaxai/minimax-m3")

        assert ok is True
        after = read_eval_log(str(log_path))
        assert after.eval.model == "minimaxai/minimax-m3"
        assert after.eval.model != original_model
        # samples preserved
        assert len(after.samples or []) == before_samples
        # all scorers preserved
        after_scorers = [s.name for s in (after.results.scores if after.results and after.results.scores else [])]
        assert after_scorers == before_scorers


def test_rewrite_idempotent_when_already_recorded():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        log_path = _copy_fixture(td)
        # First rewrite to a known value
        assert rewrite_log_model_name(log_path, "x/y-model") is True
        # Second rewrite to the same value is a no-op (still True)
        assert rewrite_log_model_name(log_path, "x/y-model") is True
        after = read_eval_log(str(log_path))
        assert after.eval.model == "x/y-model"


def test_rewrite_non_fatal_on_missing_file():
    ok = rewrite_log_model_name(Path("/nonexistent/path/foo.eval"), "whatever")
    assert ok is False  # does not raise


def test_rewrite_non_fatal_on_corrupt_zip():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        bad = td / "broken.eval"
        bad.write_text("not a zip file at all")  # corrupt
        ok = rewrite_log_model_name(bad, "whatever")
        assert ok is False  # does not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_recorded_model_identity.py -v`
Expected: FAIL — `ImportError: cannot import name 'rewrite_log_model_name'`.

- [ ] **Step 3: Write minimal implementation**

In `bench_cli/run/core.py`, add after `resolve_recorded_name`:

```python
def rewrite_log_model_name(log_path: "Path | str", recorded_name: str) -> bool:
    """Rewrite an eval log's eval.model to recorded_name. Non-fatal.

    Read -> set el.eval.model -> write_eval_log. Verified to preserve samples
    and all scorer Score objects under inspect-ai 0.3.210.

    Args:
      log_path: path to the .eval file (file:// prefix stripped if present).
      recorded_name: the model identity to store in eval.model.

    Returns:
      True if the log now holds recorded_name (or already did); False on any
      error (missing file, corrupt zip, permission). Never raises — a long
      sequential run must not be lost to a relabeling I/O hiccup.
    """
    from inspect_ai.log import read_eval_log, write_eval_log

    p = str(log_path)
    if p.startswith("file://"):
        p = p[len("file://"):]
    try:
        el = read_eval_log(p)
        if el.eval is None:
            return False
        if el.eval.model == recorded_name:
            return True  # already correct, no write needed
        el.eval.model = recorded_name
        write_eval_log(el, p)
        return True
    except Exception:
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_recorded_model_identity.py -v`
Expected: PASS (4 new tests + 7 from Task 2 = 11 total).

- [ ] **Step 5: Commit**

```bash
git add bench_cli/run/core.py tests/test_recorded_model_identity.py
git commit -m "feat(run): rewrite_log_model_name — non-fatal recorded-name rewrite"
```

---

## Task 4: Route display sites through `bare_model_name`

**Files:**
- Modify: `bench_cli/compare/core.py:376-378` (`_short_model`)
- Modify: `bench_cli/discriminative/subject.py:84-89` (`_normalize_model`)
- Test: extend `tests/test_bare_model_name.py`

**Interfaces:**
- Consumes: `bare_model_name` from Task 1.
- Produces: `_short_model` and `_normalize_model` now correctly derive bare names from OR-id inputs. Prerequisite for Tasks 6, 7.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bare_model_name.py`:

```python
def test_compare_short_model_handles_or_id():
    from bench_cli.compare.core import _short_model
    assert _short_model("minimaxai/minimax-m3") == "minimax-m3"
    assert _short_model("openai/thinking") == "thinking"


def test_discriminative_normalize_handles_or_id():
    from bench_cli.discriminative.subject import _normalize_model
    assert _normalize_model("nvidia/nemotron-3-ultra-550b-a55b") == "nemotron-3-ultra-550b-a55b"
    assert _normalize_model("openai/thinking") == "thinking"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_bare_model_name.py -v`
Expected: FAIL — `_short_model("minimaxai/minimax-m3")` returns `minimaxai/minimax-m3` (the current `.removeprefix("openai/")` leaves it unchanged).

- [ ] **Step 3: Write minimal implementation**

In `bench_cli/compare/core.py`, update the import (top of file) to add:

```python
from bench_cli.resolver import bare_model_name
```

Replace `_short_model` (lines ~376-378, currently `return name.removeprefix("openai/")`):

```python
def _short_model(name: str) -> str:
    """Strip the first path segment for display (openai/x or minimaxai/x -> x)."""
    return bare_model_name(name)
```

In `bench_cli/discriminative/subject.py`, add to imports:

```python
from bench_cli.resolver import bare_model_name
```

Replace `_normalize_model` (lines ~84-89, currently splits on `/`):

```python
def _normalize_model(model: str) -> str:
    """Strip provider prefix (e.g. minimaxai/minimax-m3 -> minimax-m3)."""
    return bare_model_name(model)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_bare_model_name.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Verify broader compare/discriminative test suite**

Run: `.venv/bin/pytest tests/ -k "compare or discriminative or subject" -q 2>&1 | tail -10`
Expected: PASS — no regressions. Display-only change for existing `openai/`-prefixed names.

- [ ] **Step 6: Commit**

```bash
git add bench_cli/compare/core.py bench_cli/discriminative/subject.py tests/test_bare_model_name.py
git commit -m "refactor: route _short_model/_normalize_model through bare_model_name"
```

---

## Task 5: `--as` flag + thread `recorded_name` through `bench run` (the core hook)

**Files:**
- Modify: `bench_cli/run/cli.py` (add `--as` option ~line 280; compute `recorded_name` after `parse_model_arg` ~line 297; substitute at `inspect_eval` sites `:391`,`:425`, resume `:352`, price-gate `:332`, status `_status_path` calls, summary, card-gen)
- Test: `tests/test_run_recorded_name.py` (create) — uses Click's CliRunner with mocked `inspect_eval`

**Interfaces:**
- Consumes: `resolve_recorded_name`, `rewrite_log_model_name` from Tasks 2–3.
- Produces: `bench run --model X [--as Y]` writes logs whose `el.eval.model` = recorded name; resume/price-gate/status/summary/card-gen all key on recorded name.

**Design note:** `bench_alias` is the single variable threaded through `run/cli.py`. We introduce `routed_name = bench_alias` and `recorded_name = resolve_recorded_name(bench_alias, as_name)`, then use `recorded_name` everywhere `bench_alias` was previously used for *identity* (resume, status path, summary, card-gen), while `routed_name` is passed to `inspect_eval(model=...)`. **The price gate stays on `bench_alias`** (B1: `_check_price_gate` resolves the *routed* alias via `resolve_openrouter_id`; for a recorded OR id that resolver returns None and the gate no-ops — so price-gating MUST use the routing name). The `[bracket]` override path still uses `bench_alias`/`parse_model_arg`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_run_recorded_name.py`. Key points (B2 + B3 fixes):
- `inspect_eval` is imported **lazily inside `run()`** (`bench_cli/run/cli.py:273`), so monkeypatching `bench_cli.run.cli.inspect_eval` raises `AttributeError`. Patch the **source**: `inspect_ai.eval` (the `eval` name in the `inspect_ai` package).
- The fake copies the committed fixture log (`tests/fixtures/eval-logs/sample_success.eval`) to the run's `log_dir`, then re-reads it so the returned object has a real `.location`. This avoids constructing an `EvalLog`/`EvalSpec` by hand (which requires `created`/`dataset`/`config` and raises `ValidationError`).

```python
"""End-to-end test of --as / recorded-name threading in `bench run`.

Patches inspect_ai.eval (inspect_eval is imported lazily inside run(), so we
patch the source name, not bench_cli.run.cli.inspect_eval) and uses the
committed fixture log so no hand-built EvalLog is needed.
"""
import shutil
from pathlib import Path

from click.testing import CliRunner
from inspect_ai.log import read_eval_log

from bench_cli.run.cli import run as run_cmd


_FIXTURE = Path(__file__).parent / "fixtures" / "eval-logs" / "sample_success.eval"


def fake_inspect_eval_factory(received: dict):
    """Return a fake inspect_eval that records routed_model and copies the fixture."""
    def _fake(tasks=None, model=None, **kwargs):
        received["model"] = model
        log_dir = kwargs.get("log_dir", "logs")
        dest = Path(log_dir) / _FIXTURE.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_FIXTURE, dest)
        # Return a list with one re-read EvalLog (so .location points at dest).
        return [read_eval_log(str(dest))]
    return _fake


def test_as_flag_records_custom_name_and_routes_through_model(monkeypatch, tmp_path):
    received = {}
    # B2: patch the source name (inspect_eval is imported lazily inside run()).
    import inspect_ai
    monkeypatch.setattr(inspect_ai, "eval", fake_inspect_eval_factory(received))

    runner = CliRunner()
    result = runner.invoke(
        run_cmd,
        [
            "--model", "openai/thinking",
            "--as", "nemotron-ultra-550b",
            "--tier", "quick",
            "--task", "smoke",
            "--log-dir", str(tmp_path),
            "--no-compare",
            "--no-tui",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    # Routed name hit the proxy
    assert received["model"] == "openai/thinking"
    # The written log records the --as name
    logs = list(Path(tmp_path).glob("*.eval"))
    assert logs, f"no log written in {tmp_path}"
    el = read_eval_log(str(logs[0]))
    assert el.eval.model == "nemotron-ultra-550b"


def test_no_as_flag_records_openrouter_id(monkeypatch, tmp_path):
    received = {}
    import inspect_ai
    monkeypatch.setattr(inspect_ai, "eval", fake_inspect_eval_factory(received))

    runner = CliRunner()
    result = runner.invoke(
        run_cmd,
        [
            "--model", "openai/thinking",
            "--tier", "quick",
            "--task", "smoke",
            "--log-dir", str(tmp_path),
            "--no-compare",
            "--no-tui",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert received["model"] == "openai/thinking"
    logs = list(Path(tmp_path).glob("*.eval"))
    el = read_eval_log(str(logs[0]))
    # thinking currently backs minimax-m3
    assert el.eval.model == "minimaxai/minimax-m3"
```

**Note on the patch target:** `from inspect_ai import eval as inspect_eval` binds the name `inspect_eval` to the object `inspect_ai.eval` AT IMPORT TIME (when `run()` executes line 273). Patching `inspect_ai.eval` BEFORE `run()` imports it makes the lazy `from inspect_ai import eval` pick up the patched object. This is the standard way to patch lazily-imported names. Verify empirically in Step 2 — if the patch isn't picked up, fall back to patching the object the import resolves to: `monkeypatch.setattr("inspect_ai._eval.eval", fake)` is NOT needed because `inspect_ai.eval` is the public re-export; the public-name patch is correct.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_run_recorded_name.py -v`
Expected: FAIL — `--as` is an unrecognized option (`Error: no such option: --as`), and logs currently record the routed name. (If the monkeypatch itself raises, confirm the patch target is `inspect_ai.eval`; the RED state is still the `--as` / recorded-name assertion failing.)

- [ ] **Step 3: Write minimal implementation**

In `bench_cli/run/cli.py`:

**(a)** Add the `--as` Click option. Find the `@click.option("--max-retries", ...)` block (near line 268) and add after it (before `def run(`):

```python
@click.option(
    "--as",
    "as_name",
    default=None,
    help=(
        "Recorded model identity to write into eval logs, overriding the "
        "auto-resolved OpenRouter id. Use when you route through a moniker "
        "(e.g. openai/thinking) but want logs/compare/cards to show a "
        "recognizable name (e.g. 'nemotron-ultra-550b'). Stored literally, no "
        "prefix applied. Without --as, logs record the raw OpenRouter id "
        "(e.g. 'minimaxai/minimax-m3'); managed/local models keep their alias."
    ),
)
```

**(b)** Add `as_name: str | None` to the `run(...)` function signature, after `max_retries: int | None`.

**(c)** Compute `routed_name` / `recorded_name`. After the existing block:
```python
    bench_alias, or_override = parse_model_arg(model)
```
add immediately (before the `if or_override is not None:` block, so the override still saves correctly):

```python
    # recorded_name: identity written into eval logs (recognizable). routed_name:
    # identity sent to the proxy (the --model value).
    from bench_cli.run.core import resolve_recorded_name, rewrite_log_model_name

    routed_name = bench_alias
    recorded_name = resolve_recorded_name(routed_name, as_name)
    if recorded_name != routed_name:
        click.echo(
            f"Recording model as '{recorded_name}' (routing through '{routed_name}')."
        )
```

**(d)** Thread `recorded_name` into identity uses. Throughout the function body, every use of `bench_alias` for *identity* (not the `[bracket]` override save) becomes `recorded_name`:
- `click.echo(f"Running {len(specs)} task(s) from tier '{tier}' with model '{recorded_name}'.")` (the line ~330)
- `_check_price_gate(bench_alias)` — **KEEP as `bench_alias` (the routing name)**. The price gate resolves the *routed* alias to a price via `resolve_openrouter_id`; a recorded OR id would resolve to None and silently disable the gate (B1). Do NOT change this to `recorded_name`.
- `done = _completed_tasks(log_dir, recorded_name, spec_dirs)` (the resume block)
- `heartbeat = _status_path(log_dir, recorded_name)` (one-by-one mode)
- `inspect_eval(..., model=routed_name, ...)` at BOTH call sites (one-by-one ~:391 and batch ~:425) — **use `routed_name` here**, not recorded_name.
- After each result is obtained, rewrite. In one-by-one mode, after `all_results.extend(result)`:
  ```python
            if recorded_name != routed_name:
                  for r in result:
                      ok = rewrite_log_model_name(r.location, recorded_name)
                      if not ok:
                          click.echo(
                              f"  Warning: could not rewrite model name in {getattr(r, 'location', '?')}; "
                              f"log keeps routed name '{routed_name}'.",
                              err=True,
                          )
  ```
  In batch mode, after `results = inspect_eval(...)`:
  ```python
        if recorded_name != routed_name:
            for r in results:
                ok = rewrite_log_model_name(r.location, recorded_name)
                if not ok:
                    click.echo(
                        f"Warning: could not rewrite model name in {getattr(r, 'location', '?')}; "
                        f"log keeps routed name '{routed_name}'.",
                        err=True,
                    )
  ```
- `_write_run_summary(..., bench_alias=recorded_name, results=results)` (was `bench_alias=bench_alias`)
- The final summary loop and card generation: `generate_card_for_model(recorded_name, ...)` (was `bench_alias`).

**Note on the price gate (B1):** `_check_price_gate` uses `bench_alias` (routing name), NOT `recorded_name`. Keep that line unchanged. `bench_alias` and `recorded_name` differ only when routing-vs-recording differ; the price gate cares about the routed model's price, so it uses the routing alias. `recorded_name` is used for everything that keys on *identity* (resume, status, summary, card-gen).

**Note on the `[bracket]` override:** the existing block `if or_override is not None: save_override(bench_alias, or_override)` continues to use `bench_alias` (routing alias) — correct, since the override is keyed on the routing alias. It remains pricing-only and does not affect the recorded name (B4 fix in Task 2 ensures `resolve_recorded_name` bypasses it).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_run_recorded_name.py -v`
Expected: PASS (2 tests). The fake copies the real fixture log (a valid binary), so no EvalLog construction is needed — B3 avoided entirely.

- [ ] **Step 5: Verify --help and existing run tests**

Run: `.venv/bin/python -m bench_cli run --help 2>&1 | grep -A2 '\-\-as '`
Expected: the `--as` help text appears.

Run: `.venv/bin/pytest tests/ -k "run" -q 2>&1 | tail -10`
Expected: PASS — no regressions in existing run tests.

- [ ] **Step 6: Commit**

```bash
git add bench_cli/run/cli.py tests/test_run_recorded_name.py
git commit -m "feat(run): --as flag + recorded-name threading (routing vs recorded identity)"
```

---

## Task 6: Discriminative subject identity from `el.eval.model` (primary)

**Files:**
- Modify: `bench_cli/discriminative/subject.py:34-43` (`resolve_subject_from_log` model extraction)
- Test: `tests/test_discriminative_subject.py` (create or extend)

**Interfaces:**
- Consumes: `bare_model_name` (Task 1).
- Produces: `resolve_subject_from_log()` returns the recorded model (from `el.eval.model`), not the routed moniker. Aligns subject identity with `get_all_log_paths` dedup.

- [ ] **Step 1: Write the failing test**

Create `tests/test_discriminative_subject.py`. **B2 fix:** `read_eval_log` is imported lazily *inside* `resolve_subject_from_log` (`subject.py:28`), so patching `bench_cli.discriminative.subject.read_eval_log` raises `AttributeError`. Patch the **source** name `inspect_ai.log.read_eval_log`.

```python
"""Subject identity comes from el.eval.model (recorded), not model_usage keys."""
from pathlib import Path

from bench_cli.discriminative.subject import resolve_subject_from_log


def test_subject_uses_eval_model_not_model_usage_key(monkeypatch, tmp_path):
    # Simulate a rewritten log: eval.model is the recorded OR id, but
    # model_usage keys are the routed moniker (as real logs have).
    class FakeSample:
        model_usage = {"openai/thinking": object(), "openai/judge": object()}

    class FakeEval:
        model = "minimaxai/minimax-m3"
        task = "smoke"
        sandbox = None
        solver_args = None

    class FakeLog:
        samples = [FakeSample()]
        eval = FakeEval()

    # B2: read_eval_log is imported lazily inside resolve_subject_from_log,
    # so patch the SOURCE name, not the consumer module attribute.
    import inspect_ai.log
    monkeypatch.setattr(inspect_ai.log, "read_eval_log", lambda *a, **k: FakeLog())

    sid = resolve_subject_from_log(Path("/fake/x.eval"))
    assert sid.model == "minimaxai/minimax-m3", (
        f"expected recorded OR id, got {sid.model!r} (model_usage key leak)"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_discriminative_subject.py -v`
Expected: FAIL — `sid.model == "openai/thinking"` (the current code reads `model_usage` keys first).

- [ ] **Step 3: Write minimal implementation**

In `bench_cli/discriminative/subject.py`, replace the model-extraction block in `resolve_subject_from_log` (lines ~34-43, the block that reads `model_usage` first):

```python
    # Model identity: PRIMARY source is el.eval.model (the recorded name after
    # the --as/rewrite path). model_usage keys are ROUTED names (monikers) and
    # would re-introduce the moniker-as-subject problem; use them only as a
    # fallback for legacy logs whose eval.model was never rewritten.
    model = el.eval.model if (el.eval and el.eval.model) else None
    if model is None:
        if el.samples and el.samples[0].model_usage:
            for key in el.samples[0].model_usage:
                if "judge" not in key.lower():
                    model = key
                    break
            if model is None:
                model = next(iter(el.samples[0].model_usage))
    if model is None:
        model = "unknown"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_discriminative_subject.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Verify discriminative suite + dedup alignment**

Run: `.venv/bin/pytest tests/ -k "discriminative or subject" -q 2>&1 | tail -10`
Expected: PASS — no regressions.

- [ ] **Step 6: Commit**

```bash
git add bench_cli/discriminative/subject.py tests/test_discriminative_subject.py
git commit -m "fix(discriminative): subject identity from el.eval.model (recorded), not model_usage"
```

---

## Task 7: `bench_cli/inspect` resolve recorded name before filtering

**Files:**
- Modify: `bench_cli/inspect/core.py:131, 323, 347` (the 3 `el.eval.model != model_alias` filters)
- Test: `tests/test_inspect_recorded_name.py` (create)

**Interfaces:**
- Consumes: `resolve_recorded_name` from Task 2.
- Produces: `bench inspect --model X` finds rewritten logs whether X is the routing alias or the recorded OR id.

- [ ] **Step 1: Write the failing test**

Create `tests/test_inspect_recorded_name.py`:

```python
"""bench inspect must find rewritten logs by routing alias OR recorded name."""
from bench_cli.inspect.core import _resolve_query_name


def test_resolve_query_name_passes_recorded_through():
    # If user queries with the routing alias, resolve to recorded OR id
    assert _resolve_query_name("openai/thinking") == "minimaxai/minimax-m3"


def test_resolve_query_name_passes_or_id_through():
    # If user queries with an OR id, it's already recorded form -> unchanged
    assert _resolve_query_name("minimaxai/minimax-m3") == "minimaxai/minimax-m3"


def test_resolve_query_name_managed_passthrough():
    assert _resolve_query_name("openai/qwen-local") == "openai/qwen-local"


def test_resolve_query_name_custom_as_is_opaque():
    # R5: a custom --as value with no LiteLLM backing resolves to itself.
    # Users query such logs by the literal --as value (matched via raw input).
    # NOTE: use a genuinely opaque name — 'nemotron-ultra-550b' is NOT opaque
    # (it resolves via LiteLLM to nvidia/nemotron-3-ultra-550b-a55b).
    assert _resolve_query_name("my-custom-label") == "my-custom-label"
```

**Note:** `_resolve_query_name` is a new tiny helper this task introduces in `inspect/core.py` — it wraps `resolve_recorded_name(q, None)` (Task 2, post-B4) so the 3 filter sites can compare against BOTH the user input and its resolved recorded form.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_inspect_recorded_name.py -v`
Expected: FAIL — `ImportError: cannot import name '_resolve_query_name'`.

- [ ] **Step 3: Write minimal implementation**

In `bench_cli/inspect/core.py`, add the helper near the top (after imports):

```python
def _resolve_query_name(model_alias: str) -> str:
    """Resolve a user-supplied inspect --model to the recorded-name form.

    Logs store the recorded identity (OR id or --as value). When a user queries
    by a routing alias, resolve it through the same path bench run uses so the
    el.eval.model filter matches. Querying by an already-recorded OR id is a
    no-op (resolve_recorded_name is idempotent on OR ids).

    NOTE (R5): a log recorded via `--as <custom>` is NOT discoverable from the
    routing alias (the custom name has no LiteLLM backing to resolve to); users
    must query such logs by the literal `--as` value. Both forms are matched
    because the filter accepts EITHER the raw user input OR the resolved form.
    """
    from bench_cli.run.core import resolve_recorded_name

    return resolve_recorded_name(model_alias, None)
```

Then, at each of the 3 filter sites (lines ~131, ~323, ~347), **hoist the resolution out of the per-log loop** (R2: it loads the price cache + LiteLLM config, so compute once). The surrounding function has a loop like `for info in infos:`; add before the loop:

```python
        resolved_query = _resolve_query_name(model_alias)
```

and change the filter from:
```python
        if el.eval.model != model_alias:
            continue
```
to:
```python
        if el.eval.model not in (model_alias, resolved_query):
            continue
```

(A log matches if its `el.eval.model` equals EITHER the raw user input OR the resolved recorded form — covering "query by alias", "query by OR id", and "query by bare name" uniformly. The literal `--as` value still matches via the raw `model_alias` branch.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_inspect_recorded_name.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Verify inspect suite**

Run: `.venv/bin/pytest tests/ -k "inspect" -q 2>&1 | tail -10`
Expected: PASS — no regressions. Existing tests querying by `openai/...` aliases still match (their logs still carry `openai/...` until rewritten; the OR-form comparison is a no-op for them since both sides resolve to the same string).

- [ ] **Step 6: Commit**

```bash
git add bench_cli/inspect/core.py tests/test_inspect_recorded_name.py
git commit -m "fix(inspect): resolve recorded name before el.eval.model filters"
```

---

## Task 8: Results card slug/name + `is_moniker_alias` for OR ids

**Files:**
- Modify: `bench_cli/results/core.py:36-80` (`_ROUTER_MONIKERS`, `is_moniker_alias`, `_slug_from_alias`, `_real_model_name`) and verify `_get_model_metadata:383-421`
- Test: `tests/test_results_slug.py` (create or extend)

**Interfaces:**
- Consumes: `bare_model_name` (Task 1).
- Produces: card filenames slugged from the recorded OR id (`minimaxai-minimax-m3.md`); display names via `bare_model_name`; `is_moniker_alias` correctly returns False for OR ids.

**Design note:** Current `_slug_from_alias`/`_real_model_name` deliberately key off the static `MODEL_ALIAS_MAP` (a recently-landed NVIDIA-sweep fix). Once the recorded name IS the OR id, that static map is redundant (its value equals the recorded name). Removing it is **intentional**, not a regression. Keep the deterministic property: derive slug/name from the input string alone, never from `resolve_openrouter_id`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_results_slug.py`:

```python
from bench_cli.results.core import _slug_from_alias, _real_model_name, is_moniker_alias


def test_slug_from_or_id():
    assert _slug_from_alias("minimaxai/minimax-m3") == "minimaxai-minimax-m3"
    assert _slug_from_alias("nvidia/nemotron-3-ultra-550b-a55b") == "nvidia-nemotron-3-ultra-550b-a55b"


def test_real_model_name_from_or_id():
    assert _real_model_name("minimaxai/minimax-m3") == "minimaxai/minimax-m3"
    assert _real_model_name("nvidia/nemotron-3-ultra-550b-a55b") == "nvidia/nemotron-3-ultra-550b-a55b"


def test_is_moniker_alias_false_for_or_id():
    assert is_moniker_alias("minimaxai/minimax-m3") is False
    assert is_moniker_alias("nvidia/nemotron-3-ultra-550b-a55b") is False


def test_is_moniker_alias_true_for_moniker_bare():
    assert is_moniker_alias("openai/thinking") is True
    assert is_moniker_alias("openai/default") is True


def test_is_moniker_alias_false_for_custom_as():
    assert is_moniker_alias("nemotron-ultra-550b") is False


def test_get_model_metadata_provider_for_nvidia_or_id():
    # R1: spec Testing #5 — provider detection must work on recorded OR ids.
    from bench_cli.results.core import _get_model_metadata
    meta = _get_model_metadata("nvidia/nemotron-3-ultra-550b-a55b")
    assert meta["provider"] == "NVIDIA NIM", (
        f"expected NVIDIA NIM for OR id, got {meta['provider']!r}"
    )
    assert meta["free"] is False  # not a managed/local model
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_results_slug.py -v`
Expected: FAIL — e.g. `_slug_from_alias("minimaxai/minimax-m3")` currently returns `minimaxai-minimax-m3` only if it happened to be in MODEL_ALIAS_MAP; for an arbitrary OR id it falls back to `.replace("openai/","").replace("/","-")` = `minimaxai-minimax-m3` (might pass by accident). `is_moniker_alias("minimaxai/minimax-m3")` — current code does `bare = bench_alias.replace("openai/","")` → `minimaxai/minimax-m3`, not in monikers → False (passes). The critical failing case is likely `_slug_from_alias` for an OR id whose static-map lookup returns None AND the fallback slug rule differs from "full name `/`→`-`". Inspect actual failures and fix to match the spec rule.

- [ ] **Step 3: Write minimal implementation**

In `bench_cli/results/core.py`:

Replace `_slug_from_alias` (lines ~57-67) with:

```python
def _slug_from_alias(bench_alias: str) -> str:
    """Deterministic card filename slug from the recorded name.

    Slug = the recorded full name with '/' -> '-'. The recorded name is the
    OpenRouter id (e.g. 'minimaxai/minimax-m3') or an --as value; either way
    we slug the whole string. NEVER calls resolve_openrouter_id.
    """
    return bench_alias.replace("/", "-")
```

Replace `_real_model_name` (lines ~70-79) with:

```python
def _real_model_name(bench_alias: str) -> str:
    """Deterministic human-readable model name = the recorded full name.

    Mirrors _slug_from_alias's source so name and slug always agree. The
    recorded OR id already carries the provider; display it in full (the
    compare table strips to bare via bare_model_name elsewhere).
    """
    return bench_alias
```

Replace `is_moniker_alias` (lines ~38-44) with:

```python
def is_moniker_alias(bench_alias: str) -> bool:
    """True if alias is a router-tier meta-moniker (default/thinking/heavy/...).

    Checks the BARE name (first segment stripped) so OR ids like
    'minimaxai/minimax-m3' (bare 'minimax-m3') are correctly False.
    """
    from bench_cli.resolver import bare_model_name

    return bare_model_name(bench_alias) in _ROUTER_MONIKERS
```

Remove the now-unused `_resolve_from_static_map` helper (lines ~46-51) and the `from bench_cli.pricing.model_aliases import MODEL_ALIAS_MAP` import at line 16 if no longer referenced elsewhere in the file (verify with `rg -n 'MODEL_ALIAS_MAP' bench_cli/results/core.py`).

- [ ] **Step 4: Verify `_get_model_metadata` works on OR ids**

Read `bench_cli/results/core.py:383-465`. The provider/hosting detection keys off `is_managed_model(bench_alias)`, `"nvidia" in bench_alias`, `"minimax" in litellm_model`, etc. For an OR id like `nvidia/nemotron-3-ultra-550b-a55b`: `"nvidia" in bench_alias` is True → provider NVIDIA. For `minimaxai/minimax-m3`: `litellm_model` lookup may miss (it's keyed by LiteLLM alias, not OR id), so the `"minimax" in litellm_model` check could fail → falls to generic "API"/"API". This is acceptable (cards still generate; provider label degrades gracefully). If you want it precise, add a fallback: after the existing elif chain, add:

```python
    # Fallback: infer provider from the recorded OR id prefix
    if provider == "API" and "/" in bench_alias:
        prov_prefix = bench_alias.split("/", 1)[0].lower()
        if prov_prefix == "nvidia":
            provider = "NVIDIA NIM"; hosting = "NVIDIA NIM"
        elif prov_prefix == "minimaxai":
            provider = "MiniMax"; hosting = "API"
        elif prov_prefix == "z-ai":
            provider = "Zhipu AI"; hosting = "API"
        # ... extend as needed for providers in MODEL_ALIAS_MAP values
```

This is optional polish; the test suite does not require it. Note any additions in the commit message.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_results_slug.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Verify full results suite**

Run: `.venv/bin/pytest tests/ -k "result or card" -q 2>&1 | tail -10`
Expected: PASS — no regressions. Existing cards (regenerated) will get new slugs only if their recorded names changed; old `openai/`-prefixed logs still slug predictably.

- [ ] **Step 7: Commit**

```bash
git add bench_cli/results/core.py tests/test_results_slug.py
git commit -m "feat(results): slug/name/is_moniker_alias from recorded OR id; drop redundant static map"
```

---

## Task 9: Full-suite verification + docs

**Files:**
- Modify: `README.md` (document `--as`), `docs/EVAL-GUIDE.md` if it mentions model identity (check), `AGENTS.md` if needed (probably not — it's deliberately minimal)
- No new code; verification + docs.

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/pytest -q 2>&1 | tail -15`
Expected: PASS — all tests green (was 587 collected before; now more). If any pre-existing test breaks due to the `openai/`-prefix removal in display, fix the test's expectation to the new bare-name behavior (this is intended).

- [ ] **Step 2: Collection smoke**

Run: `.venv/bin/pytest --co -q 2>&1 | tail -3`
Expected: "N tests collected" with no errors (N ≈ 597+).

- [ ] **Step 3: Manual smoke — --help shows --as**

Run: `.venv/bin/python -m bench_cli run --help 2>&1 | grep -A3 '\-\-as '`
Expected: the `--as` help text.

- [ ] **Step 4: Manual smoke — dry resolution**

Run:
```bash
.venv/bin/python -c "
from bench_cli.run.core import resolve_recorded_name
print('thinking ->', resolve_recorded_name('openai/thinking', None))
print('nemotron ->', resolve_recorded_name('openai/nemotron-ultra-550b', None))
print('qwen-local ->', resolve_recorded_name('openai/qwen-local', None))
print('--as ->', resolve_recorded_name('openai/thinking', 'nemotron-ultra-550b'))
"
```
Expected: OR id for thinking/nemotron, `openai/qwen-local` for managed, the `--as` literal.

- [ ] **Step 5: Update README quick reference**

In `README.md`, add a line to the "Model eval" section under Quick Reference:

```markdown
python -m bench_cli run --model openai/thinking --as nemotron-ultra-550b  # route via moniker, record recognizable name
```

And add a short note (R6 — resume-continuity caveat) below the model-eval block:

```markdown
# Resume note: re-running an existing model now records its OpenRouter id (e.g.
# 'z-ai/glm-5.2') instead of the old alias, so resume treats it as a new model
# and re-runs. To continue an old run in its old identity, pass
# --as openai/<old-alias>.
```

**R3 — document the `bench results generate --model` gap:** add a one-line note in `README.md` near the model-card section:
```markdown
# Note: after a --as / OR-id run, `bench results generate --model <alias>` won't
# match rewritten logs (they store the recorded name). Query by the recorded
# OpenRouter id or omit --model to regenerate all cards.
```

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: document bench run --as (routing vs recorded model identity)"
```

---

## Done Criteria

- [ ] `bench run --model openai/thinking --as nemotron-ultra-550b` routes through `thinking` and records `nemotron-ultra-550b` in logs/compare/cards.
- [ ] `bench run --model openai/thinking` (no `--as`) records `minimaxai/minimax-m3` (current backing model).
- [ ] `bench run --model openai/minimax-m3` records `minimaxai/minimax-m3` (NOT the bracket-override target `minimax/minimax-m3`).
- [ ] `bench run --model openai/qwen-local` records `openai/qwen-local` (managed short-circuit, NOT a LiteLLM id).
- [ ] `bench run --model openai/nemotron-ultra-550b` still passes the pre-flight price gate (gate uses the routing alias, B1).
- [ ] `bench inspect --model openai/thinking` finds rewritten logs.
- [ ] Discriminative subject identity = recorded OR id, not the routed moniker.
- [ ] Card filenames slug from the recorded OR id; `is_moniker_alias` is False for OR ids; provider detection works for NVIDIA OR ids.
- [ ] All tests green; collection smoke clean.
- [ ] Log rewrite is non-fatal (verified by test).

## Risks Handled in Plan

- **Managed-model corruption (spec B1):** Task 2's short-circuit + red test.
- **inspect regression (spec B2):** Task 7.
- **Wrong file for eval hook (spec B3):** Task 5 explicitly targets `run/cli.py:391,425`.
- **Discriminative source field (spec B4):** Task 6.
- **Price gate no-op on OR ids (review B1):** Task 5 Step 3d keeps `_check_price_gate(bench_alias)`.
- **Lazy-import monkeypatch (review B2):** Tasks 5 and 6 patch the SOURCE name (`inspect_ai.eval`, `inspect_ai.log.read_eval_log`), not the consumer module attribute.
- **Invalid EvalLog stub (review B3):** Tasks 3 and 5 use the committed fixture `tests/fixtures/eval-logs/sample_success.eval`; no hand-built EvalLog.
- **Bracket pricing override leaks into recorded name (review B4):** Task 2 adds `resolve_backing_model_id` (bypasses the override map) and a red test.
- **`_get_model_metadata` provider detection (review R1):** Task 8 test.
- **inspect loop perf (review R2):** Task 7 hoists `_resolve_query_name` out of the loop.
- **`bench results generate --model` gap (review R3):** Task 9 documents it.
- **Fixture portability (review R4):** committed fixture, not `logs/`.
- **inspect can't find `--as` logs by routing alias (review R5):** Task 7 docstring + test; matched via raw input.
- **Resume-continuity caveat (review R6):** Task 9 README note.
- **Moniker rebinds:** tests assert *current* resolution; note in commit if the underlying config drifts.
