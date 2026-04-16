"""Per-task calibrated budgets from qwen-local baseline measurements.

Each task has a specific token and latency budget derived from actual
baseline runs (62 samples, 16 tasks). These serve as the default reference
when no baseline store entry exists for a given task+model pair.

Budgets should be recalibrated when significant prompt/dataset changes occur.
"""

from __future__ import annotations

from scorers.protocol import TaskBudget

# Calibrated from qwen-local baseline run (2026-04-13).
# Tokens = average total_tokens per sample.
# Latency = average working_time per sample.

TASK_BUDGETS: dict[str, TaskBudget] = {
    "add_tests": TaskBudget(output_tokens=508, latency_seconds=17.0),
    "f1_multi_file_verify": TaskBudget(output_tokens=2619, latency_seconds=40.6),
    "f6_partial_impl": TaskBudget(output_tokens=752, latency_seconds=30.5),
    "f7_format_compliance": TaskBudget(output_tokens=328, latency_seconds=10.8),
    "f8_negative_constraint": TaskBudget(output_tokens=965, latency_seconds=36.6),
    "f9_cascading_failure": TaskBudget(output_tokens=1451, latency_seconds=29.0),
    "f10_env_mismatch": TaskBudget(output_tokens=1364, latency_seconds=33.2),
    "f11_intermittent_bug": TaskBudget(output_tokens=1503, latency_seconds=43.9),
    "f12_surgical_fix": TaskBudget(output_tokens=871, latency_seconds=28.3),
    "f14_insert_dont_replace": TaskBudget(output_tokens=1141, latency_seconds=40.0),
    "f20_scope_calibration": TaskBudget(output_tokens=492, latency_seconds=13.1),
    "f22_error_spiral": TaskBudget(output_tokens=1800, latency_seconds=60.0),
    "f25_prompt_injection": TaskBudget(output_tokens=1200, latency_seconds=45.0),
    "f26_instruction_hierarchy": TaskBudget(output_tokens=1400, latency_seconds=50.0),
    "f27_self_verification": TaskBudget(output_tokens=1100, latency_seconds=40.0),
    "u7_git_safety": TaskBudget(output_tokens=900, latency_seconds=35.0),
    "u8_edit_reliability": TaskBudget(output_tokens=1100, latency_seconds=40.0),
    "f23_ghost_constraint": TaskBudget(output_tokens=903, latency_seconds=35.0),
    "f24_honey_trap": TaskBudget(output_tokens=998, latency_seconds=35.2),
    "q1_verification_gate": TaskBudget(output_tokens=804, latency_seconds=20.8),
    "q2_do_not_touch": TaskBudget(output_tokens=920, latency_seconds=29.7),
    "q4_root_cause": TaskBudget(output_tokens=1042, latency_seconds=27.9),
    # Part III implementations (this session)
    "q3_answer_the_question": TaskBudget(output_tokens=180, latency_seconds=8.0),
    "q5_safe_git_operations": TaskBudget(output_tokens=650, latency_seconds=20.0),
    "f4_dependency_version_audit": TaskBudget(output_tokens=1500, latency_seconds=45.0),
    "f5_multi_constraint_edit": TaskBudget(output_tokens=1100, latency_seconds=38.0),
    "f15_workspace_setup": TaskBudget(output_tokens=2000, latency_seconds=120.0),
    "f16_bug_investigation": TaskBudget(output_tokens=1800, latency_seconds=90.0),
    "f17_config_migration": TaskBudget(output_tokens=1600, latency_seconds=80.0),
    "f18_direct_answer_first": TaskBudget(output_tokens=120, latency_seconds=6.0),
    "f19_admit_uncertainty": TaskBudget(output_tokens=800, latency_seconds=25.0),
    "f21_liars_codebase": TaskBudget(output_tokens=2200, latency_seconds=55.0),
}


def get_task_budget(task_name: str) -> TaskBudget | None:
    """Look up a calibrated budget by task name (with hyphen/underscore normalization)."""
    # Try exact match first
    if task_name in TASK_BUDGETS:
        return TASK_BUDGETS[task_name]
    # Normalize: f12_surgical_fix → f12-surgical-fix
    normalized = task_name.replace("_", "-")
    for key, budget in TASK_BUDGETS.items():
        if key.replace("_", "-") == normalized:
            return budget
    return None
