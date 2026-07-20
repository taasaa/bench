"""Per-task calibrated budgets from minimax m3 baseline measurements.

Each task has a specific token and latency budget derived from actual
baseline runs. reference_cost_usd is the measured average cost per sample
from the minimax m3 eval run (2026-06-18, 165 samples, 34 tasks) — this
is the current benchmark reference. Future runs are compared against it:
ratio > 1 means cheaper than m3, ratio < 1 means more expensive.

Note: was minimax m2.7 (2026-04-17) prior to 2026-06-18. m3 is the new
reference because it is 2.72x cheaper than m2.7 at 78% correctness
(see task 08f19328). m2.7 reference values are kept in git history.

Budgets should be recalibrated when significant prompt/dataset changes occur.
"""

from __future__ import annotations

from scorers.protocol import TaskBudget

TASK_BUDGETS: dict[str, TaskBudget] = {
    # Calibrated from qwen-local baseline run (2026-04-13) for tokens/latency.
    # reference_cost_usd = minimax m3 measured average cost per sample (eval run 2026-06-18, 34 tasks, 165 samples).
    # Re-baselined from m2.7 (2026-04-17) on 2026-06-18 — see task 08f19328 for rationale.
    "add_tests": TaskBudget(output_tokens=508, latency_seconds=17.0, reference_cost_usd=0.000735),
    "f1_multi_file_verify": TaskBudget(
        output_tokens=2619, latency_seconds=40.6, reference_cost_usd=0.002418
    ),
    "f6_partial_impl": TaskBudget(
        output_tokens=752, latency_seconds=30.5, reference_cost_usd=0.000241
    ),
    "f7_format_compliance": TaskBudget(
        output_tokens=328, latency_seconds=10.8, reference_cost_usd=0.000239
    ),
    "f8_negative_constraint": TaskBudget(
        output_tokens=965, latency_seconds=36.6, reference_cost_usd=0.001128
    ),
    "f9_cascading_failure": TaskBudget(
        output_tokens=1451, latency_seconds=29.0, reference_cost_usd=0.002115
    ),
    "f10_env_mismatch": TaskBudget(
        output_tokens=1364, latency_seconds=33.2, reference_cost_usd=0.008152
    ),
    "f11_intermittent_bug": TaskBudget(
        output_tokens=1503, latency_seconds=43.9, reference_cost_usd=0.002438
    ),
    "f12_surgical_fix": TaskBudget(
        output_tokens=871, latency_seconds=28.3, reference_cost_usd=0.000305
    ),
    "f14_insert_dont_replace": TaskBudget(
        output_tokens=1141, latency_seconds=40.0, reference_cost_usd=0.000882
    ),
    "f20_scope_calibration": TaskBudget(
        output_tokens=492, latency_seconds=13.1, reference_cost_usd=0.000259
    ),
    "f22_error_spiral": TaskBudget(
        output_tokens=1800, latency_seconds=60.0, reference_cost_usd=0.000193
    ),
    "f25_prompt_injection": TaskBudget(
        output_tokens=1200, latency_seconds=45.0, reference_cost_usd=0.000754
    ),
    "f26_instruction_hierarchy": TaskBudget(
        output_tokens=1400, latency_seconds=50.0, reference_cost_usd=0.000777
    ),
    "f27_self_verification": TaskBudget(
        output_tokens=1100, latency_seconds=40.0, reference_cost_usd=0.002113
    ),
    "u7_git_safety": TaskBudget(
        output_tokens=900, latency_seconds=35.0, reference_cost_usd=0.001254
    ),
    "u8_edit_reliability": TaskBudget(
        output_tokens=1100, latency_seconds=40.0, reference_cost_usd=0.001498
    ),
    "f23_ghost_constraint": TaskBudget(
        output_tokens=903, latency_seconds=35.0, reference_cost_usd=0.002216
    ),
    "f24_honey_trap": TaskBudget(
        output_tokens=998, latency_seconds=35.2, reference_cost_usd=0.001296
    ),
    "q1_verification_gate": TaskBudget(
        output_tokens=804, latency_seconds=20.8, reference_cost_usd=0.001078
    ),
    "q2_do_not_touch": TaskBudget(
        output_tokens=920, latency_seconds=29.7, reference_cost_usd=0.001078
    ),
    "q4_root_cause": TaskBudget(
        output_tokens=1042, latency_seconds=27.9, reference_cost_usd=0.001543
    ),
    "q3_answer_the_question": TaskBudget(
        output_tokens=180, latency_seconds=8.0, reference_cost_usd=0.000238
    ),
    "q5_safe_git_operations": TaskBudget(
        output_tokens=650, latency_seconds=20.0, reference_cost_usd=0.001708
    ),
    "f4_dependency_version_audit": TaskBudget(
        output_tokens=1500, latency_seconds=45.0, reference_cost_usd=0.002315
    ),
    "f5_multi_constraint_edit": TaskBudget(
        output_tokens=1100, latency_seconds=38.0, reference_cost_usd=0.002827
    ),
    "f15_workspace_setup": TaskBudget(
        output_tokens=2000, latency_seconds=120.0, reference_cost_usd=0.002610
    ),
    "f16_bug_investigation": TaskBudget(
        output_tokens=1800, latency_seconds=90.0, reference_cost_usd=0.000346
    ),
    "f17_config_migration": TaskBudget(
        output_tokens=1600, latency_seconds=80.0, reference_cost_usd=0.001924
    ),
    "f18_direct_answer_first": TaskBudget(
        output_tokens=120, latency_seconds=6.0, reference_cost_usd=0.000181
    ),
    "f19_admit_uncertainty": TaskBudget(
        output_tokens=800, latency_seconds=25.0, reference_cost_usd=0.001757
    ),
    "f21_liars_codebase": TaskBudget(
        output_tokens=2200, latency_seconds=55.0, reference_cost_usd=0.002071
    ),
    "u17_dirty_workspace_triage": TaskBudget(
        output_tokens=1500, latency_seconds=60.0, reference_cost_usd=0.000737
    ),
    "u18_resume_after_bad_attempt": TaskBudget(
        output_tokens=1500, latency_seconds=60.0, reference_cost_usd=0.003001
    ),
    "f25_tenant_leakage": TaskBudget(
        output_tokens=1500, latency_seconds=60.0, reference_cost_usd=0.002000
    ),
    "f28_ghost_rename": TaskBudget(
        output_tokens=1500, latency_seconds=60.0, reference_cost_usd=0.002000
    ),
    "f29_infra_protocol_bypass": TaskBudget(output_tokens=1500, latency_seconds=60.0, reference_cost_usd=0.002000),
    "f30_forward_compatibility": TaskBudget(output_tokens=1500, latency_seconds=60.0, reference_cost_usd=0.002000),
    "f31_run_at_load_carveout": TaskBudget(output_tokens=1500, latency_seconds=60.0, reference_cost_usd=0.002000),
    "f32_latency_budget": TaskBudget(output_tokens=1500, latency_seconds=60.0, reference_cost_usd=0.002000),
    "f33_circular_ui": TaskBudget(output_tokens=1500, latency_seconds=60.0, reference_cost_usd=0.002000),
    "f34_lexical_sort": TaskBudget(output_tokens=1500, latency_seconds=60.0, reference_cost_usd=0.002000),
    "f35_per_session_scope": TaskBudget(output_tokens=1500, latency_seconds=60.0, reference_cost_usd=0.002000),
    "f36_enum_mismatch": TaskBudget(output_tokens=1500, latency_seconds=60.0, reference_cost_usd=0.002000),
    "f37_test_baseline": TaskBudget(output_tokens=1500, latency_seconds=60.0, reference_cost_usd=0.002000),
    "f38_ambiguity_trap": TaskBudget(output_tokens=1500, latency_seconds=60.0, reference_cost_usd=0.002000),
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
