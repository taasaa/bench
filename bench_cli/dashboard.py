"""Front door dashboard — shown when user types `bench` with no arguments."""

from __future__ import annotations

import math
from pathlib import Path

from bench_cli.compare.core import load_compare_data
from bench_cli.resolver import bare_name


def _project_root() -> Path:
    """Get project root (where tasks/ and logs/ live)."""
    return Path(__file__).resolve().parent.parent


def _bar(score: float, width: int = 10) -> str:
    filled = max(0, min(width, int(round(score * width))))
    return "●" * filled + "○" * (width - filled)


def _time_ago(iso_date: str) -> str:
    """Convert ISO date string to human-readable 'X ago'."""
    from datetime import datetime

    try:
        then = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return iso_date
    now = datetime.now(tz=then.tzinfo)
    delta = now - then
    if delta.days > 30:
        return f"{delta.days // 30}mo ago"
    if delta.days > 0:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    mins = delta.seconds // 60
    if mins > 0:
        return f"{mins}min ago"
    return "just now"


def _extract_recent_runs(log_dir: str, limit: int = 5) -> list[dict]:
    """Extract recent eval runs from log filenames."""
    import re

    fname_re = re.compile(r"(\d{4}-\d{2}-\d{2}T[\d-]+)_(.+)_([A-Za-z0-9]+)\.eval")
    logs_path = Path(log_dir)
    if not logs_path.is_dir():
        return []

    runs: list[dict] = []
    for f in sorted(logs_path.glob("*.eval"), reverse=True):
        m = fname_re.search(f.name)
        if not m:
            continue
        runs.append({
            "date": m.group(1)[:10],
            "task": m.group(2),
            "id": m.group(3),
        })
        if len(runs) >= limit * 5:  # over-collect, dedup below
            break

    # Dedup by date prefix — just keep distinct dates
    seen: set[str] = set()
    result: list[dict] = []
    for r in runs:
        key = r["date"][:10]
        if key not in seen:
            seen.add(key)
            result.append(r)
        if len(result) >= limit:
            break
    return result


def render_dashboard(log_dir: str = "logs") -> str:
    """Render the front door dashboard."""
    lines: list[str] = []

    # --- Count evals and tasks ---
    logs_path = Path(log_dir)
    n_evals = len(list(logs_path.glob("*.eval"))) if logs_path.is_dir() else 0

    root = _project_root()
    tasks_root = root / "tasks"
    n_tasks = 0
    if tasks_root.is_dir():
        for f in tasks_root.rglob("task.py"):
            if "fixtures" not in str(f) and "samples" not in str(f):
                n_tasks += 1

    # --- Header ---
    lines.append(f"bench — {n_evals} eval logs · {n_tasks} tasks")
    lines.append("")

    # --- RECENT ---
    recent = _extract_recent_runs(log_dir, limit=3)
    if recent:
        lines.append("RECENT")
        for r in recent:
            lines.append(f"  {r['date']}  {r['task']}")
        lines.append("")

    # --- SCORES ---
    try:
        data = load_compare_data(log_dir)
    except Exception:
        data = None

    if data and data.models:
        lines.append("SCORES")
        # Compute per-model mean correctness
        model_scores: list[tuple[str, float]] = []
        for model in data.models:
            vals = []
            for task in data.tasks:
                ps = data.matrix.get(task, {}).get(model)
                if ps and not math.isnan(ps.correctness):
                    vals.append(ps.correctness)
            if vals:
                model_scores.append((model, sum(vals) / len(vals)))

        model_scores.sort(key=lambda x: x[1], reverse=True)
        for i, (model, score) in enumerate(model_scores[:5], 1):
            lines.append(f"  #{i}  {bare_name(model):<20s} {score:.0%}  {_bar(score)}")

        lines.append("")

    # --- ACTIONS ---
    lines.append("ACTIONS")
    lines.append("  bench run <model>          run an eval")
    lines.append("  bench show <model>         deep-dive on a model")
    lines.append("  bench compare A B          head-to-head comparison")
    lines.append("  bench score                model ranking")
    lines.append("  bench help                 all commands & flags")

    return "\n".join(lines)
