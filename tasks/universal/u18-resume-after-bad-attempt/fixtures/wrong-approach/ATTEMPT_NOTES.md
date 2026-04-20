# Bug Fix Attempt Notes

**Date:** 2026-04-18
**Bug:** `get_next()` compares deadline as string — fails for different date formats

## What I tried

1. I wrote `_to_timestamp()` at the bottom of `scheduler.py` to convert everything
   to timestamps for comparison.

2. **This was wrong.** Converting to timestamps means the original deadline strings
   get lost, and callers that expect ISO format back will break.

3. I saw `duration.py` has `is_expired()` which already handles this correctly.
   That's the right approach — I just didn't get to it.

## Key lesson

The correct fix is to import and use `is_expired()` from `duration.py`.
Don't add new parsing code to `scheduler.py`.
