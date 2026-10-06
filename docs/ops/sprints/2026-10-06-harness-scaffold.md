---
id: 2026-10-06-harness-scaffold
module: harness
status: ready_for_review
health: green
owner_session: null
worktree: canvas-export
started: 2026-10-06
updated: 2026-10-06
base_commit: null
depends_on: []
blocks: []
---

# Stage 1: clonable scaffold with per-user local/ data

## Objective

A clonable `canvas-export` repo: generic CLI code, self-contained Claude Code
guards, and every user-specific file under a gitignored `local/` folder.

## Why This Matters

Other teachers should be able to clone the repo, open it in Claude Code and get
a working, guarded Canvas posting tool, without forking someone's personal setup.

## Scope

- Package `canvas_export/` (cli, plan, pdf, settings) ported from a personal prototype.
- All per-user state under `local/` (override: `$CANVAS_EXPORT_LOCAL`): the secrets file, `profile.json`, `courses.json`, `canvas-config.json`, `plans/`, `uploads/`.
- `profile.json`: timezone, PDF naming (per-course prefix, answer-key label/words), default upload folder. No hardcoded person, school, course or path.
- Safe defaults: auto_approve false, auto_preview true, auto_publish false.
- Date warning when a date's UTC offset doesn't match the profile timezone.
- Self-contained `.claude/`: settings.json, secret guard, config guard, generic `canvas-post` skill.
- `templates/` with example files; generic example plan; tests.

## Non-goals

- Stage 2: CLI-enforced lock on switches (`config set` + fingerprint).
- Stage 3: `/setup` interview skill.
- Stage 4: publishing to GitHub (needs owner approval).

## Acceptance Criteria

- [x] No owner-specific names, ids, paths or course titles in tracked files (grep check).
- [x] With no `local/`, CLI commands give a clear "run /setup" message instead of a traceback.
- [x] All unit tests pass, including the copied guard tests.
- [x] Guards deny Claude edits to `local/canvas-config.json` and reads of the secrets file.
- [x] `git status` with a populated `local/` shows nothing from `local/` (gitignore verified).
- [x] Example plan previews with a test roster.

## Plan

1. Copy and rename modules; central paths in `settings.py`.
2. Generalize PDF naming and timezone via profile.
3. `.claude/` settings, hooks, skill.
4. Tests, templates, README, CLAUDE.md.

## Progress / Checkpoints

### 2026-10-06
- Owner decisions: self-contained repo (no shared-harness symlinks); docs/ops ships but stays generic; user data in gitignored `local/`.
- Ported CLI/plan/pdf into `canvas_export/` package; new `settings.py` owns all user-file paths, profile, roster and switches.
- Generalized: PDF prefix per course (`pdf_prefix`), answer-key words/label from profile, Chrome lookup cross-platform, `local_project` absolute/~/relative-to-projects_root.
- New: timezone-offset warning from profile; `SetupError` -> "type /setup" hint instead of tracebacks.
- Guards: secret guard copied; new `guard_approvals.py` protects `canvas-config.json` AND `*.approved` stamps (closes stamp-forging gap); deny rules in `.claude/settings.json`.
- Generic `canvas-post` skill, README, CLAUDE.md, templates, examples/plan-basic, ARCHITECTURE, module record, ADR-0001.

## Files Changed

- canvas_export/{__init__,__main__,settings,cli,plan,pdf}.py; bin/canvas-export, bin/+a
- tests/test_{cli,plan,uploads,pdf}.py; .claude/hooks/tests/test_{block_env_read,guard_approvals}.py
- .claude/settings.json, .claude/hooks/{block_env_read,guard_approvals}.py, .claude/skills/canvas-post/SKILL.md
- README.md, CLAUDE.md, .gitignore, templates/*.example.json, examples/plan-basic/
- docs/ops/ARCHITECTURE.md, modules/harness.md, decisions/ADR-0001-self-contained-repo-local-data.md

## Verification Evidence

### Commands Run

```text
python3 -m unittest discover -s tests                 -> Ran 74 tests, OK
python3 -m unittest discover -s .claude/hooks/tests   -> Ran 15 tests, OK (1 skipped: shell wrapper not shipped)
personal-data grep over all non-ignored files          -> clean
bin/canvas-export check (no local/)                    -> rc 2, "missing ... bin/+a ... type /setup"
local/ from templates + preview examples/plan-basic    -> previews @chem; wrong offset warns "doesn't match America/Chicago"
git status --ignored                                    -> local/ ignored, nothing from local/ untracked
```

### Results

- All Stage 1 acceptance criteria verified locally. Not exercised against a live Canvas instance. Test local/ removed afterwards.

## Decisions

- ADR-0001: self-contained repo + local/ data layout.

## Dependency Changes

- None.

## Risks / Blockers

- None.

## Human Decision Needed

- License choice (before Stage 4).

## Handoff

### Outcome
Stage 1 scaffold built and verified offline.

### Current State
ready_for_review; nothing committed yet (repo initialized, no commits).

### Next Action
Owner reviews; then first commit, Stage 2 (CLI-enforced switch lock), Stage 3 (`/setup` skill).
