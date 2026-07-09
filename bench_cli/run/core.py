"""Business logic for bench run -- task discovery, resolution, and price gating."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import click
from inspect_ai import Task

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Map tier names to the subdirectories under tasks/ that they include.
# "quick" runs verification/smoke tests only; "full" runs all eval tasks.
TIER_DIRS: dict[str, list[str]] = {
    "quick": ["verification"],
    "full": ["competence", "execution", "analysis", "universal"],
}

# Viability tier: a curated 4-task subset that demonstrates model viability
# across all 4 main pillars (competence / execution / analysis / universal)
# in a few minutes. Each task is verify_sh-based (deterministic, no judge
# variance), small-sample (4-7), no Docker, no agent. Use this to decide
# whether a model is worth a full 34-task run. Order is fixed: each task
# answers one pillar-level question (can you answer / reason / verify /
# handle real-world mess?).
VIABILITY_TASKS: tuple[str, ...] = (
    "q3-answer-the-question",      # competence:  can you actually answer the question?
    "q4-root-cause",               # execution:   can you reason about code, not just patch?
    "f1-multi-file-verify",        # analysis:    can you check claims against reality?
    "u17-dirty-workspace-triage",  # universal:   can you handle real-world mess?
)

DEFAULT_MODEL = "openai/default"

# Regex to extract the task token from an eval-log filename:
# 2026-04-16T23-13-32-00-00_task-name_ID.eval
# Kept independent from results/core.py:_FNAME_RE so the run path never
# couples to the results/card path.
_FNAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T[\d-]+)_(.+)_([A-Za-z0-9]+)\.eval")


# ---------------------------------------------------------------------------
# Cross-run resume (W1a)
# ---------------------------------------------------------------------------


def _completed_tasks(
    log_dir: str,
    bench_alias: str,
    spec_dirs: set[str],
    provider: str | None = None,
) -> set[str]:
    """Task dir-names (hyphenated) that already have a status='success'
    log for ``bench_alias``.

    Only logs whose filename task token is in ``spec_dirs`` are header-read,
    so this is cheap even with 1000s of logs on disk.

    Only status='success' counts -- errored/started/partial logs are always
    re-run so a killed run recovers past its failure point.

    Provider-aware dedup (2026-07-07): if a log has a `bench_provider` in
    its header metadata AND it differs from ``provider``, it is treated as
    a DIFFERENT run and NOT marked done — different providers must not
    replace one another under the same recorded identity. Logs without
    `bench_provider` (pre-feature runs) are matched by recorded identity
    alone and a one-time warning is emitted to the first spec_dirs hit.
    """
    from inspect_ai.log import list_eval_logs, read_eval_log

    log_path = Path(log_dir)
    if not log_path.is_dir():
        return set()
    done: set[str] = set()
    warned_legacy = False
    try:
        infos = list_eval_logs(log_dir=str(log_path))
    except Exception:
        return set()
    for info in infos:
        m = _FNAME_RE.search(info.name)
        if not m:
            continue
        task_token = m.group(2)
        if task_token not in spec_dirs:
            continue  # cheap skip: not a task we'd run
        try:
            el = read_eval_log(info, header_only=True)
        except Exception:
            continue
        if not (el.eval and el.eval.model == bench_alias and el.status == "success"):
            continue

        # Provider-aware dedup.
        if provider is not None:
            existing = (el.eval.metadata or {}).get("bench_provider")
            if existing is not None and existing != provider:
                # Different provider on the same recorded identity. Do NOT
                # skip — this is a distinct run that must be kept.
                continue
            if existing is None and not warned_legacy:
                import sys

                print(
                    f"Warning: found existing log for '{bench_alias}' without "
                    f"bench_provider metadata; assuming same provider "
                    f"('{provider}'). Use --no-resume or delete the log to "
                    f"force a re-run.",
                    file=sys.stderr,
                )
                warned_legacy = True
        done.add(task_token)
    return done


# ---------------------------------------------------------------------------
# Task discovery
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    """Check if Docker is running and available."""
    import subprocess

    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@lru_cache(maxsize=128)
def _requires_docker(task_py: Path) -> bool:
    """Heuristic: does task.py declare sandbox='docker'."""
    try:
        content = task_py.read_text()
    except OSError:
        return False
    return bool(re.search(r'sandbox\s*=\s*["\']docker["\']', content))


def _discover_viability_tasks(
    tasks_root: Path,
    max_tasks: int | None,
    task_filter: str | None,
) -> list[str]:
    """Return Inspect task specs for the viability tier.

    Resolves each name in ``VIABILITY_TASKS`` by searching all pillar subdirs
    under ``tasks_root`` (not a fixed-pillar lookup), so a future ``tasks/``
    reorganization that moves a viability task to a different pillar won't
    break this tier. Raises ``click.ClickException`` if a hardcoded task
    name is missing — that means ``VIABILITY_TASKS`` is stale.

    Args:
        tasks_root: Path to the ``tasks/`` directory.
        max_tasks: If set, cap the returned list to this many entries.
        task_filter: If set, only include the task whose directory name matches.

    Returns:
        List of relative task spec paths, e.g.
        ``["tasks/competence/q3-answer-the-question/task.py", ...]``
    """
    specs: list[str] = []
    for name in VIABILITY_TASKS:
        if task_filter is not None and name != task_filter:
            continue
        found: Path | None = None
        for sub in sorted(p for p in tasks_root.iterdir() if p.is_dir()):
            candidate = sub / name / "task.py"
            if candidate.is_file():
                found = candidate
                break
        if found is None:
            raise click.ClickException(
                f"Viability task '{name}' not found under {tasks_root}/. "
                "Update VIABILITY_TASKS in bench_cli/run/core.py."
            )
        # Return a path relative to CWD (tasks_root.parent) so the spec
        # matches the format Inspect expects: "tasks/<sub>/<name>/task.py".
        # Works whether tasks_root is a relative Path("tasks") (production)
        # or an absolute tmp_path/tasks (tests via monkeypatch.chdir).
        specs.append(str(found.relative_to(tasks_root.parent)))

    if max_tasks is not None and max_tasks >= 0:
        specs = specs[:max_tasks]
    return specs


def _discover_tasks(
    tier: str,
    max_tasks: int | None = None,
    task_filter: str | None = None,
) -> list[str]:
    """Return Inspect-compatible task spec strings for the given tier.

    Scans the configured subdirectories under ``tasks/`` for ``task.py``
    files and returns them as relative paths that Inspect's ``eval()``
    can resolve (e.g. ``tasks/verification/smoke/task.py``).

    Tasks that require Docker (``sandbox="docker"``) are automatically
    skipped with a warning when Docker is not available.

    Parameters
    ----------
    tier:
        ``"quick"`` runs verification/smoke only; ``"full"`` runs all 34
        eval tasks across the 4 main pillars; ``"viability"`` runs a
        curated 4-task diagnostic subset (one per pillar).
    max_tasks:
        If set, cap the returned list to this many entries.
    task_filter:
        If set, select only the task whose directory name matches.
        Matches exactly (e.g. ``"smoke"`` matches only ``"smoke"`` and
        not ``"agent_smoke"``).  Use ``--list-tasks`` first to see all names.
    """
    tasks_root = Path("tasks")
    if tier == "viability":
        return _discover_viability_tasks(tasks_root, max_tasks, task_filter)
    dirs = TIER_DIRS.get(tier)
    if dirs is None:
        raise click.BadParameter(f"Unknown tier {tier!r}", param_hint="--tier")

    docker_ok = _docker_available()

    specs: list[str] = []
    for subdir in sorted(dirs):
        # Each subdir contains task directories (e.g. tasks/verification/smoke/).
        task_parent = tasks_root / subdir
        if not task_parent.is_dir():
            continue
        for task_dir in sorted(task_parent.iterdir()):
            if task_filter and task_dir.name != task_filter:
                continue
            task_py = task_dir / "task.py"
            if not task_py.is_file():
                continue
            if _requires_docker(task_py) and not docker_ok:
                click.echo(
                    f"  Skipping {task_py} (requires Docker, not available)",
                    err=True,
                )
                continue
            specs.append(str(task_py))

    if max_tasks is not None and max_tasks >= 0:
        specs = specs[:max_tasks]

    return specs


def parse_model_arg(model: str) -> tuple[str, str | None]:
    """Split --model value into (alias, openrouter_override).

    Supports optional [override] suffix:
        openai/nvidia-devstral[mistralai/devstral-2-123b-instruct-2512]
      -> ("openai/nvidia-devstral", "mistralai/devstral-2-123b-instruct-2512")

    Without [override]:
        openai/nvidia-nemotron-30b
      -> ("openai/nvidia-nemotron-30b", None)
    """
    if "[" in model:
        alias, rest = model.split("[", 1)
        if "]" not in rest:
            raise click.BadParameter(
                f"Invalid --model format: missing closing ']' in {model!r}",
                param_hint="--model",
            )
        or_override = rest.rstrip("]")
        return alias, or_override
    return model, None


# ---------------------------------------------------------------------------
# Model routing (0.3.245 upgrade)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelRoute:
    """Resolved model routing contract for one bench run.

    Centralizes the (alias -> multi-headed routing) decision so the CLI
    doesn't have to manually thread routed_name / recorded_name /
    pricing_alias / provider_alias / model_args / config_overrides
    through five separate variables and four separate sites.

    Field semantics:
      * bench_alias       : the exact --model string the user typed
                            (may carry the [override] suffix BEFORE
                            parse_model_arg strips it; here it is the
                            bare alias, used for echo-back).
      * routed_name       : the inspect_ai.eval(model=...) value. Inspect
                            strips the openai/ prefix before sending the
                            remainder to the proxy.
      * recorded_name     : the eval.eval.model written into the .eval
                            log file (--as>resolved>fallback chain).
      * pricing_alias     : the LiteLLM-side alias used by _check_price_gate
                            and the override-save block. For chatgpt/*
                            routing this is the BARE alias (chatgpt/gpt-5.5),
                            not the openai-api provider string, so
                            overrides and pricing lookups stay on the
                            canonical side.
      * provider_alias    : the alias passed to resolve_provider() to
                            attribute the run to a vendor/brand.
      * model_args        : extra kwargs threaded into inspect_ai.eval(...).
      * config_overrides  : GenerateConfig overlay (e.g. extra_body for
                            chatgpt/* streaming usage tracking).
    """

    bench_alias: str
    routed_name: str
    recorded_name: str
    pricing_alias: str
    provider_alias: str
    model_args: dict[str, Any] = field(default_factory=dict)
    config_overrides: dict[str, Any] = field(default_factory=dict)


def _strip_openai_prefix(alias: str) -> str:
    """Strip a leading `openai/` from a routed alias, if present.

    Centralized here so the routing logic doesn't accidentally disagree
    with `bench_cli/provider._strip_openai_prefix`. Kept as a private
    duplicate rather than imported across modules to avoid a bench_cli
    internal cycle (provider.py already imports from litellm_config).
    """
    return alias[len("openai/"):] if alias.startswith("openai/") else alias


def build_model_route(bench_alias: str, as_name: str | None) -> ModelRoute:
    """Resolve user model input into Inspect routing + bench attribution.

    Normal aliases use Inspect's native OpenAI provider (`openai/<alias>`).
    ChatGPT/Codex LiteLLM aliases must use Inspect's OpenAI-compatible
    provider with streaming because LiteLLM's `chatgpt/*` route fails for
    non-streaming calls.

    Args:
      bench_alias: the --model value AFTER parse_model_arg() has stripped
                   the optional [override] suffix (override handling lives
                   in cli.py, not in routing).
      as_name:     the --as override (or None).

    Returns:
      ModelRoute dataclass with all routing fields populated.
    """
    bare_alias = _strip_openai_prefix(bench_alias)

    # ChatGPT/Codex LiteLLM routes: must go through openai-api with
    # streaming + stream_options.include_usage=True, or Inspect forces
    # Responses API which LiteLLM rejects with 500. Proven-working
    # incantation is openai-api/openai/<bare> + stream=True + extra_body
    # stream_options. The bare alias (chatgpt/gpt-5.5) is what the
    # proxy's model_name and the LiteLLM config talk, so price gate
    # and override save must use it too.
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

    # Normal path: bare alias OR prefixed alias. If the user gave a bare
    # alias (`go-kimi-k2.7-code`) Inspect needs the `openai/` prefix to
    # pick the OpenAI provider. Prefixed (`openai/go-kimi-k2.7-code`) is
    # passed through unchanged.
    if "/" not in bench_alias:
        routed_name = f"openai/{bench_alias}"
        pricing_alias = bench_alias
        provider_alias = bench_alias
    else:
        routed_name = bench_alias
        pricing_alias = bench_alias
        provider_alias = bench_alias

    recorded_name = resolve_recorded_name(pricing_alias, as_name)
    return ModelRoute(
        bench_alias=bench_alias,
        routed_name=routed_name,
        recorded_name=recorded_name,
        pricing_alias=pricing_alias,
        provider_alias=provider_alias,
        # 0.3.245 upgrade: TWO regression paths force responses_api=True and
        # route to /v1/responses, which most non-gpt bench backends (opencode,
        # kilocode, nvidia_nim, openrouter, anthropic, ...) reject with a 404.
        #   (1) is_latest_model() returns True for any model name that doesn't
        #       contain gpt/codex/o-series/deep-research → responses_preferred.
        #   (2) is_gpt_5_pro() = is_gpt_5() (via is_latest) AND "-pro" in name →
        #       auto-sets background=True, which OR's into responses_api and is
        #       NOT defeated by responses_api=False. Hits any "-pro" alias
        #       (go-mimo-pro, mimo-v2.5-pro, deepseek-v4-pro, ...).
        # Pin BOTH responses_api=False AND background=False so the OpenAI
        # provider uses Chat Completions regardless of the model name.
        model_args={"responses_api": False, "background": False},
    )


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


# ---------------------------------------------------------------------------
# Pre-flight price gate
# ---------------------------------------------------------------------------


def _check_price_gate(model_alias: str) -> None:
    """Block eval if model has no known price -- before any API calls.

    Managed/local models (qwen-local, gemma-*-local, etc.) are exempt always.
    """
    from bench_cli.pricing import OpenRouterCache
    from bench_cli.pricing.litellm_config import is_managed_model, resolve_openrouter_id

    if is_managed_model(model_alias):
        return  # exempt

    or_id = resolve_openrouter_id(model_alias)
    if or_id is None:
        return  # unknown alias, let it fail downstream

    cache = OpenRouterCache()

    # Try to refresh cache -- this pulls fresh prices from OpenRouter.
    # If OPENROUTER_API_KEY is not set, this raises RuntimeError and we
    # fall back to the existing cache. If cache is stale and refresh fails,
    # we also fall back (stale cache still has useful data if the model was
    # cached before).
    try:
        cache.fetch_and_cache_prices()
    except RuntimeError:
        pass  # no key or refresh failed -- rely on existing cache

    # Check cache for this specific model's price.
    all_prices = cache.get_all_prices()
    if or_id not in all_prices:
        from bench_cli.pricing.price_suggestions import suggest_alternatives

        alternatives = suggest_alternatives(or_id)

        click.echo(f"ERROR: No price found for {model_alias}", err=True)
        click.echo(f"  Resolved OpenRouter ID: {or_id}", err=True)
        click.echo("  This model was not found in the OpenRouter price cache.", err=True)
        click.echo(
            "  The OpenRouter catalog does not have this model. "
            "It may be a private or NIM endpoint.",
            err=True,
        )

        if alternatives:
            provider = alternatives[0].split("/")[0] if alternatives else ""
            click.echo(f"\n  Other {provider} models that ARE available:", err=True)
            for alt_id in alternatives:
                alt_price = all_prices.get(alt_id)
                if alt_price:
                    in_ppm = alt_price.input_price * 1e6
                    out_ppm = alt_price.output_price * 1e6
                    click.echo(
                        f"    {alt_id}  (${in_ppm:.4f} / ${out_ppm:.4f} per 1M tokens)",
                        err=True,
                    )
            click.echo(
                f"\n  To use one of these alternatives instead:\n"
                f"    bench run --model {model_alias}[{alternatives[0]}] --tier quick",
                err=True,
            )
            click.echo(
                f"\n  To provide a manual price for {model_alias}:\n"
                f"    bench prices add {model_alias} <input_per_million> <output_per_million>",
                err=True,
            )
        else:
            click.echo(
                f"\n  To provide a manual price for {model_alias}:\n"
                f"    bench prices add {model_alias} <input_per_million> <output_per_million>",
                err=True,
            )

        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Task and agent resolution
# ---------------------------------------------------------------------------


def _resolve_task(
    spec: str,
    agent: str | None = None,
    agent_mode: str | None = None,
    cc_model: str | None = None,
    provider: str | None = None,
    config_overrides_extra: dict | None = None,
    pricing_alias: str | None = None,
) -> Task:
    """Load a task spec (path or name) and inject bench_task_dir into its metadata.

    The verify_sh scorer runs inside Inspect AI's async event loop where stack
    introspection cannot locate task.py -- no such frame exists in the async call
    stack. By injecting bench_task_dir into the Task's metadata dict we bypass the
    need for any runtime detection.
    """
    import importlib.util
    import os
    import sys

    spec_path = os.path.abspath(spec)
    task_dir = os.path.dirname(spec_path)

    # Load the module so we can extract the Task object.
    spec_obj = importlib.util.spec_from_file_location(spec_path, spec_path)
    if spec_obj is None or spec_obj.loader is None:
        raise click.ClickException(f"Cannot load task spec: {spec}")
    module = importlib.util.module_from_spec(spec_obj)
    sys.modules[spec_path] = module  # prevent duplicate-load warnings
    spec_obj.loader.exec_module(module)

    # task.py typically defines one @task-decorated function.
    # Use registry_info to identify it (more reliable than introspection).
    task_factory = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if not callable(attr) or attr_name.startswith("_"):
            continue
        try:
            from inspect_ai._util.registry import registry_info

            info = registry_info(attr)
            if info.type == "task":
                task_factory = attr
                break
        except ValueError:
            continue

    if task_factory is None:
        raise click.ClickException(f"No @task-decorated function found in {spec}")

    # Call the factory with CWD set to the task directory so relative dataset
    # paths (e.g. "dataset.json") resolve correctly.
    orig_cwd = os.getcwd()
    try:
        os.chdir(task_dir)
        task_obj = task_factory()
    finally:
        os.chdir(orig_cwd)

    # Inject bench_task_dir into each sample's metadata (not Task metadata).
    # Inspect propagates sample.metadata -> state.metadata during scoring,
    # but Task.metadata does NOT reach state.metadata.
    for sample in task_obj.dataset:
        if sample.metadata is None:
            sample.metadata = {}
        sample.metadata["bench_task_dir"] = task_dir

        # bench_provider (2026-07-07): the brand the user pays, derived
        # strictly from ~/dev/litellm/config.yaml. Mirrors bench_agent
        # pattern. Eval-level metadata also gets it (via inspect_eval
        # metadata= kwarg) so dedup can read it in header_only mode.
        if provider is not None:
            sample.metadata["bench_provider"] = provider

        if agent is not None:
            sample.metadata["bench_agent"] = agent
            sample.metadata["bench_agent_mode"] = agent_mode
            sample.metadata["bench_cc_model"] = cc_model

        # Pricing-alias injection (0.3.245 upgrade): scorers/price_ratio.py
        # reads state.metadata["bench_pricing_alias"] first so streaming
        # openai-api routes (chatgpt/gpt-5.5) get priced under the normalized
        # LiteLLM alias, not the routed Inspect provider name.
        if pricing_alias is not None:
            sample.metadata["bench_pricing_alias"] = pricing_alias

        # Inject fixture path from dataset.json "fixture" field.
        # The fixture field specifies a scenario_id under fixtures/.
        fixture_id = sample.metadata.get("fixture") if isinstance(sample.metadata, dict) else None
        if fixture_id:
            from bench_cli.fixtures import fixture_dir_for

            fdir = fixture_dir_for(task_dir, str(fixture_id))
            if fdir:
                sample.metadata["fixture_path"] = str(fdir)
                # Copy fixture files into sample.files so Inspect AI's sandbox
                # init writes them into the Docker container.  This makes fixture
                # files available to agent solvers (which bypass the multishot
                # solver and its read_file/list_directory tools).
                if sample.files is None:
                    sample.files = {}
                sample.files["workspace"] = str(fdir)
        else:
            # No fixture — ensure workspace dir exists so cwd="workspace"
            # in the docker agent solver doesn't fail.  Use a data: URI so
            # Inspect treats it as literal content, not a filesystem path.
            if sample.files is None:
                sample.files = {}
            if "workspace" not in sample.files:
                sample.files["workspace/.gitkeep"] = "data:text/plain,"

    # Merge generous timeout into task config.  Local models behind LiteLLM
    # can be slow -- a single generate() on a complex prompt may take 2-3
    # minutes.  Default OpenAI SDK timeout is 600s which is fine, but some
    # proxy configs or model servers impose shorter limits.  Setting
    # attempt_timeout=300 gives the model 5 minutes per attempt before retry.
    from inspect_ai.model import GenerateConfig

    orig_config = task_obj.config
    config_overrides: dict = {}
    if orig_config is None or getattr(orig_config, "timeout", None) is None:
        config_overrides["timeout"] = 600
    if orig_config is None or getattr(orig_config, "attempt_timeout", None) is None:
        config_overrides["attempt_timeout"] = 300
    # Merge extra overrides (e.g. stream_options.include_usage for chatgpt/*
    # streaming routes) on top of the bench defaults. Caller-provided
    # extras must NOT clobber defaults that the bench infra relies on, but
    # they should layer cleanly when both timeout AND stream-options are
    # forced by the same caller.
    if config_overrides_extra:
        config_overrides.update(config_overrides_extra)
    config = GenerateConfig(**config_overrides)

    return Task(
        dataset=task_obj.dataset,
        setup=task_obj.setup,
        solver=task_obj.solver,
        cleanup=task_obj.cleanup,
        scorer=task_obj.scorer,
        metrics=task_obj.metrics,
        model=task_obj.model,
        config=config,
        model_roles=task_obj.model_roles,
        sandbox=task_obj.sandbox,
        # Additive Inspect 0.3.245 Task fields. Preserved via getattr so
        # older task.py sources that don't set them don't blow up during
        # reconstruction. Defaults are sentinel-None to match the upstream
        # Task constructor's documented contract.
        checkpoint=getattr(task_obj, "checkpoint", None),
        on_checkpoint=getattr(task_obj, "on_checkpoint", None),
        on_resume=getattr(task_obj, "on_resume", None),
        approval=task_obj.approval,
        epochs=task_obj.epochs,
        fail_on_error=task_obj.fail_on_error,
        continue_on_fail=task_obj.continue_on_fail,
        # 0.3.245: score_on_error and turn_limit are new fields too.
        score_on_error=getattr(task_obj, "score_on_error", None),
        message_limit=task_obj.message_limit,
        token_limit=task_obj.token_limit,
        turn_limit=getattr(task_obj, "turn_limit", None),
        time_limit=task_obj.time_limit,
        working_limit=task_obj.working_limit,
        cost_limit=task_obj.cost_limit,
        early_stopping=task_obj.early_stopping,
        display_name=task_obj.display_name,
        name=task_obj.name or task_obj.display_name,
        version=task_obj.version,
        metadata=dict(task_obj.metadata or {}),
        tags=task_obj.tags,
        # 0.3.245: new viewer field. Preserve with getattr so older task
        # sources without it still reconstruct cleanly.
        viewer=getattr(task_obj, "viewer", None),
    )


def _resolve_agent_solver(agent: str, agent_mode: str, cc_model: str | None = None) -> object:
    """Route (agent, mode) to the correct Inspect solver.

    Modes:
      local / bare -> local_agent solver (subprocess on host)
      docker / harness -> docker_agent solver (inspect-swe in Docker)
    """
    if agent_mode in ("local", "bare"):
        from bench_cli.solvers.local_agent import local_agent

        return local_agent(agent, bare=(agent_mode == "bare"), model=cc_model)

    # docker / harness
    from bench_cli.solvers.docker_agent import docker_agent

    return docker_agent(agent, harness=(agent_mode == "harness"))
