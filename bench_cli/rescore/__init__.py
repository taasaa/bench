"""Offline rescore of existing .eval logs against the current pricing pipeline.

Rescore makes zero API calls — it reads model_usage from the logged binary
ZIP and refreshes only efficiency-derived scores. Correctness is never
modified.
"""

from bench_cli.rescore.core import RescoreResult, SkipInfo, rescore_logs

__all__ = ["RescoreResult", "SkipInfo", "rescore_logs"]
