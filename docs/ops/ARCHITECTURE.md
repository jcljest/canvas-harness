# Architecture

## Purpose

canvas-harness is a clonable Claude Code harness for posting to Canvas LMS.
Each user clones it, runs `/setup` in Claude Code, and gets a guarded workflow:
plan -> preview -> approve (human) -> apply -> verify.

## Layout

| part | role |
|---|---|
| `canvas_harness/settings.py` | locations of user files (`local/`), loading profile, roster and switches |
| `canvas_harness/cli.py` | course-scoped Canvas REST client and command line |
| `canvas_harness/plan.py` | plan validation, preview, approval stamps, apply |
| `canvas_harness/pdf.py` | HTML -> PDF into a course's upload folder |
| `canvas_harness/doctor.py` | read-only setup checklist |
| `.claude/` | shipped harness: settings; secret, approval and delete guards; `canvas-post` and `setup` skills |
| secrets file at root (gitignored) | URL, token, course allowlist; user-written only |
| `local/` (gitignored) | everything else personal; never committed |
| `canvas-config.json` at root (tracked) | shipped recommended switches; maintainer-edited; `local/canvas-config.json` overrides key by key (ADR-0005) |
| `templates/` | example user files with safe defaults |

## Boundaries

- Code is generic. A user's choices live in data files under `local/`.
- The token stays inside the CLI process. Writes are limited to allowlisted course ids.
- Approval-relevant files (`canvas-config.json`, `*.approved`) are protected
  from Claude by hooks and deny rules (pattern-based, not a sandbox).

## Modules

- [harness](modules/harness.md)
