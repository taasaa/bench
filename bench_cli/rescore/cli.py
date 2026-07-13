"""``bench rescore`` command — offline rescore of existing .eval logs."""

from __future__ import annotations

import json as _json

import click

from bench_cli.rescore.core import rescore_logs


@click.command("rescore")
@click.option(
    "--log-dir",
    default="logs",
    show_default=True,
    type=click.Path(),
    help="Directory containing .eval logs (recursive).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Scan logs and report what would be updated; do not write.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Output the RescoreResult as JSON.",
)
def rescore(log_dir: str, dry_run: bool, as_json: bool) -> None:
    """Recompute efficiency-derived scores for every .eval log in ``--log-dir``.

    Rescore makes ZERO API calls. It reads ``sample.model_usage`` from the
    logged binary ZIP and rewrites efficiency fields (cost, tokens, time)
    using the current pricing pipeline. Correctness is never modified.

    Logs that cannot be processed (corrupt ZIP, missing samples,
    status != success) are recorded as skips and the rescore continues.
    """
    result = rescore_logs(log_dir, dry_run=dry_run)

    if as_json:
        click.echo(
            _json.dumps(
                {
                    "total": result.total,
                    "updated": result.updated,
                    "skipped": result.skipped,
                    "skips": [{"path": s.path, "reason": s.reason} for s in result.skips],
                },
                indent=2,
            )
        )
        return

    click.echo(
        f"Rescored {result.total} log(s): "
        f"updated={result.updated} skipped={result.skipped}"
    )
    if result.skips:
        click.echo("")
        click.echo("Skips:")
        for s in result.skips:
            click.echo(f"  {s.path}: {s.reason}")
