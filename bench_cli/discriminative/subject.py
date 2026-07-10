"""Subject resolution — detect subject type and ID from eval logs.

Key insight from log inspection (2026-04-22):
- ALL eval logs use "Claude Code" solver (Inspect agent wrapper)
- eval.sandbox.type == 'docker' → inspect-swe agent solver (AGENT)
- eval.sandbox.type is None → bare model eval (MODEL)
- sample.metadata['bench_task_dir'] → task directory path
- sample.model_usage → {model_alias: ModelUsage} dict
- sample.working_time → float seconds
- sample.events → EvalEvents (replaces deprecated transcript)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from bench_cli.resolver import bare_model_name
from bench_cli.discriminative.types import SubjectID


def resolve_subject_from_log(log_path: Path) -> SubjectID:
    """Extract SubjectID from an eval log file.

    Detection strategy:
    - eval.sandbox.type == 'docker' → AGENT (inspect-swe solver running)
    - eval.sandbox.type is None → MODEL (bare model via CLI generate() solver)
    - el.eval.model → recorded model name; sample.model_usage keys → legacy fallback

    Performance (2026-07-09 fix): uses header_only=True so we don't parse
    samples/events just to read eval.model + eval.sandbox.type. Legacy logs
    without eval.model still get the model_usage fallback via a one-shot
    full read (rare path).
    """
    from inspect_ai.log import read_eval_log

    try:
        el = read_eval_log(str(log_path), header_only=True)
    except Exception:
        return SubjectID(model="unknown")

    # Model identity: PRIMARY source is el.eval.model (the recorded name after
    # the --as/rewrite path). model_usage keys are ROUTED names (monikers) and
    # would re-introduce the moniker-as-subject problem; use them only as a
    # fallback for legacy logs whose eval.model was never rewritten.
    model = el.eval.model if (el.eval and el.eval.model) else None
    if model is None:
        # Legacy fallback needs samples — only paid when actually needed.
        try:
            el_full = read_eval_log(str(log_path))
            if el_full.samples and el_full.samples[0].model_usage:
                for key in el_full.samples[0].model_usage:
                    if "judge" not in key.lower():
                        model = key
                        break
                if model is None:
                    model = next(iter(el_full.samples[0].model_usage))
        except Exception:
            pass
    if model is None:
        model = "unknown"

    # Subject type from sandbox
    sandbox_type = getattr(el.eval.sandbox, "type", None) if el.eval else None
    if sandbox_type == "docker":
        # It's an agent eval (inspect-swe solver in Docker)
        # Try to extract agent name from solver_args
        agent = _extract_agent_name(el.eval.solver_args)
        agent_mode = _infer_agent_mode(el.eval.sandbox, el.eval.solver_args)
        return SubjectID(model=model, agent=agent, agent_mode=agent_mode)
    else:
        return SubjectID(model=model)


def _extract_agent_name(solver_args: dict | None) -> str:
    """Extract agent name from solver_args dict."""
    if not solver_args:
        return "unknown"
    # solver_args.name is often the agent name (e.g., "Claude Code")
    name = solver_args.get("name", "")
    if name:
        # Normalize to short agent name
        name_lower = name.lower()
        if "claude" in name_lower or "anthropic" in name_lower:
            return "claude"
        if "codex" in name_lower or "openai" in name_lower:
            return "codex"
        if "gemini" in name_lower or "google" in name_lower:
            return "gemini"
    # Fall back to solver name
    return "agent"


def _infer_agent_mode(sandbox, solver_args: dict | None) -> str:
    """Infer agent mode from sandbox config and solver_args."""
    if sandbox and getattr(sandbox, "type", None) == "docker":
        return "docker"
    # Could try to infer bare vs local from other signals
    return "local"


def _normalize_model(model: str) -> str:
    """Strip provider prefix (e.g. minimaxai/minimax-m3 -> minimax-m3)."""
    return bare_model_name(model)


def _candidate_normalized_models(model: str) -> set[str]:
    """Return normalized model names that should match logs for a query.

    Logs store the recorded identity (`eval.model`), while users commonly query
    by routing alias (e.g. `openai/go-mimo-pro`). For aliases whose recorded
    identity has a different bare tail (`xiaomi/mimo-v2.5-pro`), matching only
    the routing alias silently drops every log.
    """
    candidates = {_normalize_model(model)}
    try:
        from bench_cli.run.core import resolve_recorded_name

        candidates.add(_normalize_model(resolve_recorded_name(model, None)))
    except Exception:
        # Discriminative reads should still work if the live proxy config is
        # unavailable or malformed; in that case fall back to direct matching.
        pass
    return candidates


@lru_cache(maxsize=8)
def _scan_log_dir(log_dir_str: str) -> tuple[tuple[str, str, str], ...]:
    """Scan log_dir once via header_only, return {(task, norm_model): latest_path_str}.

    Performance (2026-07-09 fix):
      - header_only=True is ~9.5x faster than full read (just header.json,
        no samples/events). 1440 logs -> ~5s scan vs ~45s full-read.
      - lru_cache means N subjects in one CLI invocation cost ONE scan, not N.

    Returns an immutable tuple of (task, norm_model, path_str) so it's
    lru_cache-friendly. Caller converts path_str back to Path as needed.
    """
    from inspect_ai.log import list_eval_logs, read_eval_log

    log_dir = Path(log_dir_str)
    latest: dict[tuple[str, str], str] = {}
    for info in list_eval_logs(log_dir=str(log_dir), descending=True):
        path_str = info.name.replace("file://", "")
        try:
            el = read_eval_log(path_str, header_only=True)
            if not el.eval:
                continue
            task_obj = el.eval.task
            task = task_obj if isinstance(task_obj, str) else getattr(task_obj, "name", str(task_obj))
            model = el.eval.model or ""
            if not task:
                continue
            key = (task, _normalize_model(model))
            if key not in latest:
                latest[key] = path_str
        except Exception:
            continue
    return tuple((t, m, p) for (t, m), p in latest.items())


def get_all_log_paths(
    log_dir: Path,
    subject: SubjectID | None = None,
) -> list[Path]:
    """Return all .eval file paths for the given subject, or all if subject is None.

    Keeps the latest log per (task, model) for the given subject.
    When subject is None, keeps latest per (task, model) across all subjects.

    Performance (2026-07-09 fix): single header-only scan per log_dir per
    process (lru_cache on _scan_log_dir). N subjects share one scan instead
    of N x 1440 full reads.
    """
    mapping = _scan_log_dir(str(log_dir))

    if subject is None:
        return [Path(p) for (_t, _m, p) in mapping]

    sub_models = _candidate_normalized_models(subject.model)
    matches = [(_t, Path(p)) for (_t, m, p) in mapping if m in sub_models]
    if subject.agent is not None:
        # agent filtering needs per-file resolve_subject_from_log (rare path
        # — most CLI calls are model-only subjects). Only ~40 paths here, fast.
        filtered: list[Path] = []
        seen_tasks: set[str] = set()
        for task, p in matches:
            if task in seen_tasks:
                continue
            try:
                sid = resolve_subject_from_log(p)
                if sid.agent == subject.agent:
                    filtered.append(p)
                    seen_tasks.add(task)
            except Exception:
                continue
        return filtered

    paths: list[Path] = []
    seen_tasks: set[str] = set()
    for task, p in matches:
        if task in seen_tasks:
            continue
        paths.append(p)
        seen_tasks.add(task)
    return paths


def get_subject_display_name(subject: SubjectID) -> str:
    """Return human-readable name for a subject."""
    return subject.display_name
