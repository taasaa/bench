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

from pathlib import Path

from bench_cli.discriminative.types import SubjectID, SubjectType


def resolve_subject_from_log(log_path: Path) -> SubjectID:
    """Extract SubjectID from an eval log file.

    Detection strategy:
    - eval.sandbox.type == 'docker' → AGENT (inspect-swe solver running)
    - eval.sandbox.type is None → MODEL (bare model via CLI generate() solver)
    - sample.model_usage keys → model name (strip openai/ prefix for display)
    """
    from inspect_ai.log import read_eval_log

    el = read_eval_log(str(log_path))

    # Model: first key in model_usage
    model = None
    if el.samples and el.samples[0].model_usage:
        # Use the first non-judge model
        for key in el.samples[0].model_usage:
            if "judge" not in key.lower():
                model = key
                break
        if model is None:
            model = next(iter(el.samples[0].model_usage))
    if model is None:
        model = el.eval.model or "unknown"

    # Subject type from sandbox
    sandbox_type = getattr(el.eval.sandbox, "type", None)
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
    """Strip provider prefix to get the bare alias (e.g. openai/qwen-local → qwen-local)."""
    if "/" in model:
        return model.split("/", 1)[1]
    return model


def get_all_log_paths(
    log_dir: Path,
    subject: SubjectID | None = None,
) -> list[Path]:
    """Return all .eval file paths for the given subject, or all if subject is None.

    Keeps the latest log per (task, model) for the given subject.
    When subject is None, keeps latest per (task, model) across all subjects.
    """
    from inspect_ai.log import list_eval_logs

    infos = list_eval_logs(log_dir=str(log_dir), descending=True)
    paths: list[Path] = []
    # Track (task, normalized_model) seen — per subject to avoid blocking older subject logs
    seen: dict[tuple[str, str], Path] = {}

    for info in infos:
        path = Path(info.name.replace("file://", ""))
        try:
            from inspect_ai.log import read_eval_log

            el = read_eval_log(str(path))
            task = el.eval.task
            model = el.eval.model or ""

            # Filter by subject FIRST
            if subject is not None:
                sid = resolve_subject_from_log(path)
                # Normalize both to bare alias for comparison
                log_model = _normalize_model(sid.model)
                sub_model = _normalize_model(subject.model)
                if log_model != sub_model:
                    continue
                if subject.agent is not None and sid.agent != subject.agent:
                    continue

            # Deduplicate by (task, normalized_model) — keep latest per subject+task
            norm_model = _normalize_model(model)
            dedup_key = (task, norm_model)
            if dedup_key not in seen:
                seen[dedup_key] = path
        except Exception:
            continue

    # Return paths in order they were added (newest-first per task)
    return list(seen.values())


def get_subject_display_name(subject: SubjectID) -> str:
    """Return human-readable name for a subject."""
    return subject.display_name
