"""bench inspect — eval log inspection for stats, compare, and deep-check."""

from bench_cli.inspect.cli import inspect
from bench_cli.inspect.core import (
    SampleScore,
    _load_pillar_map,
    _per_task_stats,
    _resolve_alias,
)

__all__ = [
    "SampleScore",
    "_load_pillar_map",
    "_per_task_stats",
    "_resolve_alias",
    "inspect",
]
