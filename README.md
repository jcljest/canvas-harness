# canvas-harness

Let Claude Code post to your Canvas courses safely. You review a preview of
every change before it is sent, and Claude never sees your API token.

## Quick start

1. Clone this repo and open the folder in Claude Code. When Claude Code asks
   whether to trust the project's settings, say yes. That turns on the safety
   hooks (see [Safety](#safety)).
2. In your own terminal: `cp .env.example .env && chmod 600 .env`. Open `.env`
   in your editor and fill in `CANVAS_BASE_URL` and `CANVAS_API_TOKEN`
   (Canvas → Account → Settings → **+ New Access Token**). Never paste the token
   into a chat.
3. In Claude Code, type `/setup`. Claude checks your connection, lists your
   courses from Canvas, asks which to use and what to call them, and writes
   your settings. It then tells you which course ids to add to `.env` as
   `CANVAS_COURSE_IDS`. That list is the hard limit on what the tool can
   change, so only you edit it.

You can check progress at any time with `bin/canvas-harness doctor`. Run
`/setup` again later to add a course or start a new school year.

## How posting works

```
plan.json  ->  preview  ->  approve (you)  ->  apply  ->  verify
```

- **plan**: a JSON file that says exactly what to send (see `examples/plan-basic/`).
- **preview**: `bin/canvas-harness preview <plan>` writes an HTML page showing
  each item as students will see it, with warnings for anything risky:
  deletes, past dates, wrong timezone offsets, answer-key filenames,
  overwrites, announcements that post immediately.
- **approve**: `bin/canvas-harness approve <plan>` runs only in a real terminal,
  so only you can approve. It records a fingerprint of the exact plan.
- **apply**: sends the plan once. It refuses if anything changed after approval.

## Your files (never committed)

| file | what it holds | written by |
|---|---|---|
| `.env` (repo root) | `CANVAS_BASE_URL`, `CANVAS_API_TOKEN`, `CANVAS_COURSE_IDS` | **you only**, from `.env.example` |
| `local/courses.json` | short names (`@chem`), what you call each class (nicknames), Canvas ids, exact titles, your local project folders | `/setup` |
| `local/profile.json` | timezone, PDF naming, default upload folder | `/setup` |
| `local/canvas-config.json` | optional: your own switches, overriding the shipped ones (below) | **you only** |
| `local/plans/`, `local/uploads/<alias>/` | plan files, files waiting to upload | you and Claude |

Instead of editing `.env` by hand, you can run `bin/+a NAME` in your terminal.
It asks for the value at a hidden prompt, so it never shows on screen or in
shell history. `bin/+a -l` lists names only.

Set `CANVAS_HARNESS_ENV` to keep the secrets file elsewhere, and
`CANVAS_HARNESS_LOCAL` to move the `local/` folder.

## Switches

The repo ships recommended switches in `canvas-config.json` at the repo root:

```json
{"auto_approve": true, "auto_preview": true, "auto_publish": true}
```

To change any of them for yourself, create `local/canvas-config.json` with just
the keys you want different. It overrides the shipped file key by key and is
never committed:

```sh
mkdir -p local && echo '{"auto_approve": false}' > local/canvas-config.json
```

If neither file exists, the safe fallbacks apply: `auto_approve` false,
`auto_preview` true, `auto_publish` false.

| switch | `true` | `false` |
|---|---|---|
| `auto_approve` | `apply` approves **every** plan itself, with no check first. Anything that would have been flagged (deletes, past dates, answer-key filenames, overwrites, announcements that post immediately) is sent anyway and reported afterwards as an `ALERT` line and under `"alerts"` in `<plan>.result.json`. | You type `approve` for every plan. |
| `auto_preview` | The preview opens in your browser. | The preview file is written but not opened. |
| `auto_publish` | New assignments, pages, quizzes and discussions are created published. | They're created as unpublished drafts. |

A plan that sets `published` itself keeps that value. Changing a switch
cancels earlier approvals. `bin/canvas-harness config` shows the values in effect and which files set them.

## Safety

The project's `.claude/settings.json` turns on two hooks and some deny rules:

- **Secret guard** (`.claude/hooks/block_env_read.py`): Claude can't read,
  search, copy or print your secrets file or environment variables.
- **Approval guard** (`.claude/hooks/guard_approvals.py`): Claude can't edit
  either `canvas-config.json` or any `*.approved` stamp, so it can't approve its own
  plans or switch on auto-approve.
- **Delete guard** (`.claude/hooks/guard_deletes.py`): Claude must ask you
  before deleting anything (`rm`, `find -delete`, `git clean`, code that
  deletes). Catastrophic deletes are always blocked, such as `rm -rf` of `/`, `~`,
  `..`, `.git`, `local/`, the whole project or anything outside it, and
  `git clean -x`, which would wipe `.env` and `local/`.

These guards match patterns. They catch mistakes and common workarounds, but
they are not a sandbox. In the CLI itself:

- Requests can only reach the course ids in `CANVAS_COURSE_IDS`.
- The token never leaves the CLI process and is redacted from errors.
- Redirects to other hosts are refused.

A personal access token carries **all** of your Canvas permissions, so treat
it like a password and revoke it in Canvas if it ever leaks.

## Commands

```sh
bin/canvas-harness doctor                 # setup checklist: what's done, what's next
bin/canvas-harness check                  # test the connection (never prints the token)
bin/canvas-harness discover               # list courses you teach, with ids
bin/canvas-harness roster                 # check local/courses.json against Canvas
bin/canvas-harness which "AP Physics"     # which course a name or nickname means
bin/canvas-harness config                 # show your switches
bin/canvas-harness preview|approve|apply <plan>
bin/canvas-harness uploads                # files waiting in local/uploads/
bin/canvas-harness pdf <file.html> --course @alias [--pages N]   # needs Chrome/Chromium
bin/canvas-harness get @chem/assignments --all
bin/canvas-harness get /api/quiz/v1/@chem/quizzes   # New Quizzes API (same course allowlist)
```

## Requirements

- Python 3.9+ (standard library only)
- Claude Code
- Chrome or Chromium, only for `pdf` (override the path with `CANVAS_HARNESS_CHROME`)

## Tests

```sh
python3 -m unittest discover -s tests
python3 -m unittest discover -s .claude/hooks/tests
```

## License

MIT © Jeffrey Lai. Use it, change it and share it. Just keep the copyright
notice. See [LICENSE](LICENSE), and [NOTICE.md](NOTICE.md) for
acknowledgments of the software and services this tool works with.
