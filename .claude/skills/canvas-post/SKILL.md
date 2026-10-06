---
name: canvas-post
description: Post or update content in the user's Canvas courses (assignments, pages, announcements, modules, due dates, file uploads) through the canvas-harness CLI, making sure it goes to the CORRECT course. Use whenever the user asks to post, push, publish, upload, create, or edit anything in Canvas, or names one of their courses together with Canvas.
---

# canvas-post

Everything personal is gitignored: the secrets file at the repo root, and the `local/` folder.

| file | what it is | who writes it |
|---|---|---|
| `local/courses.json` | aliases, nicknames, Canvas ids, exact titles, project folders | `/setup` (Claude) |
| `local/profile.json` | timezone, PDF naming, default upload folder | `/setup` (Claude) |
| `local/canvas-config.json` | `auto_approve`, `auto_preview`, `auto_publish` | **the user only** |
| `.env` at the repo root | school URL, token, allowed course ids | **the user only** |

The command is `bin/canvas-harness` from the repo root (or `canvas-harness` if
`/setup` put it on PATH). If `local/courses.json` is missing, stop and suggest `/setup`.

## Never

- Read, print or search the secrets file, or print the token. If a variable is
  missing, ask the user to run `bin/+a NAME` in their own terminal (it needs a real
  terminal for the hidden prompt).
- Create, edit or work around `canvas-config.json` or any `*.approved` file.
  Don't suggest turning `auto_approve` on to get past the typed approval.
- Use bare `post`/`put`/`delete` for changes. Every change goes through a plan.

## Procedure

1. **Verify the roster.** Run `canvas-harness roster`. It must exit 0. On a
   MISMATCH or missing alias, stop and tell the user.
2. **Pick the course.** Never guess between courses.
   - If the user names a class in any form ("AP", "my physics class", "3rd period"),
     run `canvas-harness which "<their words>"`. Exit 0 means use that course.
     Exit 1 means ask which course they mean, showing the `maybe` lines. Once
     they answer, offer to save their words as a nickname for that course in
     `local/courses.json`, then run `which` again to confirm.
   - If they don't name one, and the material is a file under a course's
     `local_project`, use that course and say so.
   - Otherwise, ask. Handle several courses one at a time and say which is which.
3. **Write a plan** at `local/plans/<alias>/<YYYY-MM-DD>-<slug>/plan.json`.
   Keep long HTML in a sibling file referenced from `files`. The format is in
   the `canvas_harness/plan.py` docstring and `examples/plan-basic/`.
   Read-only lookups (for example, finding a module id) can use `canvas-harness get`.
4. **Preview.** Run `canvas-harness preview <plan>`. Relay the summary, every
   `!` warning and the `approval:` line, and give the preview file path.
5. **Approval.**
   - `approval: AUTO` means the user turned on auto_approve. Continue to
     step 6, even if warnings are listed: they become alerts after the run.
   - Otherwise, ask the user to run `bin/canvas-harness approve <plan>` in their
     own terminal (it needs a real terminal). You cannot approve for them.
   - Any edit to the plan or its files cancels approval. Preview again.
6. **Apply.** Run `canvas-harness apply <plan>`. If the output has `ALERT`
   lines (also under `"alerts"` in `<plan>.result.json`), tell the user each one
   plainly: it already happened. A plan runs once. If a step
   fails, `<plan>.result.json` records what was sent. Tell the user and make a
   new plan for the remaining steps. Never re-run the old one.
7. **Verify.** GET each created or updated item back and report its `html_url`
   and the course it landed in.

## Defaults

- **Publishing:** leave `published` out of new assignments, pages, quizzes and
  discussions. The user's `auto_publish` switch fills it in. Set it only when
  the user asks for a specific item to be hidden or published. If it ends up
  true and you add the item to a module, also add a step that publishes the
  module item.
- **Dates:** ISO 8601 with an explicit UTC offset for the user's timezone in
  `local/profile.json`, on that date (daylight time changes the offset). The
  preview warns if an offset doesn't match. If the user gives only a date, ask
  for the time, or use 11:59 PM and say so.
- **HTML bodies:** keep them in separate files referenced from `files`.
- **Referring to earlier steps:** use `"content_id": "{{1.id}}"`.

## Files and PDFs

- Uploads come from `local/uploads/<alias>/`. Run `canvas-harness uploads` to
  see what's waiting. A file there can only go to that course.
- To render course HTML to PDF: `canvas-harness pdf <file.html> --course @<alias> --pages <N>`.
  The course comes from which `local_project` folder holds the file. If it
  refuses, report why and stop. Ask before passing `--overwrite`.
- Upload step: `{"course": "@alias", "upload": "<file>", "folder": "Assignments/<name>"}`.
  To attach the file, link it from a later step's HTML:
  `<a class="instructure_file_link instructure_scribd_file" href="{{N.course_file_url}}">Title (PDF)</a>`
- **Answer keys** (names matching the profile's `answer_key_words`): never put
  one in a student-facing item. Ask the user what to do with it.
- Use `"on_duplicate": "overwrite"` only when the user is replacing a file.

## Common plan steps

```json
{"course": "@chem", "method": "POST", "path": "assignments",
 "body": {"assignment": {"name": "...", "points_possible": 10, "submission_types": ["online_upload"],
                         "due_at": "2030-10-02T23:59:00-05:00"}},
 "files": {"assignment.description": "description.html"}}

{"course": "@chem", "method": "PUT", "path": "assignments/<assignment_id>",
 "body": {"assignment": {"due_at": "2030-10-05T23:59:00-05:00"}}}

{"course": "@chem", "method": "POST", "path": "pages",
 "body": {"wiki_page": {"title": "..."}}, "files": {"wiki_page.body": "page.html"}}

{"course": "@chem", "method": "POST", "path": "discussion_topics",
 "body": {"title": "...", "is_announcement": true, "delayed_post_at": "2030-10-01T07:30:00-05:00"},
 "files": {"message": "announcement.html"}}

{"course": "@chem", "method": "POST", "path": "modules/<module_id>/items",
 "body": {"module_item": {"type": "Assignment", "content_id": "{{1.id}}"}}}

{"course": "@chem", "method": "PUT", "path": "modules/<module_id>/items/{{2.id}}",
 "body": {"module_item": {"published": true}}}
```
