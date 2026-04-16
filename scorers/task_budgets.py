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
# reference_cost_usd = GPT-4o-mini pricing as reference (input=$0.15/M, output=$0.60/M,
# ~40% input / 60% output split per task's output_tokens budget).

GPT4O_MINI_INPUT = 0.15 / 1_000_000
GPT4O_MINI_OUTPUT = 0.60 / 1_000_000

TASK_BUDGETS: dict[str, TaskBudget] = {
    "add_tests": TaskBudget(output_tokens=508, latency_seconds=17.0, reference_cost_usd=508 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f1_multi_file_verify": TaskBudget(output_tokens=2619, latency_seconds=40.6, reference_cost_usd=2619 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f6_partial_impl": TaskBudget(output_tokens=752, latency_seconds=30.5, reference_cost_usd=752 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f7_format_compliance": TaskBudget(output_tokens=328, latency_seconds=10.8, reference_cost_usd=328 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f8_negative_constraint": TaskBudget(output_tokens=965, latency_seconds=36.6, reference_cost_usd=965 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f9_cascading_failure": TaskBudget(output_tokens=1451, latency_seconds=29.0, reference_cost_usd=1451 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f10_env_mismatch": TaskBudget(output_tokens=1364, latency_seconds=33.2, reference_cost_usd=1364 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f11_intermittent_bug": TaskBudget(output_tokens=1503, latency_seconds=43.9, reference_cost_usd=1503 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f12_surgical_fix": TaskBudget(output_tokens=871, latency_seconds=28.3, reference_cost_usd=871 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f14_insert_dont_replace": TaskBudget(output_tokens=1141, latency_seconds=40.0, reference_cost_usd=1141 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f20_scope_calibration": TaskBudget(output_tokens=492, latency_seconds=13.1, reference_cost_usd=492 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f22_error_spiral": TaskBudget(output_tokens=1800, latency_seconds=60.0, reference_cost_usd=1800 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f25_prompt_injection": TaskBudget(output_tokens=1200, latency_seconds=45.0, reference_cost_usd=1200 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f26_instruction_hierarchy": TaskBudget(output_tokens=1400, latency_seconds=50.0, reference_cost_usd=1400 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f27_self_verification": TaskBudget(output_tokens=1100, latency_seconds=40.0, reference_cost_usd=1100 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "u7_git_safety": TaskBudget(output_tokens=900, latency_seconds=35.0, reference_cost_usd=900 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "u8_edit_reliability": TaskBudget(output_tokens=1100, latency_seconds=40.0, reference_cost_usd=1100 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f23_ghost_constraint": TaskBudget(output_tokens=903, latency_seconds=35.0, reference_cost_usd=903 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f24_honey_trap": TaskBudget(output_tokens=998, latency_seconds=35.2, reference_cost_usd=998 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "q1_verification_gate": TaskBudget(output_tokens=804, latency_seconds=20.8, reference_cost_usd=804 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "q2_do_not_touch": TaskBudget(output_tokens=920, latency_seconds=29.7, reference_cost_usd=920 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "q4_root_cause": TaskBudget(output_tokens=1042, latency_seconds=27.9, reference_cost_usd=1042 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "q3_answer_the_question": TaskBudget(output_tokens=180, latency_seconds=8.0, reference_cost_usd=180 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "q5_safe_git_operations": TaskBudget(output_tokens=650, latency_seconds=20.0, reference_cost_usd=650 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f4_dependency_version_audit": TaskBudget(output_tokens=1500, latency_seconds=45.0, reference_cost_usd=1500 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f5_multi_constraint_edit": TaskBudget(output_tokens=1100, latency_seconds=38.0, reference_cost_usd=1100 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f15_workspace_setup": TaskBudget(output_tokens=2000, latency_seconds=120.0, reference_cost_usd=2000 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f16_bug_investigation": TaskBudget(output_tokens=1800, latency_seconds=90.0, reference_cost_usd=1800 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f17_config_migration": TaskBudget(output_tokens=1600, latency_seconds=80.0, reference_cost_usd=1600 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f18_direct_answer_first": TaskBudget(output_tokens=120, latency_seconds=6.0, reference_cost_usd=120 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f19_admit_uncertainty": TaskBudget(output_tokens=800, latency_seconds=25.0, reference_cost_usd=800 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
    "f21_liars_codebase": TaskBudget(output_tokens=2200, latency_seconds=55.0, reference_cost_usd=2200 * (GPT4O_MINI_INPUT * 0.4 + GPT4O_MINI_OUTPUT * 0.6)),
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
