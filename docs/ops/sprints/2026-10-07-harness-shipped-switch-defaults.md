---
id: 2026-10-07-harness-shipped-switch-defaults
module: harness
status: blocked
health: yellow
owner_session: null
worktree: /Users/laij/Projects/canvas-harness
started: 2026-10-07
updated: 2026-10-07
base_commit: 80c52771cf20b611b7e03f3e48c4adae80b46896
depends_on: []
blocks: []
---

# Shipped switch defaults with a per-user override

## Objective

The repo ships the switch values the maintainer recommends for new users, in a
tracked `canvas-config.json` at the repo root. A user's
`local/canvas-config.json`, if present, overrides it key by key.

## Why This Matters

The owner: canvas-harness is not specific to one computer; its settings should
be what is best for people who first work with the harness. Until now the only
defaults lived in code (`DEFAULT_SWITCHES`), and `local/` is gitignored.

## Scope

- `settings.load_switches()`: layer code fallback -> shipped root file -> local file.
- `config` command and `doctor` show which files were used.
- Docs: README, CLAUDE.md, setup and canvas-post skills, plan.py docstring,
  ARCHITECTURE, module record; ADR-0005.
- Tests for the layering.

## Non-goals

- Weakening the approval guard. The root `canvas-config.json` stays Claude-proof
  (the guard pattern already matches it); the owner creates and edits it.
- Changing code fallback values (stay false/true/false if no file exists).
- Committing anything (owner commits; uncommitted setup/doctor/.gitignore edits
  from another session are present and not ours).

## Acceptance Criteria

- [x] With only the root file, `load_switches()` returns its values.
- [x] A local file overrides only the keys it sets.
- [x] With neither file, code fallback (false/true/false) applies.
- [x] Bad values in either file fail closed (SetupError naming the file).
- [ ] `canvas-harness config` and `doctor` show the sources (no-file case checked; shipped-file case pending).
- [ ] Root `canvas-config.json` exists with all three switches true (owner creates it).
- [x] Both test suites pass (before root file exists).
- [x] ADR-0005 recorded.

## Plan

1. Code + tests. 2. Docs + ADR. 3. Owner creates root file. 4. Run suites.

## Progress / Checkpoints

### 2026-10-07
- Owner chose: shipped root file + local override; defaults auto_approve,
  auto_preview, auto_publish all true.
- Layering, config/doctor output, tests, docs, ADR-0005 done. Blocked on the
  owner creating root `canvas-config.json` (approval guard blocks Claude, by design).

## Files Changed

- canvas_harness/settings.py, cli.py, doctor.py, plan.py (docstring)
- tests/test_plan.py (SwitchLayers)
- README.md, CLAUDE.md, .claude/skills/setup/SKILL.md (switch section), .claude/skills/canvas-post/SKILL.md
- docs/ops/ARCHITECTURE.md, modules/harness.md, decisions/ADR-0005
- Not ours (uncommitted from another session): .gitignore, the setup skill's secrets-file step, doctor.py secrets-file line

## Verification Evidence

### Commands Run

```text
python3 -m unittest discover -s tests              -> Ran 89 tests, OK
python3 -m unittest discover -s .claude/hooks/tests -> Ran 20 tests, OK (skipped=1)
bin/canvas-harness config -> files: none (safe defaults); false/true/false
```

### Results

- Layering verified by unit tests; live shipped-file check pending root file.

## Decisions

- [ADR-0005](../decisions/ADR-0005-shipped-switch-defaults.md)

## Dependency Changes

- None.

## Risks / Blockers

- New users get plans auto-approved and content auto-published from first use;
  flagged plans (deletes, answer keys) go out with alerts only (ADR-0004).

## Human Decision Needed

- None (approach and values chosen 2026-10-07).

## Handoff

### Outcome
(pending)

### Current State
blocked (waiting on the owner to create the root file)

### Next Action
Owner creates root canvas-config.json; rerun `config`, `doctor`, both suites; owner commits.
