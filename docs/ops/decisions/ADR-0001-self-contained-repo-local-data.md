---
id: ADR-0001
status: accepted
date: 2026-10-06
affected_modules:
  - harness
supersedes: null
superseded_by: null
---

# ADR-0001: Self-contained repo, with all user data in a gitignored local/

## Context

The tool began as one person's setup, with personal files in the repo root
and guard hooks linked from a private shared repo. Other users need to clone
it and customize it without forking someone's data or depending on files they
don't have.

## Decision

- The repo ships its own `.claude/` folder: settings, guard hooks and skills.
  It has no symlinks to any outside repo.
- Every per-user file lives in `local/` (gitignored), overridable with
  `$CANVAS_EXPORT_LOCAL`. User customization is data (`profile.json`,
  `courses.json`, `canvas-config.json`), never edits to code or skills.
- Defaults are the safe ones: auto_approve false, auto_publish false, auto_preview true.
- `docs/ops/` ships with the repo and is kept free of any user's data.

## Options Considered

- `~/.config/canvas-export/` for user data: cleaner, but the guards would have
  to protect paths outside the project. Rejected for now.
- A GitHub template repo: makes clean copies, but updates are hard to pull.
  Chose a plain clone plus `git pull`.

## Consequences

- `git pull` never conflicts with user data.
- The project's hooks only run if the user trusts the project in Claude Code.
  The README and `/setup` must say so.
