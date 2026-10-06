"""Plan files: preview -> owner approval -> apply.

A plan is a JSON file that says exactly what to send to Canvas:

    {
      "title": "Lab 3 for AP Physics 2",
      "steps": [
        {
          "course": "@chem",
          "method": "POST",
          "path": "assignments",
          "note": "Create the lab assignment",
          "body": {"assignment": {"name": "Lab 3", "points_possible": 10,
                                  "due_at": "2026-10-02T23:59:00-04:00", "published": false}},
          "files": {"assignment.description": "lab3.html"}
        },
        {
          "course": "@chem",
          "method": "POST",
          "path": "modules/55/items",
          "body": {"module_item": {"type": "Assignment", "content_id": "{{1.id}}"}}
        }
      ]
    }

`files` fills a dotted key in `body` with the contents of a file (relative to
the plan). "{{N.field}}" is replaced at apply time with `field` from step N's
response (1-based): a string that is exactly a placeholder becomes the raw value
(e.g. an int id); placeholders inside longer strings (HTML) are replaced as text.

An upload step sends a file from the course's landing folder
(local/uploads/<alias>/) to that course's Files:

    {"course": "@chem", "upload": "lab3.pdf", "folder": "Assignments/Lab 3",
     "on_duplicate": "rename"}

Its result adds `course_file_url` (/courses/<id>/files/<file id>) so a later
step's HTML can link the file:
    <a class="instructure_file_link instructure_scribd_file" href="{{1.course_file_url}}">Lab 3 (PDF)</a>

`approve` needs a person typing at the terminal. It records a sha256 of the
fully resolved plan (including file contents) in `<plan>.approved`. `apply`
refuses if that hash no longer matches, or if the plan was already applied.

local/canvas-config.json (user-edited; missing = safe defaults) holds three switches:
    {"auto_approve": false, "auto_preview": true, "auto_publish": false}
auto_approve lets `apply` approve a plan itself when it has no blocking
warnings (every warning except "will be PUBLISHED"); anything flagged still
needs the typed `approve`. auto_preview opens the preview in a browser.
auto_publish fills in `published` on new assignments, pages, quizzes and
(non-announcement) discussions that don't set it; an explicit value wins.
"""

import hashlib
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import settings as st
from .settings import SetupError

METHODS = {"POST", "PUT", "DELETE"}
PLACEHOLDER = re.compile(r"^\{\{(\d+)\.([A-Za-z0-9_]+)\}\}$")
INLINE = re.compile(r"\{\{(\d+)\.([A-Za-z0-9_]+)\}\}")
UPLOAD_EXTS = {".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg", ".gif", ".txt", ".csv"}
ON_DUPLICATE = {"rename", "overwrite"}
DATE_KEYS = {"due_at", "unlock_at", "lock_at", "delayed_post_at", "todo_date", "posted_at"}
SUMMARY_KEYS = ("name", "title", "points_possible", "grading_type", "submission_types", "due_at",
                "unlock_at", "lock_at", "delayed_post_at", "is_announcement", "published", "type",
                "content_id", "position", "assignment_group_id")
HTML_KEYS = ("description", "body", "message")
# POST path -> key holding the new item's fields (None = top level of the body)
PUBLISHABLE = {"assignments": "assignment", "pages": "wiki_page", "quizzes": "quiz", "discussion_topics": None}
PUBLISHED_WARNING = "will be PUBLISHED (visible to students)"


class PlanError(Exception):
    pass


def answer_key_re(profile):
    words = "|".join(re.escape(w) for w in profile["answer_key_words"]) or "(?!)"
    return re.compile(rf"(^|[-_ .])({words})([-_ .]|$)", re.I)


def _set_dotted(obj, dotted, value):
    keys = dotted.split(".")
    for k in keys[:-1]:
        obj = obj.setdefault(k, {})
        if not isinstance(obj, dict):
            raise PlanError(f"files key {dotted!r}: {k!r} is not an object")
    obj[keys[-1]] = value


def _upload_step(n, step, alias, course, uploads_root, profile):
    where = f"step {n}"
    root = (Path(uploads_root) / alias[1:]).resolve()
    f = (root / str(step["upload"])).resolve()
    if root not in f.parents:
        raise PlanError(f"{where}: upload must be a file inside {root}/")
    if not f.is_file():
        raise PlanError(f"{where}: no such file in the landing folder: {step['upload']}")
    if f.suffix.lower() not in UPLOAD_EXTS:
        raise PlanError(f"{where}: {f.suffix or 'no extension'} not allowed; allowed: {' '.join(sorted(UPLOAD_EXTS))}")
    folder = str(step.get("folder", profile["default_upload_folder"])).strip("/") or "/"  # "/" = top level of course files
    if ".." in folder.split("/"):
        raise PlanError(f"{where}: folder must be a Canvas folder path like 'Assignments/Lab 3', or '/'")
    on_dup = step.get("on_duplicate", "rename")
    if on_dup not in ON_DUPLICATE:
        raise PlanError(f"{where}: on_duplicate must be one of {sorted(ON_DUPLICATE)}")
    data = f.read_bytes()
    return {"n": n, "kind": "upload", "course": alias, "course_id": course["id"],
            "course_name": course["name"], "file": str(f.relative_to(root)), "abs": str(f),
            "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "folder": folder,
            "on_duplicate": on_dup, "note": step.get("note", "")}


def _apply_auto_publish(method, rel, body, auto_publish):
    if method != "POST" or rel not in PUBLISHABLE:
        return
    key = PUBLISHABLE[rel]
    target = body.setdefault(key, {}) if key else body
    if not isinstance(target, dict) or (key is None and target.get("is_announcement")):
        return
    target.setdefault("published", auto_publish)


def load_plan(path, roster, uploads_root=None, settings=None):
    """Parse, validate and resolve file references. Returns (plan, digest)."""
    settings = {**st.DEFAULT_SWITCHES, **(settings or st.load_switches())}
    profile = st.load_profile()
    path = Path(path).resolve()
    try:
        plan = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise PlanError(f"cannot read plan {path}: {e}")
    if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list) or not plan["steps"]:
        raise PlanError("plan must be an object with a non-empty 'steps' list")
    steps = []
    for n, step in enumerate(plan["steps"], 1):
        where = f"step {n}"
        alias = str(step.get("course", ""))
        if not alias.startswith("@") or alias[1:] not in roster:
            known = ", ".join("@" + a for a in sorted(roster))
            raise PlanError(f"{where}: course must be a roster alias ({known}), got {alias!r}")
        if "upload" in step:
            steps.append(_upload_step(n, step, alias, roster[alias[1:]], uploads_root or st.uploads_root(), profile))
            continue
        method = str(step.get("method", "")).upper()
        if method not in METHODS:
            raise PlanError(f"{where}: method must be one of {sorted(METHODS)}")
        rel = str(step.get("path", "")).strip("/")
        if not rel or rel.startswith(("courses", "api", "http")) or ".." in rel.split("/"):
            raise PlanError(f"{where}: path must be relative to the course, e.g. 'assignments'")
        body = json.loads(json.dumps(step.get("body") or {}))
        for dotted, fname in (step.get("files") or {}).items():
            fpath = (path.parent / fname).resolve()
            try:
                _set_dotted(body, dotted, fpath.read_text())
            except OSError as e:
                raise PlanError(f"{where}: cannot read {fname}: {e}")
        _apply_auto_publish(method, rel, body, settings["auto_publish"])
        for m in list(_placeholders(body)) + list(INLINE.finditer(rel)):
            if int(m.group(1)) >= n:
                raise PlanError(f"{where}: {m.group(0)} must refer to an earlier step")
        course = roster[alias[1:]]
        steps.append({"n": n, "kind": "request", "course": alias, "course_id": course["id"], "course_name": course["name"],
                      "method": method, "path": rel, "note": step.get("note", ""), "body": body})
    resolved = {"title": plan.get("title", path.stem), "steps": steps}
    digest = hashlib.sha256(json.dumps(resolved, sort_keys=True).encode()).hexdigest()
    return resolved, digest


def _placeholders(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _placeholders(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _placeholders(v)
    elif isinstance(obj, str):
        yield from INLINE.finditer(obj)


def substitute(obj, results):
    if isinstance(obj, dict):
        return {k: substitute(v, results) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute(v, results) for v in obj]
    if isinstance(obj, str):
        def lookup(m):
            got = (results.get(int(m.group(1))) or {}).get(m.group(2))
            if got is None:
                raise PlanError(f"{m.group(0)}: step {m.group(1)} result has no {m.group(2)!r}")
            return got
        m = PLACEHOLDER.match(obj)
        if m:
            return lookup(m)
        return INLINE.sub(lambda m: str(lookup(m)), obj)
    return obj


def _parse_date(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def _inner(body):
    """Canvas bodies are usually {"assignment": {...}}; summarize the inner object."""
    if len(body) == 1 and isinstance(next(iter(body.values())), dict):
        return next(iter(body.values()))
    return body


def warnings_for(step, now=None, profile=None):
    profile = profile or st.load_profile()
    if step.get("kind") == "upload":
        out = []
        if answer_key_re(profile).search(Path(step["file"]).stem):
            out.append("filename looks like an ANSWER KEY; files in course Files can be visible to students")
        if step["on_duplicate"] == "overwrite":
            out.append("OVERWRITES a same-named file in that Canvas folder")
        if step["size"] > 100 * 1024 * 1024:
            out.append("file is larger than 100 MB")
        return out
    now = now or datetime.now(timezone.utc)
    inner, out = _inner(step["body"]), []
    if step["method"] == "DELETE":
        out.append("DELETES an item")
    if inner.get("published") is True:
        out.append("will be PUBLISHED (visible to students)")
    if inner.get("is_announcement") and not inner.get("delayed_post_at"):
        out.append("announcement posts IMMEDIATELY")
    for k in DATE_KEYS & set(inner):
        d = _parse_date(inner[k])
        if d is None:
            out.append(f"{k} is not a valid ISO date: {inner[k]!r}")
        elif d.tzinfo is None:
            out.append(f"{k} has no timezone offset (Canvas will assume UTC)")
        elif d < now:
            out.append(f"{k} is in the past")
        elif profile["timezone"]:
            from zoneinfo import ZoneInfo
            local = d.astimezone(ZoneInfo(profile["timezone"]))
            if local.utcoffset() != d.utcoffset():
                out.append(f"{k} offset {d.strftime('%z')} doesn't match {profile['timezone']} on that date "
                           f"({local.strftime('%z')}); it is {local.strftime('%-I:%M %p')} local time")
    return out


def blocking_warnings(plan):
    """Warnings that keep a plan from being auto-approved, as 'step N: text'."""
    return [f"step {st['n']}: {w}" for st in plan["steps"] for w in warnings_for(st)
            if w != PUBLISHED_WARNING]


def approval_line(plan, settings):
    if not settings["auto_approve"]:
        return "approval: you type `canvas-harness approve <plan>` (auto_approve is off)"
    blocking = blocking_warnings(plan)
    if not blocking:
        return "approval: AUTO (auto_approve is on and nothing is flagged); `apply` will send it"
    return "approval: you type `canvas-harness approve <plan>` (auto_approve is on, but flagged: " + "; ".join(blocking) + ")"


def _fmt(key, value):
    if key in DATE_KEYS:
        d = _parse_date(value)
        if d and d.tzinfo:
            return d.strftime("%a %b %-d, %Y %-I:%M %p ") + d.strftime("(UTC%z)")
    return json.dumps(value) if not isinstance(value, str) else value


def _size(n):
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def _upload_card(s):
    e = html.escape
    warns = "".join(f"<li>{e(w)}</li>" for w in warnings_for(s))
    uri = Path(s["abs"]).as_uri()
    embed = (f'<embed src="{e(uri)}" type="application/pdf" class="pdf">'
             if s["file"].lower().endswith(".pdf") else "")
    return f"""
<section class="card">
  <div class="course">{e(s['course_name'])} <span class="alias">{e(s['course'])} · id {s['course_id']}</span></div>
  <h2>Step {s['n']}: upload {e(s['file'])}</h2>
  {f'<p class="note">{e(s["note"])}</p>' if s['note'] else ''}
  {f'<ul class="warn">{warns}</ul>' if warns else ''}
  <table>
    <tr><th>local file</th><td><a href="{e(uri)}">{e(s['abs'])}</a></td></tr>
    <tr><th>size</th><td>{_size(s['size'])}</td></tr>
    <tr><th>sha256</th><td>{s['sha256'][:16]}…</td></tr>
    <tr><th>Canvas folder</th><td>Files / {e('(top level)' if s['folder'] == '/' else s['folder'])}</td></tr>
    <tr><th>if name exists</th><td>{e(s['on_duplicate'])}</td></tr>
  </table>
  {embed}
  <p class="note">Later steps can link this file with <code>{{{{{s['n']}.course_file_url}}}}</code> (filled in after upload).</p>
</section>"""


def text_summary(plan, digest):
    lines = [f"Plan: {plan['title']}", f"sha256: {digest[:12]}"]
    for s in plan["steps"]:
        if s.get("kind") == "upload":
            lines.append(f"  {s['n']}. UPLOAD {s['course']} ({s['course_name']}) {s['file']} "
                         f"-> Files/{'(top level)' if s['folder'] == '/' else s['folder']}  ({_size(s['size'])}, sha256 {s['sha256'][:12]})")
            lines.extend(f"       ! {w}" for w in warnings_for(s))
            continue
        inner = _inner(s["body"])
        label = inner.get("name") or inner.get("title") or s["note"] or ""
        lines.append(f"  {s['n']}. {s['method']} {s['course']} ({s['course_name']}) /{s['path']}  {label}")
        for k in ("points_possible", "due_at", "published"):
            if k in inner:
                lines.append(f"       {k}: {_fmt(k, inner[k])}")
        for w in warnings_for(s):
            lines.append(f"       ! {w}")
    return "\n".join(lines)


def render_preview(plan, digest, base_url, approval=None):
    e = html.escape
    cards = []
    for s in plan["steps"]:
        if s.get("kind") == "upload":
            cards.append(_upload_card(s))
            continue
        inner = _inner(s["body"])
        rows = "".join(f"<tr><th>{e(k)}</th><td>{e(_fmt(k, inner[k]))}</td></tr>"
                       for k in SUMMARY_KEYS if k in inner)
        warns = "".join(f"<li>{e(w)}</li>" for w in warnings_for(s))
        bodies = "".join(
            f"<h4>{e(k)} (as students will see it)</h4>"
            f"<iframe sandbox srcdoc=\"{e(inner[k], quote=True)}\"></iframe>"
            for k in HTML_KEYS if isinstance(inner.get(k), str) and inner[k].strip())
        url = f"{base_url}/api/v1/courses/{s['course_id']}/{s['path']}"
        cards.append(f"""
<section class="card">
  <div class="course">{e(s['course_name'])} <span class="alias">{e(s['course'])} · id {s['course_id']}</span></div>
  <h2>Step {s['n']}: {e(s['method'])} {e(s['path'])}</h2>
  {f'<p class="note">{e(s["note"])}</p>' if s['note'] else ''}
  {f'<ul class="warn">{warns}</ul>' if warns else ''}
  <table>{rows}</table>
  {bodies}
  <details><summary>Exact request</summary><pre>{e(s['method'])} {e(url)}\n\n{e(json.dumps(s['body'], indent=2, ensure_ascii=False))}</pre></details>
</section>""")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Canvas plan preview</title>
<style>
:root {{ --bg:#f6f7f9; --card:#fff; --ink:#1b1f24; --muted:#5b6470; --line:#dde1e6; --warn-bg:#fff4e0; --warn:#8a4b00; --accent:#2b5fd9; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#15181c; --card:#1e2227; --ink:#e7eaee; --muted:#9aa4af; --line:#333a42; --warn-bg:#3a2a10; --warn:#ffc46b; --accent:#8fb0ff; }} }}
body {{ background:var(--bg); color:var(--ink); font:15px/1.5 -apple-system, system-ui, sans-serif; margin:0; padding:24px 16px; }}
main {{ max-width:860px; margin:0 auto; }}
h1 {{ font-size:22px; margin:0 0 4px; }} .meta {{ color:var(--muted); margin-bottom:20px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px 18px; margin-bottom:16px; }}
.course {{ font-weight:600; color:var(--accent); }} .alias {{ color:var(--muted); font-weight:400; }}
h2 {{ font-size:17px; margin:6px 0; }} .note {{ color:var(--muted); margin:0 0 8px; }}
.warn {{ background:var(--warn-bg); color:var(--warn); border-radius:6px; padding:8px 8px 8px 28px; margin:8px 0; }}
table {{ border-collapse:collapse; margin:8px 0; }} th {{ text-align:left; color:var(--muted); font-weight:500; padding:2px 16px 2px 0; }}
.pdf {{ width:100%; height:520px; border:1px solid var(--line); border-radius:6px; }}
iframe {{ width:100%; min-height:260px; border:1px solid var(--line); border-radius:6px; background:#fff; }}
pre {{ white-space:pre-wrap; word-break:break-word; font-size:12px; background:var(--bg); padding:10px; border-radius:6px; }}
.next {{ border-left:3px solid var(--accent); padding:4px 12px; }}
code {{ font-size:13px; }}
</style></head><body><main>
<h1>{e(plan['title'])}</h1>
<div class="meta">{len(plan['steps'])} step(s) · plan sha256 {digest[:12]} · generated {datetime.now().strftime('%b %-d %-I:%M %p')}</div>
{''.join(cards)}
<p class="next">Nothing has been sent yet. {e(approval) if approval else 'If this looks right, run <code>canvas-harness approve &lt;plan&gt;</code> in your terminal.'}</p>
</main></body></html>"""


def stamp_path(plan_path):
    p = Path(plan_path).resolve()
    return p.with_name(p.name + ".approved")


def read_stamp(plan_path):
    sp = stamp_path(plan_path)
    return json.loads(sp.read_text()) if sp.exists() else None


def preview(plan_path, roster, base_url, open_browser=None, uploads_root=None, settings=None):
    """open_browser=None follows auto_preview in canvas-config.json."""
    settings = settings or st.load_switches()
    plan, digest = load_plan(plan_path, roster, uploads_root, settings)
    approval = approval_line(plan, settings)
    out = Path(plan_path).resolve().with_name(Path(plan_path).name + ".preview.html")
    out.write_text(render_preview(plan, digest, base_url, approval))
    print(text_summary(plan, digest))
    print(f"\n{approval}")
    print(f"preview: {out}")
    if open_browser is None:
        open_browser = settings["auto_preview"]
    if open_browser and sys.platform == "darwin":
        subprocess.run(["open", str(out)], check=False)
    return out


def approve(plan_path, roster, tty_path="/dev/tty", uploads_root=None):
    plan, digest = load_plan(plan_path, roster, uploads_root)
    try:
        tty_in, tty_out = open(tty_path, "r"), open(tty_path, "a")
    except OSError:
        raise PlanError("approve must be run by you in an interactive terminal")
    with tty_in, tty_out:
        tty_out.write(text_summary(plan, digest) + "\n\nType 'approve' to allow this exact plan to be applied: ")
        tty_out.flush()
        answer = tty_in.readline().strip()
    if answer != "approve":
        raise PlanError("not approved")
    stamp = {"digest": digest, "approved_at": datetime.now(timezone.utc).isoformat(),
             "approved_by": "typed", "applied_at": None}
    stamp_path(plan_path).write_text(json.dumps(stamp, indent=2) + "\n")
    print(f"approved {digest[:12]}")


def apply(plan_path, roster, send, describe=print, upload=None, uploads_root=None, settings=None):
    """send(method, path, body) -> response dict; upload(course_id, abs_path, folder, on_duplicate)
    -> Canvas file dict. Returns list of step results."""
    settings = settings or st.load_switches()
    plan, digest = load_plan(plan_path, roster, uploads_root, settings)
    stamp = read_stamp(plan_path)
    if not stamp and settings["auto_approve"]:
        blocking = blocking_warnings(plan)
        if blocking:
            raise PlanError("auto_approve is on, but this plan is flagged, so you must run "
                            "`canvas-harness approve` yourself:\n  " + "\n  ".join(blocking))
        stamp = {"digest": digest, "approved_at": datetime.now(timezone.utc).isoformat(),
                 "approved_by": "auto (canvas-config.json)", "applied_at": None}
        stamp_path(plan_path).write_text(json.dumps(stamp, indent=2) + "\n")
        describe(f"auto-approved {digest[:12]} (canvas-config.json: auto_approve is on, nothing flagged)")
    if not stamp:
        raise PlanError("plan is not approved; run `canvas-harness preview` then `canvas-harness approve`")
    if stamp.get("digest") != digest:
        raise PlanError("plan (or a file it uses) changed since approval; preview and approve again")
    if stamp.get("applied_at"):
        raise PlanError(f"plan was already applied at {stamp['applied_at']}; make a new plan to change things")
    results, log = {}, []
    result_file = Path(plan_path).resolve().with_name(Path(plan_path).name + ".result.json")
    try:
        for s in plan["steps"]:
            if s["kind"] == "upload":
                if upload is None:
                    raise PlanError("this plan has upload steps but no uploader was provided")
                describe(f"step {s['n']}: UPLOAD {s['file']} -> {s['course']} = {s['course_name']} Files/{'(top level)' if s['folder'] == '/' else s['folder']}")
                resp = dict(upload(s["course_id"], s["abs"], s["folder"], s["on_duplicate"]) or {})
                if resp.get("id"):
                    resp["course_file_url"] = f"/courses/{s['course_id']}/files/{resp['id']}"
                results[s["n"]] = resp
                log.append({"step": s["n"], "ok": True, "id": resp.get("id"),
                            "html_url": resp.get("course_file_url"), "display_name": resp.get("display_name")})
                continue
            body = substitute(s["body"], results)
            rel = substitute(s["path"], results)
            describe(f"step {s['n']}: {s['method']} {s['course']} = {s['course_name']} /{rel}")
            resp = send(s["method"], f"courses/{s['course_id']}/{rel}", body) or {}
            results[s["n"]] = resp if isinstance(resp, dict) else {}
            log.append({"step": s["n"], "ok": True, "id": results[s["n"]].get("id"),
                        "html_url": results[s["n"]].get("html_url")})
    except Exception as e:
        log.append({"step": len(log) + 1, "ok": False, "error": str(e).splitlines()[0]})
        raise
    finally:
        # Any sent step consumes the approval, so a partial run cannot be replayed blindly.
        if log and any(r["ok"] for r in log):
            stamp["applied_at"] = datetime.now(timezone.utc).isoformat()
            stamp_path(plan_path).write_text(json.dumps(stamp, indent=2) + "\n")
        result_file.write_text(json.dumps({"digest": digest, "steps": log}, indent=2) + "\n")
    return log
