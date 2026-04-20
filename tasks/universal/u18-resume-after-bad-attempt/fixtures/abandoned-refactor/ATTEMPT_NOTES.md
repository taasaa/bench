# Bug Fix Attempt Notes

**Date:** 2026-04-18
**Bug:** `get_next()` does string comparison on deadline instead of datetime comparison

## What I tried

1. Started refactoring `get_next_v2()` with parsed datetime storage — abandoned because
   it changes the `add_task()` API contract.

2. Found `duration.py` has `is_expired()` helper that does the right thing.
   Should just import and use it.

3. Left dead code in scheduler.py (commented `get_next_v2`).

## What needs to happen

1. Remove the dead `get_next_v2` comment/stub
2. Import `is_expired` from `duration.py`
3. Replace `task["deadline"] > datetime.now().isoformat()` with `not is_expired(task["deadline"])`
4. Don't touch anything else — `cancel_task` and `pending_count` are fine
