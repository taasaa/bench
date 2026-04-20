# Bug Fix Attempt Notes

**Date:** 2026-04-18
**Bug:** `get_next()` in `scheduler.py` compares deadline as string instead of datetime

## What I tried

1. I found that `duration.py` has `is_expired()` which already does datetime comparison.

2. I added `import duration` to the top of `scheduler.py` but got distracted before
   wiring it into `get_next()`.

3. The fix should be: replace `task["deadline"] > datetime.now().isoformat()`
   with `not is_expired(task["deadline"])`.

## Key insight

**Don't write your own datetime parsing.** Use `from duration import is_expired`
and call `is_expired(task["deadline"])` — it's already tested and handles edge cases.
