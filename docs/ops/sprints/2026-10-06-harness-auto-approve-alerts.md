---
id: 2026-10-06-harness-auto-approve-alerts
module: harness
status: ready_for_review
health: green
owner_session: null
worktree: canvas-harness
started: 2026-10-06
updated: 2026-10-06
base_commit: 4d97804
depends_on: []
blocks: []
---

# auto_approve: alerts instead of blocks

## Objective

When the user has `auto_approve` on, `apply` sends every plan without checking
it first, and writes the warnings afterwards as alerts.

## Non-goals

- Changing behavior when `auto_approve` is off.

## Acceptance Criteria

- [x] auto_approve on + flagged plan (DELETE, past date, immediate announcement, answer-key upload, overwrite): sent, stamp says auto, `ALERT` lines printed, `alerts` in result.json.
- [x] auto_approve on + clean plan: no `alerts` key.
- [x] auto_approve off: typed approval still required.
- [x] Full offline suite passes.

## Verification Evidence

```text
python3 -m unittest discover -s tests   -> Ran 85 tests, OK
```

Not yet exercised against live Canvas.

## Decisions

- [ADR-0004](../decisions/ADR-0004-auto-approve-alerts-not-blocks.md)

## Next Action

User runs one real announcement plan with auto_approve on and confirms the ALERT output, then mark done.
