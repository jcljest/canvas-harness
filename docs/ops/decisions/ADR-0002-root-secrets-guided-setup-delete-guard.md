---
id: ADR-0002
status: accepted
date: 2026-10-06
affected_modules:
  - harness
supersedes: null
superseded_by: null
---

# ADR-0002: Secrets file at the repo root, guided /setup, delete guard on by default

## Context

The owner wants a new user's only manual step to be filling in a secrets file
copied from `.env.example`, with `/setup` doing the rest by asking questions
while it uses the Canvas API. The owner also wants an anti-rm hook active
from the first clone.

## Decision

1. **Secrets file at the repo root** (`.env`, gitignored, `$CANVAS_HARNESS_ENV`
   override), with `.env.example` shipped. This replaces the `local/` location
   for secrets in ADR-0001 only. Everything else stays in `local/`. Deny rules
   name exact secret files, so the example stays readable.
2. **The course allowlist stays user-written.** `CANVAS_COURSE_IDS` lives in
   the secrets file. `/setup` discovers courses through the API and tells
   the user which ids to add, so the user makes a second, small edit.
   Claude never decides which courses the tool may change.
3. **`/setup` skill plus `doctor` command.** Doctor is a read-only checklist
   that never prints secret values. Setup runs it after every step and is
   safe to re-run (add a course, new school year).
4. **Delete guard** (`guard_deletes.py`, Bash): catastrophic deletes are
   denied (`rm -r` of `/`, `~`, `..`, `.git`, `local/`, the project, anything
   outside it except temp folders, `$var` targets; `git clean -x`;
   unfiltered `find -delete`). Every other delete asks the user, even in auto mode.

## Options Considered

- Course allowlist in `courses.json` (written by Claude): one less manual
  edit, but Claude could widen its own access. Rejected.
- Hard-deny all deletes: safest, but blocks routine cleanup. "Ask" keeps the
  user in control without blocking work.

## Consequences

- Setup takes two edits to the secrets file, not one.
- The delete guard is pattern-based, like the other guards. It catches
  mistakes and common forms, not a determined bypass.
