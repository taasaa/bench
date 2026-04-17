"""Per-task calibrated budgets from minimax m2.7 baseline measurements.

Each task has a specific token and latency budget derived from actual
baseline runs. reference_cost_usd is the measured average cost per sample
from the minimax m2.7 eval run — this is the benchmark reference.
Future runs are compared against it: ratio > 1 means more expensive.

Budgets should be recalibrated when significant prompt/dataset changes occur.
"""

from __future__ import annotations

from scorers.protocol import TaskBudget

TASK_BUDGETS: dict[str, TaskBudget] = {
    # Calibrated from qwen-local baseline run (2026-04-13) for tokens/latency.
    # reference_cost_usd = minimax m2.7 measured average cost per sample (eval run 2026-04-17).
    "add_tests": TaskBudget(output_tokens=508, latency_seconds=17.0, reference_cost_usd=1.01406e-09),
    "f1_multi_file_verify": TaskBudget(output_tokens=2619, latency_seconds=40.6, reference_cost_usd=3.5409e-09),
    "f6_partial_impl": TaskBudget(output_tokens=752, latency_seconds=30.5, reference_cost_usd=2.27565e-09),
    "f7_format_compliance": TaskBudget(output_tokens=328, latency_seconds=10.8, reference_cost_usd=5.268e-10),
    "f8_negative_constraint": TaskBudget(output_tokens=965, latency_seconds=36.6, reference_cost_usd=2.3550000000000002e-09),
    "f9_cascading_failure": TaskBudget(output_tokens=1451, latency_seconds=29.0, reference_cost_usd=1.614375e-09),
    "f10_env_mismatch": TaskBudget(output_tokens=1364, latency_seconds=33.2, reference_cost_usd=1.06455e-09),
    "f11_intermittent_bug": TaskBudget(output_tokens=1503, latency_seconds=43.9, reference_cost_usd=1.6054499999999999e-09),
    "f12_surgical_fix": TaskBudget(output_tokens=871, latency_seconds=28.3, reference_cost_usd=8.694749999999998e-10),
    "f14_insert_dont_replace": TaskBudget(output_tokens=1141, latency_seconds=40.0, reference_cost_usd=8.788499999999999e-10),
    "f20_scope_calibration": TaskBudget(output_tokens=492, latency_seconds=13.1, reference_cost_usd=4.104e-10),
    "f22_error_spiral": TaskBudget(output_tokens=1800, latency_seconds=60.0, reference_cost_usd=3.30825e-10),
    "f25_prompt_injection": TaskBudget(output_tokens=1200, latency_seconds=45.0, reference_cost_usd=6.1245e-10),
    "f26_instruction_hierarchy": TaskBudget(output_tokens=1400, latency_seconds=50.0, reference_cost_usd=9.384e-10),
    "f27_self_verification": TaskBudget(output_tokens=1100, latency_seconds=40.0, reference_cost_usd=1.9794e-09),
    "u7_git_safety": TaskBudget(output_tokens=900, latency_seconds=35.0, reference_cost_usd=2.940975e-09),
    "u8_edit_reliability": TaskBudget(output_tokens=1100, latency_seconds=40.0, reference_cost_usd=2.3343e-09),
    "f23_ghost_constraint": TaskBudget(output_tokens=903, latency_seconds=35.0, reference_cost_usd=1.7396249999999998e-09),
    "f24_honey_trap": TaskBudget(output_tokens=998, latency_seconds=35.2, reference_cost_usd=1.1339249999999999e-09),
    "q1_verification_gate": TaskBudget(output_tokens=804, latency_seconds=20.8, reference_cost_usd=3.207e-10),
    "q2_do_not_touch": TaskBudget(output_tokens=920, latency_seconds=29.7, reference_cost_usd=8.247e-10),
    "q4_root_cause": TaskBudget(output_tokens=1042, latency_seconds=27.9, reference_cost_usd=9.082499999999999e-10),
    "q3_answer_the_question": TaskBudget(output_tokens=180, latency_seconds=8.0, reference_cost_usd=4.6005749999999995e-09),
    "q5_safe_git_operations": TaskBudget(output_tokens=650, latency_seconds=20.0, reference_cost_usd=1.870125e-09),
    "f4_dependency_version_audit": TaskBudget(output_tokens=1500, latency_seconds=45.0, reference_cost_usd=3.0522e-09),
    "f5_multi_constraint_edit": TaskBudget(output_tokens=1100, latency_seconds=38.0, reference_cost_usd=2.660775e-09),
    "f15_workspace_setup": TaskBudget(output_tokens=2000, latency_seconds=120.0, reference_cost_usd=3.2429999999999997e-09),
    "f16_bug_investigation": TaskBudget(output_tokens=1800, latency_seconds=90.0, reference_cost_usd=1.8015e-10),
    "f17_config_migration": TaskBudget(output_tokens=1600, latency_seconds=80.0, reference_cost_usd=4.7625e-10),
    "f18_direct_answer_first": TaskBudget(output_tokens=120, latency_seconds=6.0, reference_cost_usd=1.644e-10),
    "f19_admit_uncertainty": TaskBudget(output_tokens=800, latency_seconds=25.0, reference_cost_usd=1.6581749999999998e-09),
    "f21_liars_codebase": TaskBudget(output_tokens=2200, latency_seconds=55.0, reference_cost_usd=2.3975249999999997e-09),
}


# Normalized lookup cache (hyphen/underscore variants → TaskBudget)
_TASK_BUDGETS_NORM: dict[str, TaskBudget] = {
    k.replace("_", "-"): v for k, v in TASK_BUDGETS.items()
}


def get_task_budget(task_name: str) -> TaskBudget | None:
    """Look up a calibrated budget by task name (with hyphen/underscore normalization)."""
    if task_name in TASK_BUDGETS:
        return TASK_BUDGETS[task_name]
    return _TASK_BUDGETS_NORM.get(task_name.replace("_", "-"))
