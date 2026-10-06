# canvas-export

Let Claude Code post to your Canvas courses safely. You review a preview of
every change before it is sent, and Claude never sees your API token.

## Quick start

1. Clone this repo and open the folder in Claude Code. When Claude Code asks
   whether to trust the project's settings, say yes. That turns on the safety
   hooks (see [Safety](#safety)).
2. Type `/setup`. Claude asks a few questions and writes your personal files
   into `local/`. You type your Canvas token yourself, in your own terminal.

> `/setup` is still being built. Until then, copy the files in `templates/`
> into `local/` (drop `.example` from each name), edit them, and add your
> secrets with `bin/+a`, as shown below.

## How posting works

```
plan.json  ->  preview  ->  approve (you)  ->  apply  ->  verify
```

- **plan**: a JSON file that says exactly what to send (see `examples/plan-basic/`).
- **preview**: `bin/canvas-export preview <plan>` writes an HTML page showing
  each item as students will see it, with warnings for anything risky:
  deletes, past dates, wrong timezone offsets, answer-key filenames,
  overwrites, announcements that post immediately.
- **approve**: `bin/canvas-export approve <plan>` runs only in a real terminal,
  so only you can approve. It records a fingerprint of the exact plan.
- **apply**: sends the plan once. It refuses if anything changed after approval.

## Your files (`local/`, never committed)

| file | what it holds | written by |
|---|---|---|
| secrets file | `CANVAS_BASE_URL`, `CANVAS_API_TOKEN`, `CANVAS_COURSE_IDS` | you, with `bin/+a NAME` |
| `courses.json` | short names (`@chem`), Canvas ids, exact titles, your local project folders | `/setup` |
| `profile.json` | timezone, PDF naming, default upload folder | `/setup` |
| `canvas-config.json` | your switches (below) | **you only** |
| `plans/`, `uploads/<alias>/` | plan files, files waiting to upload | you and Claude |

`bin/+a NAME` asks for the value at a hidden prompt, so it never shows on
screen, in shell history, or in Claude's view. `bin/+a -l` lists names only.

Set `CANVAS_EXPORT_LOCAL` to keep these files somewhere other than `local/`.

## Switches (`local/canvas-config.json`)

```json
{"auto_approve": false, "auto_preview": true, "auto_publish": false}
```

| switch | `true` | `false` (default unless noted) |
|---|---|---|
| `auto_approve` | `apply` approves a plan itself **when nothing is flagged**. Flagged plans still need your typed `approve`. | You always type `approve`. |
| `auto_preview` | The preview opens in your browser (default). | The preview file is written but not opened. |
| `auto_publish` | New assignments, pages, quizzes and discussions are created published. | They're created as unpublished drafts. |

A plan that sets `published` itself keeps that value. Changing a switch
cancels earlier approvals. `bin/canvas-export config` shows the current values.

## Safety

The project's `.claude/settings.json` turns on two hooks and some deny rules:

- **Secret guard** (`.claude/hooks/block_env_read.py`): Claude can't read,
  search, copy or print your secrets file or environment variables.
- **Approval guard** (`.claude/hooks/guard_approvals.py`): Claude can't edit
  `canvas-config.json` or any `*.approved` stamp, so it can't approve its own
  plans or switch on auto-approve.

These guards match patterns. They catch mistakes and common workarounds, but
they are not a sandbox. In the CLI itself:

- Requests can only reach the course ids in `CANVAS_COURSE_IDS`.
- The token never leaves the CLI process and is redacted from errors.
- Redirects to other hosts are refused.

A personal access token carries **all** of your Canvas permissions, so treat
it like a password and revoke it in Canvas if it ever leaks.

## Commands

```sh
bin/canvas-export check                  # test the connection (never prints the token)
bin/canvas-export discover               # list courses you teach, with ids
bin/canvas-export roster                 # check local/courses.json against Canvas
bin/canvas-export config                 # show your switches
bin/canvas-export preview|approve|apply <plan>
bin/canvas-export uploads                # files waiting in local/uploads/
bin/canvas-export pdf <file.html> --course @alias [--pages N]   # needs Chrome/Chromium
bin/canvas-export get @chem/assignments --all
```

## Requirements

- Python 3.9+ (standard library only)
- Claude Code
- Chrome or Chromium, only for `pdf` (override the path with `CANVAS_EXPORT_CHROME`)

## Tests

```sh
python3 -m unittest discover -s tests
python3 -m unittest discover -s .claude/hooks/tests
```
