# Architecture

## Purpose

canvas-export is a clonable Claude Code harness for posting to Canvas LMS.
Each user clones it, runs `/setup` in Claude Code, and gets a guarded workflow:
plan -> preview -> approve (human) -> apply -> verify.

## Layout

| part | role |
|---|---|
| `canvas_export/settings.py` | locations of user files (`local/`), loading profile, roster and switches |
| `canvas_export/cli.py` | course-scoped Canvas REST client and command line |
| `canvas_export/plan.py` | plan validation, preview, approval stamps, apply |
| `canvas_export/pdf.py` | HTML -> PDF into a course's upload folder |
| `.claude/` | shipped harness: settings, guard hooks, `canvas-post` and `setup` skills |
| `local/` (gitignored) | everything personal; never committed |
| `templates/` | example user files with safe defaults |

## Boundaries

- Code is generic. A user's choices live in data files under `local/`.
- The token stays inside the CLI process. Writes are limited to allowlisted course ids.
- Approval-relevant files (`canvas-config.json`, `*.approved`) are protected
  from Claude by hooks and deny rules (pattern-based, not a sandbox).

## Modules

- [harness](modules/harness.md)
