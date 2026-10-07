---
id: ADR-0005
status: accepted
date: 2026-10-07
affected_modules:
  - harness
supersedes: null
superseded_by: null
---

# ADR-0005: The repo ships recommended switches; local/ overrides them

## Context

Switches (`auto_approve`, `auto_preview`, `auto_publish`) were read only from
the gitignored `local/canvas-config.json`, with code defaults false/true/false.
The owner wants the harness itself to carry what is best for new users, not
values tied to one computer.

## Decision

- A tracked `canvas-config.json` at the repo root holds the shipped switches:
  `auto_approve`, `auto_preview` and `auto_publish` all `true`.
- `load_switches()` layers: code fallback (false/true/false) <- shipped root file
  <- `local/canvas-config.json`. The local file overrides key by key and stays
  gitignored.
- Both files are validated the same way; a bad value in either fails closed.
- Both stay Claude-proof: the approval guard and deny rules already match any
  `canvas-config.json`. The maintainer edits the shipped file; users edit their override.
- `canvas-harness config` and `doctor` show which files set the values.

## Options considered

1. Shipped root file + local override (chosen): no merge conflicts when a user
   changes their own switches.
2. Commit `local/canvas-config.json`: users who change a switch get a modified
   tracked file and pull conflicts.
3. Change code defaults only: works, but the recommendation is buried in code.

## Consequences

- A fresh clone auto-approves every plan and creates new items published.
  Deletes, past dates, answer-key uploads and overwrites go out without a gate
  and are reported afterwards as alerts (ADR-0004). `preview` still lists every
  warning before `apply`.
- Users who want the typed approval must add a local override, e.g.
  `{"auto_approve": false}`.
- If the shipped file is removed, the safe code fallback applies.
- `templates/canvas-config.example.json` (safe values) is no longer referenced
  by setup; kept for now.
