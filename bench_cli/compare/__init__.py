"""bench compare — pillar-table comparison across models."""

from bench_cli.compare.cli import compare
from bench_cli.compare.core import (
    CompareData,
    PillarScores,
    _extract_from_scorers,
    _fmt,
    _fmt_avg_cost,
    _fmt_cost_ratio,
    _fmt_ratio,
    _fmt_time,
    _fmt_tokens,
    _geometric_mean,
    _is_suppressed,
    _short_model,
    format_json,
    format_pillar_table,
    load_compare_data,
)

__all__ = [
    "CompareData",
    "PillarScores",
    "_extract_from_scorers",
    "_fmt",
    "_fmt_avg_cost",
    "_fmt_cost_ratio",
    "_fmt_ratio",
    "_fmt_time",
    "_fmt_tokens",
    "_geometric_mean",
    "_is_suppressed",
    "_short_model",
    "compare",
    "format_json",
    "format_pillar_table",
    "load_compare_data",
]
