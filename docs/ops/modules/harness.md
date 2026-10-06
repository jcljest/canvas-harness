---
module: harness
health: green
updated: 2026-10-06
---

# harness

## Purpose

The whole canvas-harness product: CLI, plan workflow, and the shipped Claude Code harness.

## Inputs

- Secrets file at the repo root (user-written from the example template).
- `local/` user files: profile.json, courses.json, canvas-config.json, plans/, uploads/.

## Outputs

- Canvas REST API calls; plan preview HTML; approval stamps; result logs.

## Interfaces / Contracts

- CLI: `bin/canvas-harness <doctor|which|check|whoami|courses|discover|roster|config|preview|approve|apply|uploads|pdf|get|post|put|delete>`.
- `/setup` skill (`.claude/skills/setup`): guided, re-runnable setup.
- `bin/+a NAME`: hidden-prompt writer for the secrets file.
- Plan format: `canvas_harness/plan.py` docstring.
- `profile.json` keys: timezone, projects_root, default_upload_folder, answer_key_label, answer_key_words.
- `courses.json`: `{"courses": [{alias, id, name, nicknames?, local_project?, pdf_prefix?}]}`. Every name (alias, nickname, title; compared ignoring case, spaces and punctuation) must belong to one course only.
- `canvas-harness which NAME`: exit 0 with the one matching course, exit 1 with candidates.
- `canvas-config.json`: auto_approve, auto_preview, auto_publish (defaults false/true/false).
- `$CANVAS_HARNESS_ENV` overrides the secrets file, `$CANVAS_HARNESS_LOCAL` the `local/` folder, `$CANVAS_HARNESS_CHROME` the browser.

## Invariants

- No user-specific data in tracked files.
- The token is never printed, logged or put on argv.
- Writes only under `/api/v1/courses/<id>` for allowlisted ids.
- A plan is applied once, only with a matching typed approval or an auto-approval (any plan when `auto_approve` is on; warnings become post-run alerts, ADR-0004).
- Claude cannot edit `canvas-config.json` or `*.approved` (hooks plus deny rules).
- Claude cannot write the course allowlist (`CANVAS_COURSE_IDS` lives in the user-written secrets file).
- Deletes need the user's confirmation; catastrophic deletes are denied (delete guard).

## Dependencies

- Python 3.9+ stdlib. Chrome/Chromium for `pdf` only. Claude Code for the harness.

## License

- MIT, copyright Jeffrey Lai (`LICENSE`). Acknowledgments of external software and services in `NOTICE.md`; no third-party code is bundled.

## Non-goals

- OAuth, multi-user servers, non-Claude agents (CLI works without Claude, but the guards are Claude Code hooks).

## Current Health

**Green**

Reason: Stage 1 scaffold.

## Active Sprints

- 2026-10-06-harness-scaffold
- 2026-10-06-harness-setup

## Next Milestone

Live `/setup` run on a real Canvas account; Stage 2: the CLI enforces the lock on switches.

## Risks

- Guards are pattern-based; a determined agent could bypass them. Stage 2 adds a CLI-side check.
- Personal access tokens carry the user's full Canvas permissions.
