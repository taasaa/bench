"""Sentinels for Inspect AI public/private API contracts we depend on.

These tests pin the import surface and parameter list of APIs we use.
They break loudly if a future Inspect release renames or removes any
of them, so we can fix import sites proactively rather than at runtime
inside a 30-task live eval.

All tests are hermetic — they exercise only introspectable symbols,
no model I/O, no log files.
"""

from __future__ import annotations

import inspect


def test_inspect_eval_accepts_bench_kwargs() -> None:
    """`inspect_ai.eval(...)` must accept the kwarg names `bench_cli run` passes.

    Pin the public parameter list so a future Inspect rename surfaces here,
    not at runtime inside a long sequential run.
    """
    from inspect_ai import eval as inspect_eval

    params = set(inspect.signature(inspect_eval).parameters)
    for name in {
        "tasks",
        "model",
        "model_args",
        "solver",
        "sandbox",
        "log_dir",
        "fail_on_error",
        "retry_on_error",
        "max_tasks",
        "max_samples",
        "display",
        "metadata",
    }:
        assert name in params


def test_public_generate_config_and_task_state_imports() -> None:
    """Public `GenerateConfig` and `TaskState` must import without warnings.

    0.3.245 ships these under the public `inspect_ai.model` /
    `inspect_ai.solver` namespaces. If a future release relocates either,
    we want the test to fail at import time, not at task-resolution time.
    """
    from inspect_ai.model import GenerateConfig
    from inspect_ai.solver import TaskState

    cfg = GenerateConfig(timeout=600, attempt_timeout=300)
    assert cfg.timeout == 600
    assert cfg.attempt_timeout == 300
    assert TaskState is not None


def test_private_working_time_api_still_exists_for_latency_scorer() -> None:
    """The private `sample_working_time` utility is required by scorers/time_ratio.

    No public equivalent was found at the time of the 0.3.245 upgrade, so the
    scorer still imports from `inspect_ai._util.working`. Sentinel the API so a
    future removal breaks HERE rather than silently inside a sample's score() call.
    """
    from inspect_ai._util.working import sample_working_time

    assert callable(sample_working_time)
