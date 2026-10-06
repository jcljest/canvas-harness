# canvas-harness: notes for Claude

- If `local/courses.json` doesn't exist, the user hasn't set up yet. Suggest `/setup`.
  `bin/canvas-harness doctor` shows what's done and what's next.
- **Deleting:** the delete guard asks the user before any delete. Don't try to
  work around it (no `mv` to the trash, no truncating files instead).
- Talk to Canvas only through `bin/canvas-harness`. For any posting or editing,
  follow the `canvas-post` skill and address courses by alias (`@name`) from
  `local/courses.json`.
- **Secrets:** never read, search, print or source `.env` (repo root), and never
  print environment variables. `.env.example` is the readable template. If a variable is missing, ask the user
  to run `bin/+a NAME` in their own terminal.
- **User-only files:** never create, edit or work around `local/canvas-config.json`
  or any `*.approved` file. Read switches with `bin/canvas-harness config`.
- **Approval:** `approve` is typed by the user in their own terminal. Never
  approve on their behalf. If their `auto_approve` is on, `apply` approves
  unflagged plans itself.
- **Generic code:** code, templates, skills and docs must not contain any one
  user's names, school, course ids or paths. Personal data belongs only in `local/`.
  The exception is author credit: keep "Jeffrey Lai" in `LICENSE`, `NOTICE.md` and the README's License section.
- Run both test suites after changes (see README → Tests).
- Design records live in `docs/ops/` (architecture, module, sprints, ADRs).
