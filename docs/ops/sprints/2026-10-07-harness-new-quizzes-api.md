---
id: 2026-10-07-harness-new-quizzes-api
module: harness
status: ready_for_review
health: green
owner_session: null
worktree: /Users/laij/Projects/canvas-harness
started: 2026-10-07
updated: 2026-10-07
base_commit: 80c52771cf20b611b7e03f3e48c4adae80b46896
depends_on: []
blocks: []
---

# Allow the New Quizzes API

## Objective

The harness can read and write New Quizzes, which Instructure serves under
`/api/quiz/v1/courses/<id>/...` on the same Canvas host, with the same
course-id allowlist as the classic `/api/v1/courses/<id>/...` API.

## Why This Matters

The owner wants to manage New Quizzes from the harness. Before this, the scope
guard refused every path outside `/api/v1/`, and `normalize_path` rewrote
`/api/quiz/v1/...` into `/api/v1/api/quiz/v1/...`.

## Scope

- `cli.py`: scope guard and path normalization accept `/api/quiz/v1/courses/<id>/...`
  for allowlisted ids only; `@alias` shorthand works after the `/api/quiz/v1/` prefix.
- `plan.py`: optional `"api": "quiz"` on a request step sends it to the New Quizzes API;
  preview and approval digest include it.
- `PATCH` added to CLI subcommands and plan methods (New Quizzes updates use PATCH).
- Tests and docs (README, canvas-post skill, module record).

## Non-goals

- Any other host or API family (e.g. `/api/lti`, `/api/graphql`), or any global
  (non-course) New Quizzes route.
- `auto_publish` for New Quizzes (they have no `published` field; publishing goes
  through the quiz's assignment). Skipped for `api: quiz` steps.
- Committing (owner commits; other uncommitted edits in the tree are from
  sprint 2026-10-07-harness-shipped-switch-defaults).

## Acceptance Criteria

- [x] `check_scope` allows `/api/quiz/v1/courses/<allowed id>/...` and refuses other ids and non-course quiz paths.
- [x] `normalize_path` keeps `/api/quiz/v1/...` (and a full URL on base) intact.
- [x] `expand_alias("/api/quiz/v1/@chem/quizzes")` -> `/api/quiz/v1/courses/<id>/quizzes`.
- [x] A plan step with `"api": "quiz"` is sent to `/api/quiz/v1/courses/<id>/<path>`; bad `api` values are rejected.
- [x] Both test suites pass.
- [ ] Live check against Canvas: `get /api/quiz/v1/@<alias>/quizzes` returns the course's New Quizzes (needs the owner's credentials).

## Progress / Checkpoints

- 2026-10-07: sprint opened.
- 2026-10-07: implemented. `cli.py` (API_PREFIXES, COURSE_PATH, expand_alias, PATCH),
  `plan.py` (APIS, step `api`, PATCH; `api` stored only when not v1 so existing
  approvals keep their digest), README, canvas-post skill, module invariant.
  Evidence: `python3 -m unittest discover -s tests` -> Ran 91, OK;
  `python3 -m unittest discover -s .claude/hooks/tests` -> Ran 20, OK (skipped=1).
  Not yet run against a live Canvas (no credentials in this session).
