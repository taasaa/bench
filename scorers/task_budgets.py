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
    # Recalculated with correct per-M pricing (2026-04-20).
    "add_tests": TaskBudget(output_tokens=508, latency_seconds=17.0, reference_cost_usd=0.00101406),
    "f1_multi_file_verify": TaskBudget(
        output_tokens=2619, latency_seconds=40.6, reference_cost_usd=0.0035409
    ),
    "f6_partial_impl": TaskBudget(
        output_tokens=752, latency_seconds=30.5, reference_cost_usd=0.0022756499999999997
    ),
    "f7_format_compliance": TaskBudget(
        output_tokens=328, latency_seconds=10.8, reference_cost_usd=0.0005268
    ),
    "f8_negative_constraint": TaskBudget(
        output_tokens=965, latency_seconds=36.6, reference_cost_usd=0.0023550000000000003
    ),
    "f9_cascading_failure": TaskBudget(
        output_tokens=1451, latency_seconds=29.0, reference_cost_usd=0.001614375
    ),
    "f10_env_mismatch": TaskBudget(
        output_tokens=1364, latency_seconds=33.2, reference_cost_usd=0.00106455
    ),
    "f11_intermittent_bug": TaskBudget(
        output_tokens=1503, latency_seconds=43.9, reference_cost_usd=0.00160545
    ),
    "f12_surgical_fix": TaskBudget(
        output_tokens=871, latency_seconds=28.3, reference_cost_usd=0.0008694750000000001
    ),
    "f14_insert_dont_replace": TaskBudget(
        output_tokens=1141, latency_seconds=40.0, reference_cost_usd=0.0008788499999999999
    ),
    "f20_scope_calibration": TaskBudget(
        output_tokens=492, latency_seconds=13.1, reference_cost_usd=0.0004104
    ),
    "f22_error_spiral": TaskBudget(
        output_tokens=1800, latency_seconds=60.0, reference_cost_usd=0.00033082500000000003
    ),
    "f25_prompt_injection": TaskBudget(
        output_tokens=1200, latency_seconds=45.0, reference_cost_usd=0.0006124500000000001
    ),
    "f26_instruction_hierarchy": TaskBudget(
        output_tokens=1400, latency_seconds=50.0, reference_cost_usd=0.0009383999999999999
    ),
    "f27_self_verification": TaskBudget(
        output_tokens=1100, latency_seconds=40.0, reference_cost_usd=0.0019794
    ),
    "u7_git_safety": TaskBudget(
        output_tokens=900, latency_seconds=35.0, reference_cost_usd=0.002940975
    ),
    "u8_edit_reliability": TaskBudget(
        output_tokens=1100, latency_seconds=40.0, reference_cost_usd=0.0023342999999999997
    ),
    "f23_ghost_constraint": TaskBudget(
        output_tokens=903, latency_seconds=35.0, reference_cost_usd=0.001739625
    ),
    "f24_honey_trap": TaskBudget(
        output_tokens=998, latency_seconds=35.2, reference_cost_usd=0.001133925
    ),
    "q1_verification_gate": TaskBudget(
        output_tokens=804, latency_seconds=20.8, reference_cost_usd=0.00032070000000000004
    ),
    "q2_do_not_touch": TaskBudget(
        output_tokens=920, latency_seconds=29.7, reference_cost_usd=0.0008246999999999999
    ),
    "q4_root_cause": TaskBudget(
        output_tokens=1042, latency_seconds=27.9, reference_cost_usd=0.0009082500000000001
    ),
    "q3_answer_the_question": TaskBudget(
        output_tokens=180, latency_seconds=8.0, reference_cost_usd=0.004600575
    ),
    "q5_safe_git_operations": TaskBudget(
        output_tokens=650, latency_seconds=20.0, reference_cost_usd=0.0018701249999999998
    ),
    "f4_dependency_version_audit": TaskBudget(
        output_tokens=1500, latency_seconds=45.0, reference_cost_usd=0.0030521999999999997
    ),
    "f5_multi_constraint_edit": TaskBudget(
        output_tokens=1100, latency_seconds=38.0, reference_cost_usd=0.0026607749999999998
    ),
    "f15_workspace_setup": TaskBudget(
        output_tokens=2000, latency_seconds=120.0, reference_cost_usd=0.003243
    ),
    "f16_bug_investigation": TaskBudget(
        output_tokens=1800, latency_seconds=90.0, reference_cost_usd=0.00018014999999999996
    ),
    "f17_config_migration": TaskBudget(
        output_tokens=1600, latency_seconds=80.0, reference_cost_usd=0.0010734
    ),
    "f18_direct_answer_first": TaskBudget(
        output_tokens=120, latency_seconds=6.0, reference_cost_usd=0.00016439999999999998
    ),
    "f19_admit_uncertainty": TaskBudget(
        output_tokens=800, latency_seconds=25.0, reference_cost_usd=0.001658175
    ),
    "f21_liars_codebase": TaskBudget(
        output_tokens=2200, latency_seconds=55.0, reference_cost_usd=0.002397525
    ),
    "u17_dirty_workspace_triage": TaskBudget(
        output_tokens=1500, latency_seconds=60.0, reference_cost_usd=None
    ),
    "u18_resume_after_bad_attempt": TaskBudget(
        output_tokens=1500, latency_seconds=60.0, reference_cost_usd=None
    ),
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
