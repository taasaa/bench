"""bench compare — read EvalLogs and display per-task score breakdown."""

from __future__ import annotations

import json as json_mod
from dataclasses import dataclass, field
from pathlib import Path

import click


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ScoreRow:
    """One row in the comparison table."""

    task: str
    model: str
    scorer: str
    score: float | None
    samples: int | None
    status: str
    created: str


# ---------------------------------------------------------------------------
# Log reading
# ---------------------------------------------------------------------------

def _load_rows(
    log_dir: str,
    latest: int | None = None,
) -> list[ScoreRow]:
    """Read eval logs from *log_dir* and return ScoreRow instances.

    Parameters
    ----------
    log_dir:
        Path to directory containing ``.eval`` / ``.json`` log files.
    latest:
        If set, limit to the most recent *N* logs (by mtime descending).

    Returns
    -------
    List of :class:`ScoreRow` sorted by (task, model, created).
    """
    from inspect_ai.log import list_eval_logs, read_eval_log

    log_dir_path = Path(log_dir)
    if not log_dir_path.is_dir():
        return []

    infos = list_eval_logs(log_dir=str(log_dir_path), descending=True)

    if latest is not None and latest >= 0:
        infos = infos[:latest]

    rows: list[ScoreRow] = []
    for info in infos:
        try:
            el = read_eval_log(info, header_only=True)
        except Exception:
            # Skip corrupted or unreadable logs silently.
            continue

        task = el.eval.task
        model = el.eval.model
        created = el.eval.created
        status = el.status

        if el.results is None or not el.results.scores:
            rows.append(
                ScoreRow(
                    task=task,
                    model=model,
                    scorer="—",
                    score=None,
                    samples=None,
                    status=status,
                    created=created,
                )
            )
            continue

        for sc in el.results.scores:
            # Pick the primary metric: prefer "accuracy", then "mean", then first.
            metric = sc.metrics.get("accuracy") or sc.metrics.get("mean")
            if metric is None and sc.metrics:
                metric = next(iter(sc.metrics.values()))
            score_val = metric.value if metric is not None else None

            rows.append(
                ScoreRow(
                    task=task,
                    model=model,
                    scorer=sc.scorer,
                    score=score_val,
                    samples=sc.scored_samples,
                    status=status,
                    created=created,
                )
            )

    rows.sort(key=lambda r: (r.task, r.model, r.created))
    return rows


# ---------------------------------------------------------------------------
# Table formatting
# ---------------------------------------------------------------------------

def _format_table(rows: list[ScoreRow]) -> str:
    """Render *rows* as an aligned plain-text table."""
    if not rows:
        return "No eval logs found."

    headers = ("Task", "Model", "Scorer", "Score", "Samples", "Status")
    # Build string cells.
    cells: list[list[str]] = []
    for r in rows:
        score_str = f"{r.score:.3f}" if r.score is not None else "—"
        samples_str = str(r.samples) if r.samples is not None else "—"
        cells.append(
            [r.task, r.model, r.scorer, score_str, samples_str, r.status]
        )

    # Compute column widths.
    col_widths = [len(h) for h in headers]
    for row in cells:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    # Format.
    sep = "  "
    header_line = sep.join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    lines = [header_line, sep.join("—" * w for w in col_widths)]
    for row in cells:
        lines.append(sep.join(cell.ljust(col_widths[i]) for i, cell in enumerate(row)))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def _format_json(rows: list[ScoreRow]) -> str:
    """Render *rows* as a JSON array."""
    data = [
        {
            "task": r.task,
            "model": r.model,
            "scorer": r.scorer,
            "score": r.score,
            "samples": r.samples,
            "status": r.status,
            "created": r.created,
        }
        for r in rows
    ]
    return json_mod.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

@click.command()
@click.option(
    "--log-dir",
    default="logs",
    show_default=True,
    type=click.Path(),
    help="Directory containing EvalLog files.",
)
@click.option(
    "--latest",
    type=int,
    default=None,
    help="Limit to the last N runs (default: all).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
def compare(log_dir: str, latest: int | None, as_json: bool) -> None:
    """Compare evaluation results from logged runs."""
    rows = _load_rows(log_dir, latest)

    if as_json:
        click.echo(_format_json(rows))
    else:
        click.echo(_format_table(rows))
