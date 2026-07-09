# Inspect AI 0.3.245 Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Load subagent-driven-development/SKILL.md (recommended) or executing-plans/SKILL.md to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade bench from `inspect-ai==0.3.210` to `0.3.245` safely, preserve existing LiteLLM model eval behavior, and add a supported streaming route for `chatgpt/gpt-5.5` through the Codex/ChatGPT LiteLLM endpoint.

**Architecture:** Treat this as two related but separable changes: dependency/runtime upgrade first, then a small routing layer that can select Inspect's `openai-api` provider with streaming for `chatgpt/*` aliases. Reduce private Inspect API usage where it is easy, add compatibility sentinels where it is not, and validate with disposable eval logs so resume/cache cannot hide failures.

**Tech Stack:** Python, Inspect AI 0.3.245, inspect-swe 0.2.65, OpenAI Python SDK >=2.40.0, Click CLI, LiteLLM proxy, pytest.

## Global Constraints

- Use the project venv only: `.venv/bin/python`, `.venv/bin/pytest`, `.venv/bin/pip`.
- Models route through LiteLLM; do not call OpenAI/OpenRouter directly for bench evals.
- Do not treat router monikers (`default`, `thinking`, `heavy`, `background`, `smart-router`) as fixed model subjects.
- Resume is default-on; live smoke evals for this upgrade must use fresh disposable `--log-dir` and `--no-resume`.
- Preserve normal `openai/<alias>` routing semantics: Inspect strips `openai/`, proxy receives bare alias.
- `chatgpt/gpt-5.5` only works through LiteLLM with streaming; non-streaming is known-bad.
- For streaming GPT-5.5, request usage via `stream_options.include_usage=true` or token/cost pillars will be missing.
- Do not accept the upgrade on a vague "tests mostly pass" signal; classify pre-existing failures vs upgrade regressions.

---

## Current Evidence

- Installed project version: `inspect-ai==0.3.210`; latest: `0.3.245`.
- Latest Inspect requires new deps: dry-run would install `agent-client-protocol==0.11.0`, `anyio==4.14.1`, `fastapi==0.139.0`, `starlette==1.3.1`, `uvicorn==0.51.0`.
- `inspect-ai==0.3.245` OpenAI provider requires `openai>=2.40.0`; current `pyproject.toml` says only `openai>=1.0`.
- `inspect-swe==0.2.47` is installed; latest `0.2.65` requires `inspect-ai>=0.3.244` and aligns with current Agent Bridge changes.
- `openai-api/openai/chatgpt/gpt-5.5` + `stream=True` works through Inspect.
- With `GenerateConfig(extra_body={"stream_options": {"include_usage": True}})`, streaming `chatgpt/gpt-5.5` returns usage, e.g. `input_tokens=1634 output_tokens=5 total_tokens=1639`.
- Native `openai/chatgpt/gpt-5.5` remains bad for this endpoint:
  - default path takes Responses API and can assert/fail against LiteLLM;
  - `responses_api=False` uses non-streaming Chat Completions and gets LiteLLM 500.
- Subagent recon artifacts:
  - `.pi-subagents/artifacts/outputs/25b98dfa-fa68-4d52-a78d-7a94a0676a9b/inspect-upgrade/codebase-risk.md`
  - `.pi-subagents/artifacts/outputs/25b98dfa-fa68-4d52-a78d-7a94a0676a9b/inspect-upgrade/release-delta.md`
  - `.pi-subagents/artifacts/outputs/25b98dfa-fa68-4d52-a78d-7a94a0676a9b/inspect-upgrade/validation-plan.md`

---

## File Structure

- `pyproject.toml` — dependency floors for Inspect, OpenAI SDK, inspect-swe optional agent extra.
- `bench_cli/run/core.py` — task loading, task config merging, recorded-name resolution, provider metadata injection.
- `bench_cli/run/cli.py` — `bench run` model normalization, `inspect_ai.eval(...)` invocation, future `model_args` plumbing.
- `bench_cli/provider.py` — provider attribution from LiteLLM config; needs a `chatgpt/*` transport fallback.
- `bench_cli/pricing/litellm_config.py` — existing alias → OpenRouter ID resolution already handles `chatgpt/gpt-5.5` as `openai/gpt-5.5`.
- `bench_cli/solvers/multishot.py` — private `TaskState` import cleanup.
- `scorers/time_ratio.py` — private `sample_working_time`; keep but sentinel-test because no public equivalent was found.
- `scorers/price_ratio.py` — must prefer `bench_pricing_alias` metadata for `openai-api/...` routes so GPT-5.5 streaming evals keep cost scoring.
- `tests/test_inspect_compat.py` — new compatibility sentinels for Inspect APIs and provider behavior.
- `tests/test_run_model_routing.py` — new route normalization tests for normal aliases and `chatgpt/*` streaming aliases.

---

### Task 1: Establish/record the pre-upgrade baseline

**Files:**
- Modify: none unless you choose to commit a baseline note later.
- Test: existing test suite.

**Interfaces:**
- Consumes: current repo state and current `.venv`.
- Produces: a written list of pre-existing failures that must not be counted as Inspect regressions.

- [ ] **Step 1: Confirm versions**

Run:

```bash
cd /Users/rut/dev/bench
.venv/bin/python -m pip show inspect-ai inspect-swe openai pytest
```

Expected:

```text
Name: inspect_ai
Version: 0.3.210
...
Name: inspect_swe
Version: 0.2.47
...
```

- [ ] **Step 2: Collect tests**

Run:

```bash
.venv/bin/pytest --co -q
```

Expected:

```text
714 tests collected
```

- [ ] **Step 3: Run the full baseline once**

Run:

```bash
.venv/bin/pytest -q
```

Expected: either fully green, or the known red baseline from QA recon:

```text
700 passed, 14 failed
```

Known failures are live LiteLLM/proxy pricing/resolution drift around removed or changed aliases (`nemotron-*`, `kimi-2.6`, related pricing tests). If the failures differ, stop and classify before upgrading.

- [ ] **Step 4: Save the baseline output outside source code if needed**

Run:

```bash
mkdir -p /tmp/bench-inspect-upgrade
.venv/bin/pytest -q > /tmp/bench-inspect-upgrade/pre-upgrade-pytest.txt 2>&1 || true
```

Expected: `/tmp/bench-inspect-upgrade/pre-upgrade-pytest.txt` exists and captures the pre-upgrade truth.

---

### Task 2: Upgrade dependency floors deliberately

**Files:**
- Modify: `pyproject.toml`
- Test: dependency install/import checks.

**Interfaces:**
- Consumes: current dependency declarations.
- Produces: explicit dependency floors compatible with Inspect 0.3.245.

- [ ] **Step 1: Write failing dependency-floor assertions**

Create `tests/test_dependency_contract.py` with:

```python
from __future__ import annotations

from pathlib import Path


def test_inspect_upgrade_dependency_floors_are_explicit() -> None:
    text = Path("pyproject.toml").read_text()
    assert '"inspect-ai>=0.3.245,<0.4"' in text
    assert '"openai>=2.40.0"' in text
    assert '"inspect-swe>=0.2.65"' in text
```

Run:

```bash
.venv/bin/pytest -q tests/test_dependency_contract.py
```

Expected: FAIL because `pyproject.toml` still has older floors.

- [ ] **Step 2: Update `pyproject.toml` dependency lines**

Change:

```toml
dependencies = [
    "inspect-ai>=0.3.205",
    "openai>=1.0",
    "click>=8.0",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
agent = [
    "inspect-swe>=0.2.46",
    "anthropic>=0.30",
]
```

To:

```toml
dependencies = [
    "inspect-ai>=0.3.245,<0.4",
    "openai>=2.40.0",
    "click>=8.0",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
agent = [
    "inspect-swe>=0.2.65",
    "anthropic>=0.30",
]
```

- [ ] **Step 3: Install upgraded deps into the project venv**

Run:

```bash
.venv/bin/python -m pip install -U 'inspect-ai==0.3.245' 'openai>=2.40.0' 'inspect-swe>=0.2.65'
```

Expected: install succeeds. If pip reports a conflict around `fastapi`, `starlette`, `anyio`, or ACP, stop and inspect the resolver output rather than forcing.

- [ ] **Step 4: Verify imported versions**

Run:

```bash
.venv/bin/python - <<'PY'
import inspect_ai
import inspect_swe
import openai
print("inspect_ai", inspect_ai.__version__)
print("openai", openai.__version__)
print("inspect_swe", getattr(inspect_swe, "__version__", "unknown"))
PY
```

Expected:

```text
inspect_ai 0.3.245
openai 2.40.0-or-newer
inspect_swe 0.2.65-or-newer
```

- [ ] **Step 5: Verify dependency test passes**

Run:

```bash
.venv/bin/pytest -q tests/test_dependency_contract.py
```

Expected: PASS.

---

### Task 3: Remove avoidable private Inspect imports and preserve new Task fields

**Files:**
- Modify: `bench_cli/run/core.py`
- Modify: `bench_cli/solvers/multishot.py`
- Test: `tests/test_inspect_compat.py`

**Interfaces:**
- Consumes: Inspect public `GenerateConfig`, public `TaskState`.
- Produces: lower-risk compatibility with future Inspect releases.

- [ ] **Step 1: Add failing import compatibility tests**

Create `tests/test_inspect_compat.py` with:

```python
from __future__ import annotations

import inspect


def test_inspect_eval_accepts_bench_kwargs() -> None:
    from inspect_ai import eval as inspect_eval

    params = set(inspect.signature(inspect_eval).parameters)
    for name in {
        "tasks",
        "model",
        "model_args",
        "solver",
        "sandbox",
        "log_dir",
        "fail_on_error",
        "retry_on_error",
        "max_tasks",
        "max_samples",
        "display",
        "metadata",
    }:
        assert name in params


def test_public_generate_config_and_task_state_imports() -> None:
    from inspect_ai.model import GenerateConfig
    from inspect_ai.solver import TaskState

    cfg = GenerateConfig(timeout=600, attempt_timeout=300)
    assert cfg.timeout == 600
    assert cfg.attempt_timeout == 300
    assert TaskState is not None


def test_private_working_time_api_still_exists_for_latency_scorer() -> None:
    from inspect_ai._util.working import sample_working_time

    assert callable(sample_working_time)
```

Run:

```bash
.venv/bin/pytest -q tests/test_inspect_compat.py
```

Expected: PASS after dependency upgrade; if it fails, fix imports before proceeding.

- [ ] **Step 2: Replace private `GenerateConfig` import**

In `bench_cli/run/core.py`, replace:

```python
from inspect_ai._eval.task.run import GenerateConfig
```

With:

```python
from inspect_ai.model import GenerateConfig
```

- [ ] **Step 3: Replace private `TaskState` import**

In `bench_cli/solvers/multishot.py`, replace:

```python
from inspect_ai.solver._task_state import TaskState
```

With:

```python
from inspect_ai.solver import Generate, Solver, TaskState, generate, solver, use_tools
```

And remove `TaskState` from the private import line entirely.

- [ ] **Step 4: Preserve additive Inspect Task fields when reconstructing**

In `bench_cli/run/core.py`, extend the `Task(...)` reconstruction in `_resolve_task()` to copy new 0.3.245 fields safely with `getattr`:

```python
        checkpoint=getattr(task_obj, "checkpoint", None),
        on_checkpoint=getattr(task_obj, "on_checkpoint", None),
        on_resume=getattr(task_obj, "on_resume", None),
        score_on_error=getattr(task_obj, "score_on_error", None),
        turn_limit=getattr(task_obj, "turn_limit", None),
        viewer=getattr(task_obj, "viewer", None),
```

Place them next to the related existing `Task` kwargs (`sandbox`, `fail_on_error`, `message_limit`, etc.).

- [ ] **Step 5: Verify focused tests**

Run:

```bash
.venv/bin/pytest -q tests/test_inspect_compat.py tests/test_scorers.py::TestMultishotSolver
```

Expected: PASS, except any known unrelated live-config drift must be outside these selected tests.

---

### Task 4: Add explicit model routing for `chatgpt/*` streaming endpoints

**Files:**
- Modify: `bench_cli/run/core.py`
- Modify: `bench_cli/run/cli.py`
- Modify: `bench_cli/provider.py`
- Modify: `scorers/price_ratio.py`
- Test: `tests/test_run_model_routing.py`
- Test: `tests/test_scorers.py`

**Interfaces:**
- Consumes: user model input (`chatgpt/gpt-5.5`, `openai/chatgpt/gpt-5.5`, normal aliases).
- Produces: `routed_name`, `pricing_alias`, `provider_alias`, `recorded_name`, `model_args`, `config_overrides`.

- [ ] **Step 1: Add route object tests first**

Create `tests/test_run_model_routing.py` with:

```python
from __future__ import annotations


def test_normal_bare_alias_routes_through_openai_provider() -> None:
    from bench_cli.run.core import build_model_route

    route = build_model_route("go-kimi-k2.7-code", as_name=None)
    assert route.routed_name == "openai/go-kimi-k2.7-code"
    assert route.pricing_alias == "go-kimi-k2.7-code"
    assert route.provider_alias == "go-kimi-k2.7-code"
    assert route.model_args == {}
    assert route.config_overrides == {}


def test_normal_prefixed_alias_is_preserved() -> None:
    from bench_cli.run.core import build_model_route

    route = build_model_route("openai/go-kimi-k2.7-code", as_name=None)
    assert route.routed_name == "openai/go-kimi-k2.7-code"
    assert route.pricing_alias == "openai/go-kimi-k2.7-code"
    assert route.provider_alias == "openai/go-kimi-k2.7-code"
    assert route.model_args == {}


def test_chatgpt_alias_uses_openai_api_provider_streaming_and_usage(monkeypatch) -> None:
    from bench_cli.run.core import build_model_route

    # Keep this unit test hermetic. Exact recorded identity normally comes
    # from live LiteLLM config + pricing cache; patch that resolver path here.
    monkeypatch.setattr(
        "bench_cli.pricing.litellm_config.is_managed_model",
        lambda _alias: False,
    )
    monkeypatch.setattr(
        "bench_cli.pricing.litellm_config.resolve_backing_model_id",
        lambda alias: "openai/gpt-5.5" if alias == "chatgpt/gpt-5.5" else None,
    )

    route = build_model_route("chatgpt/gpt-5.5", as_name=None)
    assert route.routed_name == "openai-api/openai/chatgpt/gpt-5.5"
    assert route.provider_alias == "chatgpt/gpt-5.5"
    assert route.pricing_alias == "chatgpt/gpt-5.5"
    assert route.recorded_name == "openai/gpt-5.5"
    assert route.model_args == {"stream": True}
    assert route.config_overrides == {
        "extra_body": {"stream_options": {"include_usage": True}}
    }


def test_openai_chatgpt_alias_normalizes_to_same_streaming_route() -> None:
    from bench_cli.run.core import build_model_route

    route = build_model_route("openai/chatgpt/gpt-5.5", as_name=None)
    assert route.routed_name == "openai-api/openai/chatgpt/gpt-5.5"
    assert route.provider_alias == "chatgpt/gpt-5.5"
    assert route.pricing_alias == "chatgpt/gpt-5.5"
    assert route.model_args == {"stream": True}


def test_as_name_still_wins_for_chatgpt_route() -> None:
    from bench_cli.run.core import build_model_route

    route = build_model_route("chatgpt/gpt-5.5", as_name="gpt-5.5-codex")
    assert route.recorded_name == "gpt-5.5-codex"
```

Run:

```bash
.venv/bin/pytest -q tests/test_run_model_routing.py
```

Expected: FAIL because `build_model_route()` does not exist yet.

- [ ] **Step 2: Implement `ModelRoute` and `build_model_route()`**

In `bench_cli/run/core.py`, add near model parsing helpers:

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelRoute:
    """Resolved model routing contract for one bench run."""

    bench_alias: str
    routed_name: str
    recorded_name: str
    pricing_alias: str
    provider_alias: str
    model_args: dict[str, Any] = field(default_factory=dict)
    config_overrides: dict[str, Any] = field(default_factory=dict)


def _strip_openai_prefix(alias: str) -> str:
    return alias[len("openai/") :] if alias.startswith("openai/") else alias


def build_model_route(bench_alias: str, as_name: str | None) -> ModelRoute:
    """Resolve user model input into Inspect routing + bench attribution.

    Normal aliases use Inspect's native OpenAI provider (`openai/<alias>`).
    ChatGPT/Codex LiteLLM aliases must use Inspect's OpenAI-compatible provider
    with streaming because LiteLLM's `chatgpt/*` route fails for non-streaming
    calls.
    """
    bare_alias = _strip_openai_prefix(bench_alias)

    if bare_alias.startswith("chatgpt/"):
        routed_name = f"openai-api/openai/{bare_alias}"
        recorded_name = resolve_recorded_name(bare_alias, as_name)
        return ModelRoute(
            bench_alias=bench_alias,
            routed_name=routed_name,
            recorded_name=recorded_name,
            pricing_alias=bare_alias,
            provider_alias=bare_alias,
            model_args={"stream": True},
            config_overrides={
                "extra_body": {"stream_options": {"include_usage": True}}
            },
        )

    routed_name = f"openai/{bench_alias}" if "/" not in bench_alias else bench_alias
    return ModelRoute(
        bench_alias=bench_alias,
        routed_name=routed_name,
        recorded_name=resolve_recorded_name(bench_alias, as_name),
        pricing_alias=bench_alias,
        provider_alias=bench_alias,
    )
```

- [ ] **Step 3: Thread route through `bench_cli/run/cli.py`**

Replace the current `routed_name` / `recorded_name` block with:

```python
from bench_cli.run.core import build_model_route, rewrite_log_model_name

route = build_model_route(bench_alias, as_name)
routed_name = route.routed_name
recorded_name = route.recorded_name
```

Then change override saving and gates to use route aliases. The route must be built before the override block so bracket overrides for `openai/chatgpt/*[...]` are saved under the normalized pricing alias that the price gate checks:

```python
if or_override is not None:
    from bench_cli.pricing.litellm_config import save_override

    try:
        save_override(route.pricing_alias, or_override)
        if route.pricing_alias != bench_alias:
            save_override(bench_alias, or_override)
        click.echo(f"Override saved: {route.pricing_alias} -> {or_override}")
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from None

_check_price_gate(route.pricing_alias)
provider = resolve_provider(route.provider_alias)
```

Then pass `model_args` to both `inspect_eval(...)` calls:

```python
model_args=route.model_args,
```

Include it in both one-by-one and batch mode eval calls.

- [ ] **Step 4: Thread config overrides into `_resolve_task()`**

Change `_resolve_task(...)` signature in `bench_cli/run/core.py` to include both model-config overrides and the normalized pricing alias:

```python
    config_overrides_extra: dict | None = None,
    pricing_alias: str | None = None,
```

Merge it into existing config overrides:

```python
    config_overrides: dict = {}
    if orig_config is None or getattr(orig_config, "timeout", None) is None:
        config_overrides["timeout"] = 600
    if orig_config is None or getattr(orig_config, "attempt_timeout", None) is None:
        config_overrides["attempt_timeout"] = 300
    if config_overrides_extra:
        config_overrides.update(config_overrides_extra)
    config = GenerateConfig(**config_overrides)
```

Also inject pricing alias into each sample's metadata in the same loop that injects `bench_provider`:

```python
        if pricing_alias is not None:
            sample.metadata["bench_pricing_alias"] = pricing_alias
```

Change the CLI call site:

```python
        _resolve_task(
            spec,
            agent=agent,
            agent_mode=agent_mode,
            cc_model=cc_model,
            provider=provider,
            config_overrides_extra=route.config_overrides,
            pricing_alias=route.pricing_alias,
        )
```

- [ ] **Step 5: Make `price_ratio_scorer` prefer the normalized pricing alias**

In `scorers/price_ratio.py`, change:

```python
        model_alias = str(state.model)
```

To:

```python
        model_alias = (
            (state.metadata or {}).get("bench_pricing_alias")
            if state.metadata
            else None
        ) or str(state.model)
```

This is required for `openai-api/openai/chatgpt/gpt-5.5`: Inspect's routed model name is not the LiteLLM pricing alias, and bracket overrides are saved under `route.pricing_alias`.

Add a focused unit test inside `tests/test_scorers.py::TestPriceRatioScorer`:

```python
    def test_bench_pricing_alias_overrides_state_model(self):
        """openai-api streaming routes price by normalized LiteLLM alias."""
        from unittest.mock import patch

        from scorers.price_ratio import price_ratio_scorer
        from scorers.protocol import TaskBudget

        seen = {}

        def fake_resolve_and_price(model_alias, usage):
            seen["model_alias"] = model_alias
            return 0.0002, None, False, None

        s = price_ratio_scorer(task_budget=TaskBudget(reference_cost_usd=0.001))
        state = self._make_scored_state(
            "output",
            "openai-api/openai/chatgpt/gpt-5.5",
            100,
            50,
        )
        state.metadata = {
            "bench_pricing_alias": "chatgpt/gpt-5.5",
            "task_name": "smoke",
        }

        with patch(
            "scorers.price_ratio._resolve_and_price",
            side_effect=fake_resolve_and_price,
        ):
            result = run_async(s(state, state.target))

        assert seen["model_alias"] == "chatgpt/gpt-5.5"
        assert result.value == pytest.approx(5.0)
```

Run:

```bash
.venv/bin/pytest -q tests/test_scorers.py::TestPriceRatioScorer::test_bench_pricing_alias_overrides_state_model
```

Expected: PASS.

- [ ] **Step 6: Teach provider resolution about `chatgpt/*` LiteLLM entries**

In `bench_cli/provider.py`, after the inline credentials branch and before returning `None`, add a transport fallback for ChatGPT routes:

```python
    model_field = params.get("model")
    if isinstance(model_field, str) and model_field.startswith("chatgpt/"):
        return "chatgpt"
```

This is intentionally narrow. Do not add a broad "return transport for anything" fallback because provider attribution is supposed to be strict.

- [ ] **Step 7: Add provider test for ChatGPT route**

Append to `tests/test_provider.py`, using its existing `_write_config()` and `_patch_config_path()` helpers so both config path globals are patched and the test never reads the live proxy config:

```python
def test_chatgpt_transport_without_explicit_credential_returns_chatgpt(tmp_path):
    cfg = """\
model_list:
  - model_name: chatgpt/gpt-5.5
    litellm_params:
      model: chatgpt/gpt-5.5
"""
    p = _write_config(tmp_path, cfg)
    with _patch_config_path(p):
        assert resolve_provider("chatgpt/gpt-5.5") == "chatgpt"
```

Run:

```bash
.venv/bin/pytest -q \
  tests/test_run_model_routing.py \
  tests/test_scorers.py::TestPriceRatioScorer::test_bench_pricing_alias_overrides_state_model \
  tests/test_provider.py::test_chatgpt_transport_without_explicit_credential_returns_chatgpt
```

Expected: PASS.

---

### Task 5: Verify GPT-5.5 streaming preserves usage through Inspect

**Files:**
- Modify: tests only if adding a live opt-in test; otherwise no source changes.
- Test: one direct Inspect smoke and one bench smoke.

**Interfaces:**
- Consumes: LiteLLM proxy with `chatgpt/gpt-5.5` route.
- Produces: evidence that model output and usage survive streaming.

- [ ] **Step 1: Direct Inspect smoke**

Run:

```bash
OPENAI_BASE_URL=http://localhost:4000/v1 \
.venv/bin/python - <<'PY'
import asyncio
import os
from dotenv import load_dotenv
from inspect_ai.model import ChatMessageUser, GenerateConfig, get_model

load_dotenv()
os.environ["OPENAI_BASE_URL"] = "http://localhost:4000/v1"

async def main() -> None:
    model = get_model(
        "openai-api/openai/chatgpt/gpt-5.5",
        config=GenerateConfig(
            max_tokens=20,
            extra_body={"stream_options": {"include_usage": True}},
        ),
        memoize=False,
        stream=True,
    )
    result = await model.generate([ChatMessageUser(content="Say exactly: hi")])
    print("completion", result.completion)
    print("model", result.model)
    print("usage", result.usage)
    assert result.completion.strip().lower() == "hi"
    assert result.usage is not None
    assert result.usage.input_tokens > 0
    assert result.usage.output_tokens > 0

asyncio.run(main())
PY
```

Expected: PASS and printed usage with positive input/output tokens.

- [ ] **Step 2: Bench route smoke with disposable log dir**

Run:

```bash
RUN_ID="inspect-gpt55-$(date +%Y%m%d%H%M%S)"
LOG_DIR="logs/$RUN_ID"
mkdir -p "$LOG_DIR"
.venv/bin/python -m bench_cli run \
  --tier quick \
  --task smoke \
  --model chatgpt/gpt-5.5 \
  --as gpt-5.5-codex-smoke \
  --no-resume \
  --no-compare \
  --no-tui \
  --log-dir "$LOG_DIR"
```

Expected:

```text
Provider: chatgpt
...
smoke: success
```

Also inspect the log:

```bash
LOG_DIR="$LOG_DIR" .venv/bin/python - <<'PY'
import os
from inspect_ai.log import list_eval_logs, read_eval_log
infos = list_eval_logs(log_dir=os.environ["LOG_DIR"])
assert len(infos) == 1
log = read_eval_log(infos[0])
print(log.eval.model, log.status)
assert log.eval.model == "gpt-5.5-codex-smoke"
assert str(log.status) == "success"
for sample in log.samples or []:
    print(sample.model_usage)
    assert sample.model_usage
PY
```

Expected: recorded model is `gpt-5.5-codex-smoke`, status is `success`, and `sample.model_usage` is not empty.

---

### Task 6: Run focused compatibility and post-processing tests

**Files:**
- Modify: none unless tests reveal real incompatibilities.
- Test: existing suites.

**Interfaces:**
- Consumes: upgraded deps and routing changes.
- Produces: confidence that Inspect APIs, log readers, scorers, and model cards still work.

- [ ] **Step 1: Run high-signal unit tests**

Run:

```bash
.venv/bin/pytest -q \
  tests/test_dependency_contract.py \
  tests/test_inspect_compat.py \
  tests/test_run_model_routing.py \
  tests/test_cli.py \
  tests/test_run.py \
  tests/test_verify_sh_scorer.py \
  tests/test_scorers.py \
  tests/test_viability_tier.py \
  tests/test_integration.py
```

Expected: no new failures compared with the pre-upgrade baseline. Any failure importing Inspect, constructing `Task`, scorer shape changes, or `ModelOutput` usage is an upgrade blocker.

- [ ] **Step 2: Run log reader and result generator tests**

Run:

```bash
.venv/bin/pytest -q \
  tests/test_compare.py \
  tests/test_inspect.py \
  tests/test_inspect_recorded_name.py \
  tests/test_results.py \
  tests/test_results_slug.py \
  tests/test_ratio_recompute.py \
  tests/test_discriminative_subject.py
```

Expected: no schema/read/write regressions in `.eval` handling.

- [ ] **Step 3: Run task behavioral tests**

Run:

```bash
.venv/bin/pytest -q \
  tests/test_tier1_tasks.py \
  tests/test_tier2_tasks.py \
  tests/test_verify_patterns.py \
  tests/test_fixtures.py
```

Expected: PASS.

---

### Task 7: Run live disposable eval smoke matrix

**Files:**
- Modify: none.
- Test: live LiteLLM evals into a disposable log dir.

**Interfaces:**
- Consumes: LiteLLM proxy, `.env`, upgraded Inspect.
- Produces: fresh `.eval` logs proving end-to-end behavior.

- [ ] **Step 1: Create disposable log dir**

Run:

```bash
RUN_ID="inspect-upgrade-$(date +%Y%m%d%H%M%S)"
LOG_DIR="logs/$RUN_ID"
mkdir -p "$LOG_DIR"
echo "$LOG_DIR"
```

Expected: fresh path under `logs/`.

- [ ] **Step 2: Smoke minimal pipeline**

Run:

```bash
.venv/bin/python -m bench_cli run \
  --tier quick \
  --task smoke \
  --model openai/go-kimi-k2.7-code \
  --no-resume \
  --no-compare \
  --no-tui \
  --log-dir "$LOG_DIR"
```

Expected: one success log, no `Invalid model name`, no schema/scorer error.

- [ ] **Step 3: Prefix regression guard**

Run the same concrete non-moniker alias in bare and prefixed forms:

```bash
.venv/bin/python -m bench_cli run --tier quick --task smoke --model go-kimi-k2.7-code --no-resume --no-compare --no-tui --log-dir "$LOG_DIR"
.venv/bin/python -m bench_cli run --tier quick --task smoke --model openai/go-kimi-k2.7-code --no-resume --no-compare --no-tui --log-dir "$LOG_DIR"
```

Expected: both route successfully and neither sends `openai/go-kimi-k2.7-code` through to LiteLLM as an invalid proxy model name. Do not use `default`/`openai/default` here; those are router monikers and should hard-stop by design.

- [ ] **Step 4: Ratio scorer smoke**

Run:

```bash
.venv/bin/python -m bench_cli run \
  --tier full \
  --task q3-answer-the-question \
  --model openai/go-kimi-k2.7-code \
  --no-resume \
  --no-compare \
  --no-tui \
  --sequential \
  --max-retries 4 \
  --log-dir "$LOG_DIR"
```

Expected: `success` with scorer keys including `verify_sh`, `token_ratio_scorer`, `time_ratio_scorer`, `price_ratio_scorer`.

- [ ] **Step 5: Hybrid/judge smoke**

Run:

```bash
.venv/bin/python -m bench_cli run \
  --tier full \
  --task q4-root-cause \
  --model openai/go-kimi-k2.7-code \
  --no-resume \
  --no-compare \
  --no-tui \
  --sequential \
  --max-retries 4 \
  --log-dir "$LOG_DIR"
```

Expected: `success`; hybrid metadata includes `verify_sh_score` and `llm_judge_score`.

- [ ] **Step 6: GPT-5.5 Codex streaming smoke**

Run:

```bash
.venv/bin/python -m bench_cli run \
  --tier quick \
  --task smoke \
  --model chatgpt/gpt-5.5 \
  --as gpt-5.5-codex-smoke \
  --no-resume \
  --no-compare \
  --no-tui \
  --log-dir "$LOG_DIR"
```

Expected: `success`, `Provider: chatgpt`, usage present in the sample log.

- [ ] **Step 7: GPT-5.5 Codex cost-scored smoke**

Run a small real task that includes `price_ratio_scorer`; the `smoke` task alone is not enough because it does not exercise the cost pillar.

```bash
.venv/bin/python -m bench_cli run \
  --tier full \
  --task q3-answer-the-question \
  --model chatgpt/gpt-5.5 \
  --as gpt-5.5-codex-q3 \
  --no-resume \
  --no-compare \
  --no-tui \
  --sequential \
  --max-retries 4 \
  --log-dir "$LOG_DIR"
```

Expected: `success`, sample `model_usage` is present, and scorer keys include `price_ratio_scorer` with non-NaN `actual_cost_usd` metadata.

- [ ] **Step 8: Fresh log post-processing**

Run:

```bash
.venv/bin/python -m bench_cli compare --log-dir "$LOG_DIR"
.venv/bin/python -m bench_cli inspect stats --model gpt-5.5-codex-smoke --log-dir "$LOG_DIR"
.venv/bin/python -m bench_cli inspect deep-check --model gpt-5.5-codex-smoke --log-dir "$LOG_DIR"
.venv/bin/python -m bench_cli inspect stats --model gpt-5.5-codex-q3 --log-dir "$LOG_DIR"
```

Expected: compare/stats/deep-check render without `.eval` schema crashes. The `gpt-5.5-codex-q3` stats show a cost ratio or at least a populated `Cost/sample`; if cost is `--`, inspect `bench_pricing_alias` propagation before accepting the upgrade.

---

### Task 8: Full acceptance and cleanup

**Files:**
- Modify: only if previous tasks required fixes.
- Test: full suite and git review.

**Interfaces:**
- Consumes: completed code changes and live smoke evidence.
- Produces: an accept/reject decision for the upgrade.

- [ ] **Step 1: Run full suite**

Run:

```bash
.venv/bin/pytest -q
```

Expected: no new failures compared with Task 1 baseline. Preferred target is fully green after fixing config-drift tests; minimum acceptable target is exactly the same known allowlist with no Inspect/routing regressions.

- [ ] **Step 2: Review dependency tree**

Run:

```bash
.venv/bin/python -m pip check
.venv/bin/python -m pip show inspect-ai inspect-swe openai agent-client-protocol fastapi starlette anyio uvicorn
```

Expected: `pip check` reports no broken requirements.

- [ ] **Step 3: Review diff**

Run:

```bash
git diff -- pyproject.toml bench_cli/run/core.py bench_cli/run/cli.py bench_cli/provider.py bench_cli/solvers/multishot.py tests
```

Expected: diff is scoped to dependency floors, Inspect compatibility cleanup, model routing support, and tests.

- [ ] **Step 4: Done criteria**

The upgrade is done only if all are true:

```text
[ ] inspect_ai imports as 0.3.245
[ ] openai SDK is >=2.40.0
[ ] inspect-swe is >=0.2.65 if agent evals are in scope
[ ] normal LiteLLM aliases still route through openai/<alias>
[ ] chatgpt/gpt-5.5 routes through openai-api/openai/chatgpt/gpt-5.5 with stream=True
[ ] stream_options.include_usage=true produces sample.model_usage
[ ] compare/results/inspect can read fresh logs
[ ] no new pytest failures beyond explicitly documented pre-existing config drift
```

- [ ] **Step 5: Commit**

Run:

```bash
git add pyproject.toml bench_cli/run/core.py bench_cli/run/cli.py bench_cli/provider.py bench_cli/solvers/multishot.py scorers/price_ratio.py tests/test_dependency_contract.py tests/test_inspect_compat.py tests/test_run_model_routing.py tests/test_provider.py tests/test_scorers.py
git commit -m "chore: upgrade inspect ai to 0.3.245"
```

Expected: one scoped commit. If `bench_cli/run/cli.py` already contains the prior uncommitted prefix-handling fix, include it in this commit only if you explicitly want one combined dependency/routing commit; otherwise split commits first.
