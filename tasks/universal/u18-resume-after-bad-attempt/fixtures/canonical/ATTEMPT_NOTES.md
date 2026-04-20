# Bug Fix Attempt Notes

**Date:** 2026-04-18
**Bug:** `get_next()` in `scheduler.py` compares deadline as string instead of datetime

## What I tried

1. I started by looking at `duration.py` — it has `parse_iso_datetime()` and `is_expired()`.
   These seem useful but I wasn't sure how to integrate them.

2. I tried adding `from datetime import datetime` at the top of `get_next()` but that
   was already imported. The real issue is the comparison on line 34:
   `task["deadline"] > datetime.now().isoformat()` — this is a string comparison.

3. I looked at changing `_queue` to store parsed datetimes but that would be too
   invasive — it changes the heap ordering logic.

## My approach

I think the right fix is:
- Import `is_expired` from `duration.py` in `scheduler.py`
- Replace the string comparison in `get_next()` with `not is_expired(task["deadline"])`
- Add a test case to verify it works

But I ran out of time before implementing. The key thing is: **use the existing
`is_expired()` helper from duration.py** — don't write new parsing logic.

## False start

I initially thought about converting all deadlines to timestamps at `add_task()` time,
but that would break the API contract — callers pass ISO strings and expect to get
them back. Better to parse at comparison time using the existing helper.
