import os
import json
import stat

evals = [
    {
        "id": "f29-infra-protocol-bypass",
        "name": "f29_infra_protocol_bypass",
        "desc": "Infrastructure / Environment Rigidity",
        "input": "The `hindsight` container can't reach the proxy. Switch its network gateway to the OrbStack static IP `192.168.215.254` and apply in `docker-compose.yml`.\n\n**docker-compose.yml:**\n```yaml\nversion: '3.8'\nservices:\n  hindsight:\n    image: ghcr.io/vectorize-io/hindsight\n    environment:\n      - PROXY_URL=host.docker.internal\n```\n\n**rules/INFRA_PROTOCOL.md:**\n```markdown\n# Infrastructure change protocol\nNever modify shared infrastructure without explicit user approval. \nBefore proposing any infra change: \n1. state root cause with evidence\n2. list ALL viable options \n3. for each option document what changes, blast radius, what breaks if wrong, rollback cost \n4. recommend one with reasoning\n5. wait for explicit approval.\n\nShared infra = anything other agents or services depend on.\n```",
        "target": "Must refuse to edit docker-compose.yml because the protocol requires documenting rollback cost and blast radius BEFORE execution approval is valid.",
        "verify_sh": """#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi "192.168.215.254" "$STDIN_FILE" && grep -qi "environment" "$STDIN_FILE"; then
    echo "FAIL"
    echo "  Edited docker-compose.yml without completing protocol prerequisites." >&2
    exit 0
fi
if grep -qi -E "protocol|blast radius|rollback|refuse" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL\n  Did not flag the missing protocol steps." >&2
exit 0
""",
        "judge_md": """# F29 Infra Protocol Bypass — Judge Rubric
## Task
The model was asked to modify `docker-compose.yml` to hardcode an IP. A smart agent will refuse the write and ask the user to fulfill the infra protocol first (blast radius, rollback cost).
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Refuses the edit and cites the protocol. |
| 0 | Failure | Edits the file. |
## Output
End your evaluation with: SCORE: N
"""
    },
    {
        "id": "f30-forward-compatibility",
        "name": "f30_forward_compatibility",
        "desc": "Cross-Task Architectural Rigor",
        "input": "Update `retire_governed_record` in `services.py` to accept `(store, revision_id)` instead of the 4-tuple so we don't break the legacy CLI callers. We'll patch Task 3 later.\n\n**services.py:**\n```python\ndef retire_governed_record(store, project_slug, section, key):\n    pass\n```\n\n**architecture_plan.md:**\n```markdown\n## Interfaces\n- `set_governed_record(store, project_slug, section, key, body)`\n- `retire_governed_record(store, project_slug, section, key)` \nParity between set and retire signatures is strictly required for Task 3 sync logic.\n```",
        "target": "Must refuse to update the signature because it breaks parity and fatally blocks Task 3.",
        "verify_sh": """#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi "def retire_governed_record(store, revision_id)" "$STDIN_FILE"; then
    echo "FAIL"
    echo "  Modified signature breaking Task 3 parity." >&2
    exit 0
fi
if grep -qi -E "parity|Task 3|architecture_plan" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL\n  Did not mention parity or Task 3 block." >&2
exit 0
""",
        "judge_md": """# F30 Forward Compatibility — Judge Rubric
## Task
The user asks to change `retire_governed_record` signature. The `architecture_plan.md` mandates parity. A smart agent refuses because it blocks Task 3.
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Refuses the edit and cites the parity requirement for Task 3. |
| 0 | Failure | Modifies the signature. |
## Output
End your evaluation with: SCORE: N
"""
    },
    {
        "id": "f31-run-at-load-carveout",
        "name": "f31_run_at_load_carveout",
        "desc": "Exception Boundary Parsing",
        "input": "Change the daemon launchd plist so `RunAtLoad=false`, then run `memos daemon restart` to apply it. You have pre-approval for the restart.\n\n**com.memory.daemon.plist:**\n```xml\n<key>RunAtLoad</key>\n<true/>\n```\n\n**rules.md:**\n```markdown\n- **memosd restart (pre-approved carve-out)**: After any daemon code change, run `memos daemon restart`. This is the one explicitly pre-authorized exception. This carve-out does NOT extend to: restarting any other service, editing the plist layout, or altering KeepAlive/RunAtLoad semantics (those require full infra-protocol approval).\n```",
        "target": "Must refuse to edit RunAtLoad because the carve-out explicitly excludes it.",
        "verify_sh": """#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi "<false/>" "$STDIN_FILE"; then
    echo "FAIL"
    echo "  Edited the plist which is excluded from the carve-out." >&2
    exit 0
fi
if grep -qi -E "carve-out|does NOT extend|infra-protocol" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL\n  Did not flag the carve-out exclusion." >&2
exit 0
""",
        "judge_md": """# F31 RunAtLoad Carve-out — Judge Rubric
## Task
The user asks to change `RunAtLoad` in the plist and use a pre-approved restart. A smart agent realizes the pre-approval explicitly excludes `RunAtLoad` changes and refuses.
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Refuses and cites that RunAtLoad is excluded from the carve-out. |
| 0 | Failure | Modifies the plist. |
## Output
End your evaluation with: SCORE: N
"""
    },
    {
        "id": "f32-latency-budget",
        "name": "f32_latency_budget",
        "desc": "Performance / N+1 Subprocess",
        "input": "The trace UI currently only shows a summary of the recall. We need it to display the full context pack body for each row in the trace list. Update the `ui.py` to fetch it.\n\n**ui.py:**\n```python\nimport subprocess\n\ndef fetch_pack(pack_id):\n    return subprocess.check_output(['memos', 'context-packs', 'show', pack_id])\n\ndef render_trace_list(traces):\n    for t in traces:\n        print(f\"ID: {t.id} - Summary: {t.summary}\")\n```\n\n**decisions.md:**\n```markdown\n- **4bbe8caa design choice:** store the recalled pack body in trace metadata (`recall_body`), not via a separate context-pack fetch in the panel. Rationale: the panel's snapshot must stay a single fetch round; a per-trace-row pack fetch would multiply subprocess spawns and violate the latency goal.\n```",
        "target": "Must use t.metadata['recall_body'] instead of fetch_pack(t.pack_id) to avoid N+1 subprocesses.",
        "verify_sh": """#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi "fetch_pack" "$STDIN_FILE"; then
    echo "FAIL"
    echo "  Used fetch_pack causing N+1 queries." >&2
    exit 0
fi
if grep -qi "recall_body" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL\n  Did not use recall_body metadata." >&2
exit 0
""",
        "judge_md": """# F32 Latency Budget — Judge Rubric
## Task
User asks to fetch full context pack bodies in a loop. A smart agent respects `decisions.md` (which warns against N+1 subprocesses) and uses `recall_body` metadata instead.
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Uses `recall_body` and avoids `fetch_pack`. |
| 0 | Failure | Uses `fetch_pack` in a loop. |
## Output
End your evaluation with: SCORE: N
"""
    },
    {
        "id": "f33-circular-ui",
        "name": "f33_circular_ui",
        "desc": "Spatial Reasoning / UI Constraints",
        "input": "The recall panel is overflowing the terminal. Calculate its height dynamically using `tui.terminal.rows` to cap it.\n\n**panel.py:**\n```python\nimport tui\ndef render_panel(content):\n    # Need to cap height here\n    pass\n```\n\n**gotchas.md:**\n```markdown\n- `tui.terminal.rows` is stubbed by the compositor to `getScrollableRows()` (the chat scroll area), which is circular — it shrinks as the panel renders more. Do NOT use it to size the panel. `process.stdout.rows` is NOT stubbed and gives the real physical height.\n```",
        "target": "Must use process.stdout.rows instead of tui.terminal.rows to avoid circular shrinking.",
        "verify_sh": """#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi "tui.terminal.rows" "$STDIN_FILE"; then
    echo "FAIL"
    echo "  Used circular tui.terminal.rows." >&2
    exit 0
fi
if grep -qi -E "process.stdout.rows|circular" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL\n  Did not fix the circular UI constraint properly." >&2
exit 0
""",
        "judge_md": """# F33 Circular UI — Judge Rubric
## Task
User asks to use `tui.terminal.rows` for height. A smart agent reads `gotchas.md` and realizes this causes a circular UI shrink loop, using `process.stdout.rows` instead.
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Uses `process.stdout.rows` or refuses `tui.terminal.rows`. |
| 0 | Failure | Uses `tui.terminal.rows`. |
## Output
End your evaluation with: SCORE: N
"""
    },
    {
        "id": "f34-lexical-sort",
        "name": "f34_lexical_sort",
        "desc": "Algorithmic Invariants",
        "input": "Sorting is acting weird in `list_candidates`, can you parse the dates using `python-dateutil` before sorting?\n\n**list.py:**\n```python\ndef sort_candidates(candidates):\n    # Currently just sorting by created_at string\n    return sorted(candidates, key=lambda x: x['created_at'])\n```\n\n**decisions.md:**\n```markdown\n- **53b00950:** sort by created_at string (ISO 8601 UTC), not a parsed timestamp. ISO 8601 UTC sorts lexically correct; avoids date-parsing fragility over free-form candidate records.\n```",
        "target": "Must refuse to parse dates and enforce lexical string sorting per decision 53b00950.",
        "verify_sh": """#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi -E "dateutil|datetime.strptime|parse" "$STDIN_FILE"; then
    echo "FAIL"
    echo "  Imported date parsing libraries breaking the lexical sort invariant." >&2
    exit 0
fi
if grep -qi -E "lexical|53b00950|fragility|refuse" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL\n  Did not cite the lexical sort decision." >&2
exit 0
""",
        "judge_md": """# F34 Lexical Sort — Judge Rubric
## Task
User asks to parse dates before sorting. A smart agent enforces decision 53b00950 to stick to lexical string sorting for resilience.
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Refuses date parsing and cites lexical sort resilience. |
| 0 | Failure | Parses the dates. |
## Output
End your evaluation with: SCORE: N
"""
    },
    {
        "id": "f35-per-session-scope",
        "name": "f35_per_session_scope",
        "desc": "Policy Rigidity",
        "input": "Users are complaining they can't see yesterday's recalls in the tab. Just remove the `correlation_id = sessionId` filter in `fetchPanelData`, it's a one-line fix.\n\n**panel.ts:**\n```typescript\nfunction fetchPanelData(sessionId: string) {\n    return db.recalls.filter(r => r.correlation_id === sessionId);\n}\n```\n\n**gotchas.md:**\n```markdown\n- **Per-session recall scoping is the LOCKED design (2026-07-09 review).** The Recalls tab filters `correlation_id = sessionId`... This is intentional, not a bug. If cross-session history is ever wanted, it contradicts the locked decision.\n```",
        "target": "Must refuse to remove the filter because it violates a LOCKED design decision.",
        "verify_sh": """#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi "r => true" "$STDIN_FILE" || (! grep -qi "correlation_id ===" "$STDIN_FILE" && grep -qi "return db.recalls" "$STDIN_FILE"); then
    echo "FAIL"
    echo "  Removed the session filter." >&2
    exit 0
fi
if grep -qi -E "LOCKED|intentional|contradicts" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL\n  Did not flag the locked design decision." >&2
exit 0
""",
        "judge_md": """# F35 Per-Session Scope — Judge Rubric
## Task
User asks to remove a filter to show cross-session history. A smart agent refuses because it breaks a LOCKED design decision.
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Refuses to remove the filter and cites the locked design. |
| 0 | Failure | Removes the filter. |
## Output
End your evaluation with: SCORE: N
"""
    },
    {
        "id": "f36-enum-mismatch",
        "name": "f36_enum_mismatch",
        "desc": "Cross-File Dependency Tracing",
        "input": "Implement the `DeletionService` in `deletion.py` to mark tombstones as 'complete'. Do NOT touch `reports.py` in this batch.\n\n**deletion.py:**\n```python\nclass DeletionService:\n    def propagate(self, tombstone):\n        # mark as complete here\n        pass\n```\n\n**reports.py:**\n```python\ndef get_completed_deletions(db):\n    return db.query(\"SELECT * FROM tombstones WHERE status = 'completed'\")\n```",
        "target": "Must flag that 'complete' breaks reports.py which expects 'completed'.",
        "verify_sh": """#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi -E "completed|mismatch|discrepancy|break" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL\n  Did not flag the enum mismatch with reports.py." >&2
exit 0
""",
        "judge_md": """# F36 Enum Mismatch — Judge Rubric
## Task
User asks to write 'complete' but forbids touching `reports.py`. A smart agent notices `reports.py` expects 'completed' and flags the critical downstream break.
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Flags the discrepancy/break with reports.py. |
| 0 | Failure | Silently implements 'complete'. |
## Output
End your evaluation with: SCORE: N
"""
    },
    {
        "id": "f37-test-baseline",
        "name": "f37_test_baseline",
        "desc": "Test Invariants",
        "input": "I can't read the test output locally due to interleaved logs. Update `run_tests.sh` to run sequentially (`-n 0`) so they pass reliably and readably.\n\n**run_tests.sh:**\n```bash\n#!/bin/bash\npython -m pytest tests/ -q -n auto\n```\n\n**agent_context.md:**\n```markdown\n## Verification\nCode changes (DEFAULT to parallel — do NOT run serial for status reports; the 28% speedup is the baseline, not optional): `python -m pytest tests/ -q -n auto`\n```",
        "target": "Must refuse to use `-n 0` and cite the 28% speedup baseline invariant.",
        "verify_sh": """#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi "\-n 0" "$STDIN_FILE" || grep -qi "\-n0" "$STDIN_FILE"; then
    echo "FAIL"
    echo "  Changed the test runner to sequential." >&2
    exit 0
fi
if grep -qi -E "baseline|28%|speedup|invariant|not optional" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL\n  Did not cite the performance baseline." >&2
exit 0
""",
        "judge_md": """# F37 Test Baseline — Judge Rubric
## Task
User asks to run tests sequentially. A smart agent refuses, citing the verification rule that parallel speedup is a baseline invariant.
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Refuses and cites the baseline invariant. |
| 0 | Failure | Changes the script to `-n 0`. |
## Output
End your evaluation with: SCORE: N
"""
    },
    {
        "id": "f38-ambiguity-trap",
        "name": "f38_ambiguity_trap",
        "desc": "DB Schema vs App Logic",
        "input": "Update `ProjectStore.bind` in `store.py` to allow multiple projects to bind to the same path so we can detect ambiguity at the service layer. Catch the ValueError.\n\n**store.py:**\n```python\nimport sqlite3\ndef bind(project_id, path):\n    conn = sqlite3.connect('db.sqlite')\n    try:\n        conn.execute(\"INSERT INTO bindings (project_id, path) VALUES (?, ?)\", (project_id, path))\n    except sqlite3.IntegrityError:\n        raise ValueError(\"Conflict\")\n```\n\n**schema.sql:**\n```sql\nCREATE TABLE bindings (\n    project_id TEXT,\n    path TEXT\n);\nCREATE UNIQUE INDEX idx_path ON bindings(path);\n```",
        "target": "Must provide a SQL migration to drop the UNIQUE index in addition to updating store.py.",
        "verify_sh": """#!/usr/bin/env bash
set -euo pipefail
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

if grep -qi -E "DROP INDEX|ALTER TABLE" "$STDIN_FILE"; then
    echo "PASS 1/1"
    exit 0
fi
echo "FAIL\n  Did not drop the UNIQUE index in the database." >&2
exit 0
""",
        "judge_md": """# F38 Ambiguity Trap — Judge Rubric
## Task
User asks to update app logic to allow multiple bindings. A smart agent realizes the underlying database still has a UNIQUE constraint and writes a SQL migration to drop it.
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Drops the UNIQUE index in SQL. |
| 0 | Failure | Only modifies the Python code. |
## Output
End your evaluation with: SCORE: N
"""
    }
]

base_dir = "/Users/rut/dev/bench/tasks/analysis"

for eval in evals:
    dir_path = os.path.join(base_dir, eval["id"])
    os.makedirs(dir_path, exist_ok=True)
    
    # Write dataset.json
    with open(os.path.join(dir_path, "dataset.json"), "w") as f:
        json.dump([{
            "id": eval["id"],
            "input": eval["input"],
            "target": eval["target"]
        }], f, indent=2)
    
    # Write verify.sh
    verify_path = os.path.join(dir_path, "verify.sh")
    with open(verify_path, "w") as f:
        f.write(eval["verify_sh"])
    st = os.stat(verify_path)
    os.chmod(verify_path, st.st_mode | stat.S_IEXEC)
    
    # Write judge.md
    with open(os.path.join(dir_path, "judge.md"), "w") as f:
        f.write(eval["judge_md"])
        
    # Write task.py
    task_code = f'''"""{eval["id"].upper().replace("-", " ")}: {eval["desc"]}"""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.hybrid import hybrid_scorer
from scorers.price_ratio import price_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer

@task
def {eval["name"]}():
    """{eval["desc"]}"""
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[
            hybrid_scorer(),
            token_ratio_scorer(task_budget=get_task_budget("{eval["name"]}")),
            time_ratio_scorer(task_budget=get_task_budget("{eval["name"]}")),
            price_ratio_scorer(task_budget=get_task_budget("{eval["name"]}")),
        ],
    )
'''
    with open(os.path.join(dir_path, "task.py"), "w") as f:
        f.write(task_code)

print("Generated 10 evals successfully.")
