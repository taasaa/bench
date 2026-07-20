# F28 Ghost Rename — Judge Rubric

## Task
The model was asked to update `models.py` and `api.py` to rename `user_id` to `owner_id`. However, the prompt also provided `sync_worker.py` which contains a raw SQL query `SELECT id, user_id, title FROM documents`. An intelligent agent should realize that renaming the column requires updating `sync_worker.py` as well to avoid breaking the nightly sync, despite the prompt's narrow instruction.

## Grading Dimensions

### Dimension 1: Proactive Refactoring
Did the model update `sync_worker.py`?
- Excellent: Updates `sync_worker.py` to `SELECT id, owner_id` (and updates the `export_to_warehouse` parameter if they chose to).
- Poor: Strictly follows the instructions and leaves `sync_worker.py` unchanged or fails to output it.

## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Updates `models.py`, `api.py`, AND `sync_worker.py` correctly. |
| 0 | Failure | Leaves `sync_worker.py` untouched, leading to a broken system. |

## Output
End your evaluation with: SCORE: N (where N is exactly 0 or 10)
