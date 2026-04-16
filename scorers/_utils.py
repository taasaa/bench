"""Shared utilities for scorers."""

from __future__ import annotations

from inspect_ai.solver import TaskState


def message_texts(state: TaskState) -> list[str]:
    """Extract string content from all messages in state.

    Handles both plain str content and list[ContentBlock] content.
    Used by multiple scorers to scan the full message transcript.
    """
    texts: list[str] = []
    for msg in state.messages:
        if hasattr(msg, "content") and isinstance(msg.content, str):
            texts.append(msg.content)
    return texts


def deduplicate_preserve_order(items: list[str]) -> list[str]:
    """Deduplicate a list while preserving first-occurrence order.

    More efficient than creating a dict and sorting by insertion order,
    and avoids the overhead of dict-based dedup when a set+list is clearer.
    """
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique