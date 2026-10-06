---
id: 2026-10-06-harness-setup
module: harness
status: ready_for_review
health: green
owner_session: null
worktree: canvas-harness
started: 2026-10-06
updated: 2026-10-06
base_commit: 6243c07
depends_on: [2026-10-06-harness-scaffold]
blocks: []
---

# Stage 3: guided /setup, root secrets file, anti-rm hook

## Objective

A new user's only manual steps are: trust the project hooks, copy
`.env.example` to `.env` and fill in the URL and token, and later add the
course ids that `/setup` tells them. `/setup` asks questions while it uses the
Canvas API and writes everything else.

## Why This Matters

The owner wants clone -> fill in the secrets file -> `/setup` -> working,
with no manual file editing beyond the secrets.

## Scope

- Secrets file moves to the repo root (`.env`, gitignored); `.env.example`
  ships. Override: `$CANVAS_HARNESS_ENV`. `bin/+a` writes the same file.
- Deny rules list exact secret-file names so `.env.example` stays readable.
- Anti-rm hook (`.claude/hooks/guard_deletes.py`), on from first clone:
  deny catastrophic deletes, ask before any other delete.
- `/setup` skill: prerequisites -> secrets check -> discover courses via API ->
  user picks courses and aliases -> user adds CANVAS_COURSE_IDS -> roster
  verified live -> profile questions -> switches explained -> sample preview.
  Re-runnable to add or change courses.
- `canvas-harness doctor`: one read-only status report setup can rerun.

## Non-goals

- Stage 2 (CLI-enforced switch lock).
- Claude ever writing the secrets file or the course allowlist.

## Acceptance Criteria

- [x] `.env.example` readable by Claude; `.env` still blocked.
- [x] CLI and `+a` read and write the root secrets file; tests updated.
- [x] Anti-rm hook: tested deny cases (`rm -rf /`, `~`, `..`, `.git`, `local`, `git clean -fdx` at root) and ask cases (`rm file`, `find -delete`, `shutil.rmtree`), and ordinary commands allowed.
- [x] `doctor` reports each setup step without printing secrets and works with nothing set up.
- [x] `/setup` skill written; dry run of its steps against a fake `local/` succeeds where no live Canvas is needed.
- [x] Course nicknames: `nicknames` list per course; roster rejects a name (alias, nickname or title) that points to two courses.
- [x] `canvas-harness which NAME` resolves a teacher's name to one course, or says none matched (exit 1) with close candidates.
- [x] `/setup` asks for nicknames and flags overlaps; `canvas-post` resolves names with `which` and offers to save new nicknames.
- [x] All tests pass.

## Plan

1. Secrets path + example + deny rules.
2. Anti-rm hook + tests.
3. `doctor` command.
4. `/setup` skill, README, CLAUDE.md.

## Progress / Checkpoints

### 2026-10-06
- Sprint started after owner asked for: .env-from-example as the only manual step, setup asking questions while using the Canvas API, and an anti-rm hook from the start.
- Design note: course ids stay in the secrets file (user-written) because they are the access allowlist; setup tells the user which ids to add.
- Secrets file moved to repo root with shipped example template; `$CANVAS_HARNESS_ENV` override; deny rules list exact names; tests isolate both env overrides.
- `guard_deletes.py` + 5 tests (deny / ask / temp / allow / hook protocol); wired in settings.json.
- `canvas-harness doctor [--offline]` + tests (all set, allowlist TODO, loose permissions, token never printed).
- Owner renamed the project to canvas-harness (matches the GitHub repo): folder, package `canvas_harness`, command `bin/canvas-harness`, env vars `CANVAS_HARNESS_*`, all docs. Earlier records were updated to the new name.
- `/setup` skill (8 steps, re-run mode, hook probe, two user edits).
- Course nicknames (owner request): `nicknames` in courses.json, collision check in load_roster, `which` command, doctor/roster display, setup step 4 asks "what do you call this class" and flags near overlaps, canvas-post resolves names via `which`. ADR-0003. README quick start, CLAUDE.md, canvas-post skill, ADR-0002, module/architecture docs updated.

## Files Changed

- canvas_harness/{settings,cli,doctor}.py, bin/+a, the example secrets template, .gitignore
- .claude/settings.json, .claude/hooks/guard_deletes.py, .claude/hooks/tests/test_guard_deletes.py
- .claude/skills/setup/SKILL.md, .claude/skills/canvas-post/SKILL.md
- tests/test_{cli,plan,pdf,uploads,doctor}.py
- README.md, CLAUDE.md, docs/ops/{ARCHITECTURE.md, modules/harness.md, decisions/ADR-0002-...}

## Verification Evidence

### Commands Run

```text
python3 -m unittest discover -s tests                 -> Ran 84 tests, OK (after nicknames)
python3 -m unittest discover -s .claude/hooks/tests   -> Ran 20 tests, OK (1 skipped)
bin/canvas-harness doctor (fresh clone)                 -> TODO lines with next steps, rc 1
scratch user (fake secrets, roster, profile) doctor --offline -> All set, rc 0; sample plan previews
personal-data scan of changed files                    -> clean (only the repo's own GitHub URL in a sprint record)
scratch roster: which AP / ap physics / physics      -> @ap / @ap / @phys (rc 0); 'phys class' -> maybe @phys (rc 1); overlapping 'physics' roster -> rejected (rc 2)
```

### Results

- Offline acceptance criteria verified.
- NOT verified: a live /setup run against real Canvas; the step-1 hook probe in a session opened inside this repo (this session's hooks come from the parent folder, so the repo's own hooks weren't active here).

## Decisions

- [ADR-0002](../decisions/ADR-0002-root-secrets-guided-setup-delete-guard.md)
- [ADR-0003](../decisions/ADR-0003-course-nicknames.md)

## Dependency Changes

- None.

## Risks / Blockers

- Live `/setup` not yet exercised against a real Canvas account.

## Human Decision Needed

- None.

## Handoff

### Outcome
Guided /setup, doctor, root secrets file and delete guard built; offline-verified.

### Current State
ready_for_review; nicknames added and pushed to origin/main.

### Next Action
Live run: fresh clone in a new folder, open Claude Code there, follow /setup with a real token.
