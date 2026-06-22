# Handoff: brain-ctl `context:update --section` appends instead of replacing

**From:** bench project maintainer (via pi session 2026-06-19)
**To:** brain-code / brain-ctl maintainer
**Severity:** medium — causes silent context bloat; not data loss but makes project context files grow unboundedly across sessions.

## Summary

`brain-ctl context:update <slug> --section <name> --content <text>` does NOT replace the section body. It appends the new content to it. Every session that uses this command to "update" a section leaves the old content in place alongside the new, growing the section file each time.

Repro is trivial and was confirmed in this session.

## Repro

```bash
# Show a section before
brain-ctl context bench 2>&1 | sed -n '/#### Current Handoff/,/## Current Handoff/p' | head -5

# Update the section with new content
brain-ctl context:update bench --section "Current Handoff" --content "NEW CONTENT BLOCK"

# Show the section after — the OLD content is still there, NEW appended at the top
brain-ctl context bench 2>&1 | sed -n '/#### Current Handoff/,/## Current Handoff/p' | head -20
```

Expected: section body is replaced with the new content.
Actual: section body now contains `[NEW CONTENT BLOCK]\n<previous body>`. Each subsequent `--section` update grows it further.

## What the user sees

In the bench project's context file, calling `context:update --section "Current Handoff"` three times in a row (once per session wrap) left the file with three session wraps stacked, each prepended in front of the previous one, with no way to remove the old ones via the CLI. The context grew from ~150 lines to ~250 lines within two days, all from this single bug.

## How I discovered it

I was trying to clean up stale "SB task stuck / brain-code 404 bug" references from the bench project context after the user reported the underlying bug was fixed. I called `context:update --section "Current Handoff" --content "..."` with my replacement text. The output showed my new block at the top, but the entire 2026-06-18 wrap and earlier content was still there underneath — my "update" had appended rather than replaced.

I verified the same pattern applied to my updates to `Verification`, `Decisions`, and `Gotchas` (each call added a new bullet but didn't remove the old ones).

## Suggested fix

The `PATCH /projects/<slug>/context` API already supports `full_content` as an alternative to `sections` (confirmed by reading `src/http_server.py:436-447`):

```python
@application.route("/projects/<slug>/context", methods=["PATCH"])
def update_context(slug):
    data, err = _require_json(detail="sections or full_content required")
    ...
    result = _update(
        slug,
        sections=data.get("sections"),
        full_content=data.get("full_content"),
    )
```

The error message I get from the CLI (`{"detail": "Section 'X' updates must be body-only; do not include Markdown headings at levels 1-4. Send a PATCH /projects/<slug>/context request with `full_content` for whole-file or multi-section rewrites.", ...}`) also points to this same endpoint.

Two reasonable approaches, in order of preference:

1. **Make `--section` actually replace by default.** Currently it's surprising (every other `*:update` command in `brain-ctl` replaces the named resource). Add an explicit `--append` flag for the rare case where append is wanted. Backward compatibility: anyone relying on the current append behavior would need to add `--append`, but I think this is rare enough that the surprise-fix is worth it.

2. **Add a separate `context:replace` (or `context:set`) subcommand** that calls the API with `full_content`. Keep `context:update --section` as append for backward compatibility. Less surprising but more surface area.

For context files specifically (vs tasks/projects which are append-only-by-design), replacement is the right semantic — that's what users want when they "update" a section.

## Related observations (FYI, not blocking)

- The CLI also has a separate bug: `brain-ctl --pretty projects:show bench` returns empty for bench (and likely other projects with substantive context), but `brain-ctl context bench` returns the full content fine. Cosmetic; didn't block this work.
- The error message text mentioning `full_content` is a strong signal that the maintainer already intended this to work but didn't expose it via the CLI — possibly just an oversight.

## Suggested verification after fix

```bash
# 1. Confirm replace behavior
brain-ctl context:update testproj --section "Foo" --content "X"
brain-ctl context:update testproj --section "Foo" --content "Y"
# Expected: section now contains only "Y"

# 2. Confirm full-content rewrite still works
curl -X PATCH http://127.0.0.1:27125/projects/testproj/context \
  -H "X-Api-Key: $BRAIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"full_content": "..."}'
# Expected: 200 OK with new content
```

## Workaround for affected users (until fix lands)

1. Hand-edit the vault file directly (users with access).
2. Or archive + recreate the project via `projects:archive` then `projects:create` (heavyweight; loses session/task history).
3. Or accept the bloat and just stop adding to context (existing content stays; new updates keep appending).