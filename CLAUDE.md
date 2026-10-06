# canvas-export: notes for Claude

- If `local/courses.json` doesn't exist, the user hasn't set up yet. Suggest `/setup`.
- Talk to Canvas only through `bin/canvas-export`. For any posting or editing,
  follow the `canvas-post` skill and address courses by alias (`@name`) from
  `local/courses.json`.
- **Secrets:** never read, search, print or source the secrets file in `local/`,
  and never print environment variables. If a variable is missing, ask the user
  to run `bin/+a NAME` in their own terminal.
- **User-only files:** never create, edit or work around `local/canvas-config.json`
  or any `*.approved` file. Read switches with `bin/canvas-export config`.
- **Approval:** `approve` is typed by the user in their own terminal. Never
  approve on their behalf. If their `auto_approve` is on, `apply` approves
  unflagged plans itself.
- **Generic code:** code, templates, skills and docs must not contain any one
  user's names, school, course ids or paths. Personal data belongs only in `local/`.
- Run both test suites after changes (see README → Tests).
- Design records live in `docs/ops/` (architecture, module, sprints, ADRs).
