"""bench results -- model card generation from eval logs."""

from bench_cli.results.cli import results
from bench_cli.results.core import (
    _compute_pillar_scores,
    _extract_task_scores,
    _format_ratio,
    _generate_summary,
    _rating,
    _slug_from_alias,
    generate_all_cards,
    generate_card,
    generate_card_for_model,
)

__all__ = [
    "_compute_pillar_scores",
    "_extract_task_scores",
    "_format_ratio",
    "_generate_summary",
    "_rating",
    "_slug_from_alias",
    "generate_all_cards",
    "generate_card",
    "generate_card_for_model",
    "results",
]
