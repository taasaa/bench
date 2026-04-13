"""BaselineStore: persists and retrieves baseline eval results for ratio scoring.

Baselines provide the highest-fidelity reference source for TokenRatioScorer
and TimeRatioScorer. Each baseline is a measured run of a reference model
on a specific task.

Correctness validity gate:
  A baseline is only eligible as a reference if the reference model actually
  solved the task (correctness >= CORRECTNESS_GATE). A fast-but-wrong reference
  would penalize any slower-but-correct model.

Storage:
  baselines/{task_id}/{model_id}.json
  Example: baselines/f6_partial_impl/claude-sonnet-3-5.json
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

BASELINES_DIR = "baselines"
CORRECTNESS_GATE_DEFAULT = 0.8


@dataclass
class Baseline:

    """A single baseline measurement for a (task, model) pair."""

    task_id: str
    model_id: str
    run_at: str  # ISO-8601 timestamp
    correctness: float  # 0.0 to 1.0
    valid_for_reference: bool  # True if correctness >= gate
    total_tokens: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_seconds: float | None = None
    tool_call_count: int | None = None

    def to_dict(self) -> dict:
        """Serialize this baseline to a plain dict for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Baseline:
        """Reconstruct a Baseline from a dict (e.g., loaded from JSON)."""
        return cls(**d)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class BaselineStore:

    """Read/write access to the baseline store on disk."""

    def __init__(self, baselines_dir: str = BASELINES_DIR) -> None:
        self._baselines_dir = Path(baselines_dir)

    def _path(self, task_id: str, model_id: str) -> Path:
        """Return the path for a baseline JSON file.

        Sanitize model_id for filesystem safety (replace / with _).
        """
        safe_model = model_id.replace("/", "_").replace(":", "_")
        return self._baselines_dir / task_id / f"{safe_model}.json"

    def load(self, task_id: str, model_id: str) -> Baseline | None:
        """Load baseline for (task, model). Returns None if not found."""
        path = self._path(task_id, model_id)
        if not path.is_file():
            return None
        try:
            with open(path) as f:
                d = json.load(f)
            return Baseline.from_dict(d)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def save(self, baseline: Baseline, task_id: str, model_id: str) -> None:
        """Save a baseline to disk. Creates directories as needed."""
        path = self._path(task_id, model_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp, then rename
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w") as f:
                json.dump(baseline.to_dict(), f, indent=2)
            tmp.replace(path)
        except OSError:
            # Fallback: direct write
            with open(path, "w") as f:
                json.dump(baseline.to_dict(), f, indent=2)

    def list_all(self) -> list[Baseline]:
        """Return all baselines in the store."""
        baselines: list[Baseline] = []
        if not self._baselines_dir.is_dir():
            return baselines

        for task_dir in self._baselines_dir.iterdir():
            if not task_dir.is_dir():
                continue
            for file in task_dir.iterdir():
                if file.suffix == ".json":
                    try:
                        with open(file) as f:
                            d = json.load(f)
                        baselines.append(Baseline.from_dict(d))
                    except (json.JSONDecodeError, TypeError, KeyError):
                        continue

        return baselines

    def record(
        self,
        task_id: str,
        model_id: str,
        correctness: float,
        total_tokens: int,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_seconds: float | None = None,
        tool_call_count: int | None = None,
        correctness_gate: float = CORRECTNESS_GATE_DEFAULT,
    ) -> Baseline:
        """Create and save a baseline with correctness gate applied.

        Args:
            correctness_gate: Threshold below which the baseline is NOT eligible
                             as a reference (default 0.8).
        """
        baseline = Baseline(
            task_id=task_id,
            model_id=model_id,
            run_at=datetime.now(timezone.utc).isoformat(),
            correctness=correctness,
            valid_for_reference=correctness >= correctness_gate,
            total_tokens=total_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_seconds=latency_seconds,
            tool_call_count=tool_call_count,
        )
        self.save(baseline, task_id, model_id)
        return baseline
