---
id: ADR-0004
status: accepted
date: 2026-10-06
affected_modules:
  - harness
supersedes: null
superseded_by: null
---

# ADR-0004: auto_approve sends every plan; warnings become alerts afterwards

## Context

With `auto_approve` on, `apply` used to refuse any plan with a warning other
than "will be PUBLISHED". Announcements that post immediately are flagged, so
routine announcements still needed a typed `approve`. The owner said this was
causing issues and asked that, with approval switched off, plans go through
without the check and alerts be written after the fact.

## Decision

- `auto_approve: true`: `apply` approves every plan. Warnings that used to
  block (deletes, past or offset-less dates, timezone mismatches, answer-key
  filenames, overwrites, immediate announcements, files over 100 MB) are printed
  as `ALERT step N: ...` after the run and saved under `"alerts"` in
  `<plan>.result.json`.
- `auto_approve: false` (the default) is unchanged: the typed `approve` is required.
- Plan hashing, apply-once, course allowlist and config guards are unchanged.

## Options considered

1. Keep blocking flagged plans. Rejected by the owner: it got in the way of announcements.
2. Unblock only announcements. Not chosen: the owner asked for no check at all.
3. No check; alerts afterwards (chosen).

## Consequences

- With the switch on, deletes and answer-key uploads go out without a gate; the
  user learns of them only from the alerts. The canvas-post skill tells Claude
  to relay every alert.
- `preview` still lists every warning before `apply`, so a careful user can
  still review first.
