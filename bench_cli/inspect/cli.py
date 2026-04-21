"""CLI adapter for bench inspect — stats, compare, and deep-check."""

from __future__ import annotations

from pathlib import Path

import click

from bench_cli.inspect.core import (
    SampleScore,
    _load_baseline,
    _load_pillar_map,
    _load_samples,
    _per_task_stats,
    _resolve_alias,
    _PILLAR_MAP_NORMALIZED,
    _get_task_dir,
    _LOG_DIR,
)
from bench_cli.compare.core import _fmt_avg_cost, _fmt_cost_ratio, _short_model


@click.group("inspect")
def inspect() -> None:
    """Inspect eval logs — stats, compare, and deep-check for a model."""
    pass


# ---------------------------------------------------------------------------
# inspect stats
# ---------------------------------------------------------------------------

@inspect.command("stats")
@click.option(
    "--model",
    "model_alias",
    required=True,
    help="Full bench alias (e.g. openai/nvidia-nemotron-30b) or short name.",
)
@click.option(
    "--log-dir",
    default=str(_LOG_DIR),
    show_default=True,
    type=click.Path(),
    help="Directory containing .eval log files.",
)
def stats(model_alias: str, log_dir: str) -> None:
    """Print per-task pillar averages for a model."""
    model_alias = _resolve_alias(model_alias)
    log_path = Path(log_dir)
    task_samples = _load_samples(model_alias, log_path, latest_only=True)
    _load_pillar_map()
    pillar_map_norm = _PILLAR_MAP_NORMALIZED

    if not task_samples:
        click.echo(f"No eval logs found for {model_alias}.", err=True)
        raise SystemExit(1)

    click.echo(f"{'─'*100}")
    click.echo(f" MODEL: {_short_model(model_alias)}")
    click.echo(f" TASKS: {len(task_samples)}")
    click.echo(f"{'─'*100}")
    click.echo(f" {'Task':<35} {'Pillar':<12} {'Scorer':<14} {'N':>3}  {'Correct':>8}  {'TokRatio':>9}  {'TimeRatio':>10}  {'CostRatio':>10}  {'Cost/sample':>12}")
    click.echo(f" {'-'*35} {'-'*12} {'-'*14} {'-'*3}  {'-'*8}  {'-'*9}  {'-'*10}  {'-'*10}  {'-'*12}")

    task_list = sorted(task_samples.keys())
    for task in task_list:
        samples = task_samples[task]
        stats_ = _per_task_stats(samples)
        pillar = pillar_map_norm.get(task, "?")
        scorer = stats_.get("scorer_type", "?")
        n = stats_.get("n", 0)

        corr = stats_.get("correctness_avg")
        corr_str = f"{corr:.3f}" if corr is not None else "--"

        tr = stats_.get("token_ratio_avg")
        tr_str = f"{tr:.3f}" if tr is not None else "--"

        lr = stats_.get("time_ratio_avg")
        lr_str = f"{lr:.3f}" if lr is not None else "--"

        pr = stats_.get("price_ratio_avg")
        pr_str = _fmt_cost_ratio(pr) if pr is not None else "--"

        cost = stats_.get("avg_cost_usd")
        cost_str = _fmt_avg_cost(cost) if cost is not None else "--"

        flags = []
        if stats_.get("n_nan_tok"):
            flags.append(f"NaNtok={stats_['n_nan_tok']}")
        if stats_.get("n_nan_time"):
            flags.append(f"NaNtime={stats_['n_nan_time']}")
        if stats_.get("n_tok_suppressed"):
            flags.append(f"tokSup={stats_['n_tok_suppressed']}")
        if stats_.get("n_time_suppressed"):
            flags.append(f"timeSup={stats_['n_time_suppressed']}")
        flag_str = f" [{', '.join(flags)}]" if flags else ""

        click.echo(f" {task:<35} {pillar:<12} {scorer:<14} {n:>3}  {corr_str:>8}  {tr_str:>9}  {lr_str:>10}  {pr_str:>10}  {cost_str:>12}{flag_str}")

    click.echo(f"{'─'*100}")


# ---------------------------------------------------------------------------
# inspect compare
# ---------------------------------------------------------------------------

@inspect.command("compare")
@click.option(
    "--model",
    "model_alias",
    required=True,
    help="Full bench alias or short name.",
)
@click.option(
    "--log-dir",
    default=str(_LOG_DIR),
    show_default=True,
    type=click.Path(),
    help="Directory containing .eval log files.",
)
@click.option(
    "--delta-threshold",
    default=0.15,
    show_default=True,
    type=float,
    help="Flag tasks where correctness delta exceeds this value.",
)
def compare_cmd(model_alias: str, log_dir: str, delta_threshold: float) -> None:
    """Compare new eval scores against the old baseline for a model.

    Today's run is excluded from the baseline. Tasks with correctness delta
    > --delta-threshold are flagged as SIGNIFICANT.
    """
    model_alias = _resolve_alias(model_alias)
    log_path = Path(log_dir)

    # Load current run samples (today only)
    task_samples = _load_samples(model_alias, log_path, latest_only=True)

    if not task_samples:
        click.echo(f"No eval logs found for {model_alias}.", err=True)
        raise SystemExit(1)

    # Load baseline (all runs except today)
    baseline = _load_baseline(model_alias, log_path)

    click.echo(f"{'─'*90}")
    click.echo(f" MODEL: {_short_model(model_alias)}  |  Delta threshold: {delta_threshold}")
    click.echo(f" BASELINE: {len(baseline)} tasks  |  CURRENT: {len(task_samples)} tasks")
    click.echo(f"{'─'*90}")
    click.echo(f" {'Task':<35} {'Old':>8}  {'New':>8}  {'Delta':>8}  {'Flag':<15} Notes")
    click.echo(f" {'-'*35} {'-'*8}  {'-'*8}  {'-'*8}  {'-'*15} {'-'*30}")

    new_tasks = set(task_samples.keys()) - set(baseline.keys())
    gone_tasks = set(baseline.keys()) - set(task_samples.keys())

    # Sort: significant deltas first, then unchanged
    deltas: list[tuple[str, float | None, float | None, float, str, str]] = []
    for task in sorted(task_samples.keys()):
        samples = task_samples[task]
        stats_ = _per_task_stats(samples)
        new_avg = stats_.get("correctness_avg")

        old_avg = baseline.get(task)
        if old_avg is None:
            deltas.append((task, None, new_avg, 0.0, "NEW TASK", ""))
        else:
            delta = (new_avg - old_avg) if new_avg is not None else 0.0
            abs_d = abs(delta)
            if abs_d > delta_threshold:
                flag = "*** SIGNIFICANT"
            elif abs_d > 0.05:
                flag = "* notable"
            else:
                flag = ""
            deltas.append((task, old_avg, new_avg, delta, flag, ""))

    # Sort: significant first, then notable, then rest
    def sort_key(item: tuple) -> tuple[int, float]:
        _, old, new, delta, flag, _ = item
        priority = 0 if "SIGNIFICANT" in flag else (1 if "* notable" in flag else 2)
        return (priority, -abs(delta))
    deltas.sort(key=sort_key)

    has_issues = False
    for task, old_avg, new_avg, delta, flag, notes in deltas:
        old_str = f"{old_avg:.3f}" if old_avg is not None else "N/A"
        new_str = f"{new_avg:.3f}" if new_avg is not None else "N/A"
        delta_str = f"{delta:+.3f}" if new_avg is not None and old_avg is not None else "N/A"
        flag_str = flag
        if "SIGNIFICANT" in flag or "notable" in flag:
            has_issues = True
        click.echo(f" {task:<35} {old_str:>8}  {new_str:>8}  {delta_str:>8}  {flag_str:<15}")

    if new_tasks:
        click.echo(f"\n NEW TASKS (not in baseline): {', '.join(sorted(new_tasks))}")
    if gone_tasks:
        click.echo(f"\n GONE TASKS (in baseline, not in current): {', '.join(sorted(gone_tasks))}")

    click.echo(f"{'─'*90}")
    if has_issues:
        click.echo(" ⚠ Some tasks have notable deltas — run deep-check to investigate.")


# ---------------------------------------------------------------------------
# inspect deep-check
# ---------------------------------------------------------------------------

@inspect.command("deep-check")
@click.option(
    "--model",
    "model_alias",
    required=True,
    help="Full bench alias or short name.",
)
@click.option(
    "--log-dir",
    default=str(_LOG_DIR),
    show_default=True,
    type=click.Path(),
    help="Directory containing .eval log files.",
)
@click.option(
    "--output",
    type=click.Path(),
    default=None,
    help="Write QA report to file instead of stdout.",
)
def deep_check(model_alias: str, log_dir: str, output: str | None) -> None:
    """Full QA pass — read every sample output and judge explanation for a model."""
    model_alias = _resolve_alias(model_alias)
    log_path = Path(log_dir)
    task_samples = _load_samples(model_alias, log_path, latest_only=True)
    _load_pillar_map()
    pillar_map_norm = _PILLAR_MAP_NORMALIZED

    if not task_samples:
        click.echo(f"No eval logs found for {model_alias}.", err=True)
        raise SystemExit(1)

    lines: list[str] = []
    lines.append(f"# Deep QA Report — {model_alias}")
    lines.append(f"**Date:** {__import__('datetime').date.today().isoformat()}")
    lines.append(f"**Tasks:** {len(task_samples)}")
    lines.append("")

    # ── Anomaly summary ──────────────────────────────────────────────────────
    anomalies: list[str] = []
    all_tasks = sorted(task_samples.keys())

    for task in all_tasks:
        samples = task_samples[task]
        stats_ = _per_task_stats(samples)
        n = stats_.get("n", 0)

        # Hard anomalies
        if stats_.get("all_correctness_one") and n > 1:
            anomalies.append(f"{task}: ALL-PERFECT correctness (1.0) — verify scorer isn't broken")
        if stats_.get("all_correctness_zero"):
            anomalies.append(f"{task}: ALL-ZERO correctness — scorer bug or model failure")
        if stats_.get("n_nan_tok") == n and n > 0:
            anomalies.append(f"{task}: ALL NaN token_ratio — missing reference budget in task_budgets.py")
        if stats_.get("n_nan_time") == n and n > 0:
            anomalies.append(f"{task}: ALL NaN time_ratio — noise floor triggering incorrectly")

        # Scorer-specific: non-binary verify_sh scores are expected (n/total checks),
        # not a scorer bug. Collect unique values for optional info (not an anomaly).
        if stats_.get("scorer_type") == "verify_sh" and not stats_.get("all_verify_sh_binary"):
            pass  # expected behavior, intentionally no anomaly entry

        # Judge quality
        for s in samples:
            if s.scorer_type in ("llm_judge", "hybrid_scorer") and s.judge_explanation:
                if len(s.judge_explanation) < 30:
                    anomalies.append(f"{task}/{s.sample_id}: judge explanation too short (<30 chars)")
                    break

    if anomalies:
        lines.append("## Anomalies")
        for a in anomalies:
            lines.append(f"- {a}")
        lines.append("")

    # ── Per-task deep check ───────────────────────────────────────────────────
    lines.append("## Per-Task Deep Check")
    lines.append("")

    task_verdicts: list[dict] = []

    for task in all_tasks:
        samples = task_samples[task]
        stats_ = _per_task_stats(samples)
        pillar = pillar_map_norm.get(task, "?")
        scorer_type = stats_.get("scorer_type", "?")
        n = stats_.get("n", 0)
        corr_avg = stats_.get("correctness_avg")
        n_llm = stats_.get("n_llm_judge_samples", 0)

        # Read task files
        task_dir = _get_task_dir(task)
        task_py = ""
        scorer_file = ""
        scorer_content = ""

        if task_dir:
            task_py = (task_dir / "task.py").read_text()[:800] if (task_dir / "task.py").is_file() else ""
            if scorer_type == "llm_judge" or scorer_type == "hybrid_scorer":
                for f in ("judge.md", "judge.yaml"):
                    p = task_dir / f
                    if p.is_file():
                        scorer_file = f
                        scorer_content = p.read_text()[:600]
                        break
            elif scorer_type == "verify_sh":
                verify_script = task_dir / "verify.sh"
                if verify_script.is_file():
                    scorer_file = "verify.sh"
                    scorer_content = verify_script.read_text()[:600]

        # Judge quality analysis
        judge_quality = "N/A"
        judge_notes = ""
        if n_llm > 0:
            explanations = [s.judge_explanation for s in samples if s.judge_explanation]
            if not explanations:
                judge_quality = "BROKEN"
                judge_notes = "No explanations found"
            else:
                lens = [len(e) for e in explanations]
                avg_len = sum(lens) / len(lens)
                unique = len(set(explanations))
                if avg_len < 50:
                    judge_quality = "BROKEN"
                    judge_notes = f"Explanations too short (avg {avg_len:.0f} chars)"
                elif unique == 1 and len(explanations) > 1:
                    judge_quality = "BROKEN"
                    judge_notes = "All explanations identical — rubber stamping"
                elif unique <= 2 and len(explanations) > 4:
                    judge_quality = "WEAK"
                    judge_notes = f"Only {unique} unique explanations for {len(explanations)} samples"
                else:
                    judge_quality = "SOUND"
                    judge_notes = f"Avg explanation length: {avg_len:.0f} chars, {unique} unique"

        # Score correctness — verify_sh scores are always SOUND (n/total is by design)
        score_sound = "SOUND"
        score_notes = ""
        if scorer_type in ("llm_judge", "hybrid_scorer"):
            mismatches = 0
            for s in samples:
                if s.judge_explanation and s.correctness is not None:
                    text_lower = s.judge_explanation.lower()
                    if s.correctness >= 0.75 and not any(w in text_lower for w in ["good", "correct", "pass", "acceptable", "well"]):
                        mismatches += 1
                    elif s.correctness < 0.5 and not any(w in text_lower for w in ["incorrect", "wrong", "fail", "poor", "bad"]):
                        mismatches += 1
            if mismatches > len(samples) * 0.5:
                score_sound = "UNCERTAIN"
                score_notes = f"{mismatches}/{len(samples)} explanations don't match score"
            else:
                score_sound = "SOUND"

        # Hybrid check
        hybrid_ok = True
        hybrid_notes = ""
        if scorer_type == "hybrid_scorer":
            for s in samples:
                if s.verify_sh_score is not None and s.llm_judge_score is not None and s.correctness is not None:
                    expected = s.verify_sh_score * 0.7 + s.llm_judge_score * 0.3
                    if abs(expected - s.correctness) > 0.01:
                        hybrid_ok = False
                        hybrid_notes = f"Hybrid mismatch: verify={s.verify_sh_score}, judge={s.llm_judge_score}, combined={s.correctness}"
                        break
            if hybrid_ok:
                hybrid_notes = "Hybrid weights correct"

        # Task design
        task_design = "REASONABLE"
        design_notes = ""
        prompt_lines = [l for l in task_py.split("\n") if l.strip() and not l.strip().startswith("#")]
        if not prompt_lines:
            task_design = "UNCERTAIN"
            design_notes = "Could not read task prompt"
        elif corr_avg is not None and corr_avg >= 0.95 and n >= 4:
            task_design = "TOO EASY"
            design_notes = f"All models score {corr_avg:.0%} — task provides no signal"
        elif corr_avg is not None and corr_avg <= 0.2 and n >= 4:
            task_design = "TOO HARD"
            design_notes = f"All models score {corr_avg:.0%} — task may be unrealistic"

        # Overall verdict
        if judge_quality == "BROKEN" or score_sound == "FLAWED":
            verdict = "FLAWED"
        elif judge_quality == "WEAK" or score_sound == "UNCERTAIN" or task_design in ("TOO EASY", "TOO HARD"):
            verdict = "UNCERTAIN"
        else:
            verdict = "SOUND"

        lines.append(f"### {task} (`{pillar}`)")
        lines.append(f"| Field | Value |")
        lines.append(f"|-------|-------|")
        lines.append(f"| **Scorer** | {scorer_type} |")
        lines.append(f"| **Samples** | {n} |")
        corr_str = f"{corr_avg:.3f}" if corr_avg is not None else "N/A"
        lines.append(f"| **Correctness avg** | {corr_str} |")
        lines.append(f"| **Judge quality** | {judge_quality} |")
        if judge_notes:
            lines.append(f"| **Judge notes** | {judge_notes} |")
        lines.append(f"| **Score sound?** | {score_sound} |")
        if score_notes:
            lines.append(f"| **Score notes** | {score_notes} |")
        if scorer_type == "hybrid_scorer":
            lines.append(f"| **Hybrid** | {hybrid_notes} |")
        lines.append(f"| **Task design** | {task_design} |")
        if design_notes:
            lines.append(f"| **Design notes** | {design_notes} |")
        lines.append(f"| **Verdict** | {verdict} |")
        lines.append("")

        # Sample outputs (first 2)
        lines.append(f"**Sample outputs** (first 2 of {n}):")
        for s in samples[:2]:
            lines.append(f"```")
            lines.append(f"  Sample: {s.sample_id}  correctness={s.correctness}  working_time={s.working_time:.1f}s")
            if s.output_text:
                out_snippet = s.output_text[:400].replace("\n", "\n  ")
                lines.append(f"  Output:\n  {out_snippet}")
            else:
                lines.append(f"  Output: (empty)")
            if s.judge_explanation:
                lines.append(f"  Judge:\n  {s.judge_explanation[:300]}")
            lines.append(f"```")
            lines.append("")

        task_verdicts.append({
            "task": task,
            "pillar": pillar,
            "verdict": verdict,
            "judge_quality": judge_quality,
            "score_sound": score_sound,
            "task_design": task_design,
        })

    # ── Summary table ─────────────────────────────────────────────────────────
    lines.append("## Verdict Summary")
    lines.append("")
    lines.append(f"| Task | Pillar | Judge Quality | Score Sound | Task Design | Verdict |")
    lines.append(f"|------|--------|--------------|-------------|-------------|---------|")
    for v in task_verdicts:
        lines.append(f"| {v['task']} | {v['pillar']} | {v['judge_quality']} | {v['score_sound']} | {v['task_design']} | {v['verdict']} |")

    report = "\n".join(lines)

    if output:
        Path(output).write_text(report, encoding="utf-8")
        click.echo(f"Report written to {output}")
    else:
        click.echo(report)
