"""bench tasks — human-readable task browser grouped by pillar."""

from __future__ import annotations

import importlib.util
from collections import defaultdict
from pathlib import Path

import click


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _extract_docstring(task_py: Path) -> str:
    """Extract first-line docstring from a task.py file."""
    try:
        spec = importlib.util.spec_from_file_location("task", task_py)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            doc = getattr(mod, "__doc__", "")
            if doc:
                return doc.strip().split("\n")[0]
    except Exception:
        pass
    return ""


def _load_task_map() -> dict[str, list[tuple[str, str]]]:
    """Scan tasks/ and return {pillar: [(task_name, docstring), ...]}."""
    tasks_root = _project_root() / "tasks"
    if not tasks_root.is_dir():
        return {}

    pillar_tasks: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for pillar_dir in sorted(tasks_root.iterdir()):
        if not pillar_dir.is_dir():
            continue
        pillar = pillar_dir.name
        for task_dir in sorted(pillar_dir.iterdir()):
            if not task_dir.is_dir():
                continue
            task_py = task_dir / "task.py"
            if not task_py.is_file():
                continue
            if "fixtures" in task_dir.name or "samples" in task_dir.name:
                continue
            doc = _extract_docstring(task_py)
            pillar_tasks[pillar].append((task_dir.name, doc))

    return dict(pillar_tasks)


def _load_task_scores(log_dir: str) -> dict[str, float]:
    """Load avg correctness per task from compare data."""
    try:
        from bench_cli.compare.core import load_compare_data

        data = load_compare_data(log_dir)
    except Exception:
        return {}

    scores: dict[str, float] = {}
    for task in data.tasks:
        vals = []
        for model in data.models:
            ps = data.matrix.get(task, {}).get(model)
            if ps and not __import__("math").isnan(ps.correctness):
                vals.append(ps.correctness)
        if vals:
            scores[task.replace("-", "_")] = sum(vals) / len(vals)
    return scores


PILLAR_ORDER = ["competence", "execution", "analysis", "universal", "verification"]
PILLAR_LABELS = {
    "competence": "COMPETENCE",
    "execution": "EXECUTION",
    "analysis": "ANALYSIS",
    "universal": "UNIVERSAL",
    "verification": "VERIFICATION",
}


@click.command("tasks")
@click.argument("pillar", required=False)
@click.option("--scores", "show_scores", is_flag=True, help="Show avg correctness per task.")
@click.option("--log-dir", default="logs", hidden=True)
def tasks_cmd(pillar: str | None, show_scores: bool, log_dir: str) -> None:
    """Browse available tasks grouped by pillar."""
    task_map = _load_task_map()
    if not task_map:
        click.echo("No tasks found.")
        return

    score_map = _load_task_scores(log_dir) if show_scores else {}

    # Filter to single pillar if requested
    if pillar:
        matched = None
        for p in PILLAR_ORDER:
            if p.startswith(pillar.lower()):
                matched = p
                break
        if matched is None:
            click.echo(f"Unknown pillar '{pillar}'. Choose: {', '.join(PILLAR_ORDER)}")
            return
        task_map = {matched: task_map.get(matched, [])}

    lines: list[str] = []
    for p in PILLAR_ORDER:
        tasks = task_map.get(p)
        if tasks is None:
            continue
        label = PILLAR_LABELS.get(p, p.upper())
        lines.append(f"{label} ({len(tasks)} tasks)")
        for name, doc in tasks:
            score_str = ""
            if show_scores:
                sc = score_map.get(name.replace("-", "_"))
                if sc is not None:
                    score_str = f"  {sc:.0%}"
            lines.append(f"  {name:<28s} {doc}{score_str}")
        lines.append("")

    click.echo("\n".join(lines).rstrip())
