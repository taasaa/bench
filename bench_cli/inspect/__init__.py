"""bench inspect — eval log inspection for stats, compare, and deep-check."""

from bench_cli.inspect.cli import inspect
from bench_cli.inspect.core import (
    SampleScore,
    _load_baseline,
    _load_pillar_map,
    _load_samples,
    _per_task_stats,
    _resolve_alias,
)

__all__ = [
    "inspect",
    "SampleScore",
    "_load_pillar_map",
    "_per_task_stats",
    "_resolve_alias",
]
