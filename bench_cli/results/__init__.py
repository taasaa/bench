"""bench results -- model card generation from eval logs."""

from bench_cli.results.cli import results
from bench_cli.results.core import (
    generate_card,
    generate_all_cards,
    generate_card_for_model,
    _rating,
    _format_ratio,
    _compute_pillar_scores,
    _slug_from_alias,
    _extract_task_scores,
    _generate_summary,
)

__all__ = [
    "results",
    "generate_card",
    "generate_all_cards",
    "generate_card_for_model",
    "_rating",
    "_format_ratio",
    "_compute_pillar_scores",
    "_slug_from_alias",
    "_extract_task_scores",
    "_generate_summary",
]
