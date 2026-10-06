---
name: setup
description: First-time setup (or changes to setup) for canvas-harness. Interviews the user, checks their Canvas connection, finds their courses through the Canvas API, and writes their personal files in local/. Use when the user types /setup, says they just cloned the repo, wants to add/remove a course, starts a new school year, or when `bin/canvas-harness doctor` shows TODO lines.
---

# /setup

Goal: from a fresh clone to `bin/canvas-harness doctor` saying **All set.**, by
asking the user short questions and doing everything else yourself.

## Ground rules

- **Never ask for, read, print or write secret values.** The user edits the
  `.env` file themselves in their own editor. You may say which line to add,
  never what the token is. If a secret ever shows up in your context, stop and
  tell the user to revoke that token in Canvas.
- You can't create, edit or copy the `.env` file, `local/canvas-config.json` or any
  `*.approved` file. The guards will block you. Tell the user the exact
  command or edit instead.
- Ask with the AskUserQuestion tool when there are 2–4 clear choices.
  Otherwise ask in plain text. Ask one topic at a time.
- After each step, run `bin/canvas-harness doctor` (add `--offline` before the
  connection works) and continue from the first TODO line. Doctor never prints
  secrets.
- Keep the user oriented: one line on what's done and what's next.

## 0. Start

Run `bin/canvas-harness doctor --offline`.

- If `local/courses.json` already exists, this is a **re-run**. Ask what to change:
  add a course, remove a course, new school year (replace courses),
  change profile settings, or just check everything. Do only that part, then
  finish with step 8.
- Otherwise, tell the user there are about 8 short steps, and that they'll edit
  one file (the `.env` file) by hand, twice.

## 1. Check that the safety hooks are on

Run `touch /tmp/canvas-harness-hook-probe.approved`.

- **Blocked by the approval guard:** hooks are on. Continue.
- **It succeeded:** the project's hooks aren't running, so the guards that keep
  the token away from Claude are off. Stop. Tell the user to quit Claude Code,
  reopen it in this folder, and accept the project's settings when asked (or
  check `/hooks`). Then run `/setup` again. Don't continue without hooks.

## 2. Canvas address and token (the user's first edit)

If doctor shows TODO for the secrets file, `CANVAS_BASE_URL` or `CANVAS_API_TOKEN`,
explain:

1. In their own terminal, from this folder: `cp .env.example .env`, then
   `chmod 600 .env`.
2. Open the `.env` file in their editor and fill in:
   - `CANVAS_BASE_URL`: the address they log in to Canvas at, like
     `https://theirschool.instructure.com`.
   - `CANVAS_API_TOKEN`: in Canvas, go to **Account → Settings → + New Access
     Token**. Purpose: "canvas-harness". An expiry date at the end of the term is
     a good habit. Copy the token into the file, never into this chat.
   - Leave `CANVAS_COURSE_IDS` empty for now.
3. Save, then say "done".

`bin/+a NAME` (hidden prompt, in their own terminal) works too, if they prefer.

Then run `bin/canvas-harness doctor`. The connection line must say
"token works for <name>". If not, explain the error in plain words: a 401 means
the token was mistyped or expired; a network error means the URL is wrong.
Have them fix it and check again.

## 3. Find their courses through the Canvas API

Run `bin/canvas-harness discover --json` and keep the data, and
`bin/canvas-harness discover` to show the user the table.

- Ask which courses they want to post to. With 4 or fewer courses, use
  AskUserQuestion (multiSelect). With more, list them numbered and ask for numbers.
- If an expected course is missing, offer `discover --any-role` (for example,
  when they're a TA or designer rather than a teacher).

## 4. Name each course

For each chosen course, ask (a few at a time, not all at once):

- **Short name (alias):** used as `@alias` when posting. Suggest one from the
  course code, short and lowercase, letters, digits and `_` only (e.g. `chem`, `bio2`).
  Aliases must be unique.
- **Local project folder (optional):** where they keep this course's
  materials on this computer. It lets Claude pick the course from where a file
  lives, and makes `pdf` work. Check that it exists with `ls`. They can skip it.
- **PDF name prefix (optional):** default is the alias in capitals.

Show a summary table and get a yes before writing.

## 5. Write the roster, then the user allows those courses (second edit)

Write `local/courses.json`. Copy `id` and `name` exactly from the
`discover --json` data, never retyped:

```json
{"courses": [{"alias": "chem", "id": 1001, "name": "<exact Canvas title>",
              "local_project": "~/Projects/chemistry", "pdf_prefix": "CHEM"}]}
```

Leave out `local_project` and `pdf_prefix` when not given. Then tell the user
to set this line in the `.env` file (you give the ids, they type them):

```
CANVAS_COURSE_IDS=1001,1002
```

Explain why: this list is the hard limit on which courses the tool can
change, so only they control it. When they say "done", run
`bin/canvas-harness roster`. It must exit 0 with every course `allowed=yes` and `ok`.

## 6. Profile

Suggest their timezone from the system (`readlink /etc/localtime` on macOS or
Linux) and confirm it, as an IANA name like `America/Chicago`. Then ask, offering
the defaults:

- the label for answer-key PDFs (default `ANS`),
- the words that mark a file as an answer key (show the defaults from
  `templates/profile.example.json`; most people keep them),
- the default Canvas Files folder for uploads (default `Uploads`).

Write `local/profile.json` with only the keys from
`templates/profile.example.json`.

## 7. Switches (explain only)

Explain the three switches and their safe defaults (see README → Switches):
`auto_approve` false, `auto_preview` true, `auto_publish` false. No file is
needed for the defaults. If they want different values, they run this in their
own terminal and then edit the file:

```
mkdir -p local && cp templates/canvas-config.example.json local/canvas-config.json
```

You can't create or edit that file, by design. Confirm the result with
`bin/canvas-harness config`.

## 8. Optional conveniences, then a dry run

Ask (AskUserQuestion, multiSelect) whether they want:

- the `canvas-harness` command available everywhere:
  `mkdir -p ~/.local/bin && ln -s "$PWD/bin/canvas-harness" ~/.local/bin/canvas-harness`
  (and `bin/+a` likewise). Check that `~/.local/bin` is on their PATH.
- the `canvas-post` skill available in all their Claude Code projects (so they
  can post from a course folder):
  `mkdir -p ~/.claude/skills && ln -s "$PWD/.claude/skills/canvas-post" ~/.claude/skills/canvas-post`.

Dry run: copy `examples/plan-basic/` to `local/plans/<alias>/setup-check/`
for their first course, change `@chem` to `@<alias>`, change the date's offset to their
timezone, and run `bin/canvas-harness preview <plan>`. Point out the
summary, the warnings and the `approval:` line. **Don't approve or apply it.**
It's only a check.

Finish with `bin/canvas-harness doctor`. It should say **All set.** Then give a
short recap: their courses and aliases, where their files live, how to post
("ask Claude to post X to @alias"), and that they approve in their own terminal
with `bin/canvas-harness approve <plan>`.
