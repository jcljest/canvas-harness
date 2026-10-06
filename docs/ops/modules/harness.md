---
module: harness
health: green
updated: 2026-10-06
---

# harness

## Purpose

The whole canvas-export product: CLI, plan workflow, and the shipped Claude Code harness.

## Inputs

- `local/` user files (see README): secrets, profile.json, courses.json, canvas-config.json.

## Outputs

- Canvas REST API calls; plan preview HTML; approval stamps; result logs.

## Interfaces / Contracts

- CLI: `bin/canvas-export <check|whoami|courses|discover|roster|config|preview|approve|apply|uploads|pdf|get|post|put|delete>`.
- `bin/+a NAME`: hidden-prompt writer for the secrets file.
- Plan format: `canvas_export/plan.py` docstring.
- `profile.json` keys: timezone, projects_root, default_upload_folder, answer_key_label, answer_key_words.
- `courses.json`: `{"courses": [{alias, id, name, local_project?, pdf_prefix?}]}`.
- `canvas-config.json`: auto_approve, auto_preview, auto_publish (defaults false/true/false).
- `$CANVAS_EXPORT_LOCAL` overrides the `local/` folder; `$CANVAS_EXPORT_CHROME` the browser.

## Invariants

- No user-specific data in tracked files.
- The token is never printed, logged or put on argv.
- Writes only under `/api/v1/courses/<id>` for allowlisted ids.
- A plan is applied once, only with a matching typed approval or an auto-approval of an unflagged plan.
- Claude cannot edit `canvas-config.json` or `*.approved` (hooks plus deny rules).

## Dependencies

- Python 3.9+ stdlib. Chrome/Chromium for `pdf` only. Claude Code for the harness.

## Non-goals

- OAuth, multi-user servers, non-Claude agents (CLI works without Claude, but the guards are Claude Code hooks).

## Current Health

**Green**

Reason: Stage 1 scaffold.

## Active Sprints

- 2026-10-06-harness-scaffold

## Next Milestone

Stage 2: the CLI enforces the lock on switches. Stage 3: `/setup` skill.

## Risks

- Guards are pattern-based; a determined agent could bypass them. Stage 2 adds a CLI-side check.
- Personal access tokens carry the user's full Canvas permissions.
