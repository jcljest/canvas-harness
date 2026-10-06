"""Course-scoped Canvas REST client.

Reads CANVAS_BASE_URL, CANVAS_API_TOKEN and CANVAS_COURSE_IDS from the
secrets file in local/ written by `bin/+a` (or from the process environment). The token is
only ever used inside this process: it is never printed, and any error text is
redacted before it is shown.

Scope rule: every request must target /api/v1/courses/<id>/... for an id in
CANVAS_COURSE_IDS. The only exceptions are a few read-only GETs about the
token's own user and the list of their own courses (see READ_ONLY_GLOBAL).
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import settings as st
from .settings import SetupError, load_roster

PROG = "canvas-harness"
SETUP_HINT = "First time? Open this repo in Claude Code and type /setup."
REQUIRED = ("CANVAS_BASE_URL", "CANVAS_API_TOKEN", "CANVAS_COURSE_IDS")
WRITE_METHODS = {"POST", "PUT", "DELETE"}
COURSE_PATH = re.compile(r"^/api/v1/courses/(\d+)(/.*)?$")
READ_ONLY_GLOBAL = re.compile(r"^/api/v1/(users/self(/profile)?|courses)$")


class ScopeError(Exception):
    pass


class ConfigError(Exception):
    pass


def parse_secrets(text):
    """Parse KEY=value lines; ignores blanks/comments, strips `export ` and matching quotes."""
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key] = value
    return out


def load_config(path=None, environ=None, require_courses=True):
    environ = os.environ if environ is None else environ
    path = Path(path or st.secrets_path())
    values = {}
    if path.exists():
        values = parse_secrets(path.read_text())
    for key in REQUIRED:
        if environ.get(key):
            values[key] = environ[key]
    needed = REQUIRED if require_courses else REQUIRED[:2]
    missing = [k for k in needed if not values.get(k)]
    if missing:
        raise ConfigError(
            "missing " + ", ".join(missing) + " — add each in your own terminal with: bin/+a "
            + " / bin/+a ".join(missing) + "\n" + SETUP_HINT
        )
    base = values["CANVAS_BASE_URL"].rstrip("/")
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ConfigError("CANVAS_BASE_URL must look like https://yourschool.instructure.com")
    base = f"https://{parsed.netloc}"
    ids = {s.strip() for s in re.split(r"[,\s]+", values.get("CANVAS_COURSE_IDS", "")) if s.strip()}
    bad = sorted(i for i in ids if not i.isdigit())
    if bad:
        raise ConfigError("CANVAS_COURSE_IDS must be numeric Canvas course ids (comma-separated)")
    return {"base": base, "token": values["CANVAS_API_TOKEN"], "course_ids": ids}


def expand_alias(target, roster):
    """'@chem/assignments' -> 'courses/1001/assignments'. Other targets pass through."""
    if not target.startswith("@"):
        return target
    alias, _, rest = target[1:].partition("/")
    if alias not in roster:
        known = ", ".join("@" + a for a in sorted(roster)) or "(none; see courses.json)"
        raise ScopeError(f"unknown course alias @{alias}; known: {known}")
    return f"courses/{roster[alias]['id']}" + (f"/{rest}" if rest else "")


def describe_target(path, roster):
    m = COURSE_PATH.match(path.split("?", 1)[0].rstrip("/"))
    if not m:
        return path
    by_id = {str(c["id"]): c for c in roster.values()}
    c = by_id.get(m.group(1))
    if not c:
        return f"course {m.group(1)} (WARNING: not in courses.json)"
    return f"@{c['alias']} = {c['name']} (id {c['id']})"


def normalize_path(target, base):
    """Accept 'courses/1/x', '/api/v1/courses/1/x' or a full URL on base; return '/api/v1/...[?q]'."""
    parsed = urllib.parse.urlsplit(target)
    if parsed.scheme or parsed.netloc:
        if f"{parsed.scheme}://{parsed.netloc}" != base:
            raise ScopeError(f"refusing URL on another host: {parsed.scheme}://{parsed.netloc}")
    path = parsed.path
    if not path.startswith("/"):
        path = "/" + path
    if not path.startswith("/api/v1/"):
        path = "/api/v1" + path
    path = re.sub(r"/{2,}", "/", path)
    if "/../" in path + "/" or "/./" in path + "/":
        raise ScopeError("path may not contain '.' or '..' segments")
    return path + (f"?{parsed.query}" if parsed.query else "")


def check_scope(method, path, course_ids):
    bare = path.split("?", 1)[0].rstrip("/")
    m = COURSE_PATH.match(bare)
    if m:
        if m.group(1) not in course_ids:
            raise ScopeError(f"course {m.group(1)} is not in CANVAS_COURSE_IDS")
        return
    if method == "GET" and READ_ONLY_GLOBAL.match(bare):
        return
    raise ScopeError(f"{method} {bare} is outside the allowed course scope")


def redact(text, token):
    return text.replace(token, "[REDACTED]") if token else text


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward the Authorization header to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            raise urllib.error.HTTPError(newurl, code, "cross-host redirect refused", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SameHostRedirect)


def _next_link(link_header):
    for part in (link_header or "").split(","):
        m = re.match(r'\s*<([^>]+)>\s*;\s*rel="next"', part)
        if m:
            return m.group(1)
    return None


def request(cfg, method, target, query=None, form=None, body=None, paginate=False, dry_run=False):
    method = method.upper()
    path = normalize_path(target, cfg["base"])
    check_scope(method, path, cfg["course_ids"])
    if query:
        sep = "&" if "?" in path else "?"
        path += sep + urllib.parse.urlencode(query, doseq=True)
    url = cfg["base"] + path

    data, ctype = None, None
    if body is not None:
        data, ctype = json.dumps(body).encode(), "application/json"
    elif form:
        data, ctype = urllib.parse.urlencode(form, doseq=True).encode(), "application/x-www-form-urlencoded"

    if dry_run:
        return {"dry_run": True, "method": method, "url": url,
                "body": body if body is not None else (form or None)}

    results = []
    while True:
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {cfg['token']}")
        req.add_header("Accept", "application/json")
        if ctype:
            req.add_header("Content-Type", ctype)
        try:
            with _opener.open(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8", "replace")
                link = resp.headers.get("Link")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace") if e.fp else ""
            raise RuntimeError(redact(f"HTTP {e.code} {e.reason} for {method} {path}\n{detail}", cfg["token"]))
        except urllib.error.URLError as e:
            raise RuntimeError(redact(f"network error for {method} {path}: {e.reason}", cfg["token"]))
        payload = json.loads(raw) if raw.strip() else None
        if not (paginate and method == "GET" and isinstance(payload, list)):
            return payload
        results.extend(payload)
        nxt = _next_link(link)
        if not nxt:
            return results
        nxt_path = normalize_path(nxt, cfg["base"])
        check_scope("GET", nxt_path, cfg["course_ids"])
        url = cfg["base"] + nxt_path


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # surface 3xx as HTTPError so we decide where auth goes


_upload_opener = urllib.request.build_opener(_NoRedirect)
FILE_CONFIRM = re.compile(r"^/api/v1/files/\d+(/create_success)?$")


def _multipart(fields, filename, content, ctype):
    boundary = "----canvasharness" + os.urandom(12).hex()
    safe_name = filename.replace('"', "%22").replace("\r", "").replace("\n", "")
    out = []
    for key, value in fields:
        out.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    out.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
               f"Content-Type: {ctype}\r\n\r\n".encode() + content + b"\r\n")
    out.append(f"--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def upload_file(cfg, course_id, local_path, folder, on_duplicate="rename"):
    """Canvas 3-step upload into a course's Files. Returns the Canvas file object.

    1. POST /courses/:id/files (authenticated, scope-checked) -> upload_url + upload_params
    2. POST multipart to upload_url WITHOUT the Authorization header
    3. If Canvas answers with a confirm location, GET it (authenticated) only if it is
       /api/v1/files/<id> on the Canvas host.
    """
    import mimetypes

    path = Path(local_path)
    data = path.read_bytes()
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    init = request(cfg, "POST", f"courses/{course_id}/files", body={
        "name": path.name, "size": len(data), "content_type": ctype,
        "parent_folder_path": folder, "on_duplicate": on_duplicate,
    })
    up_url = (init or {}).get("upload_url", "")
    if urllib.parse.urlsplit(up_url).scheme != "https":
        raise RuntimeError("Canvas did not return an https upload_url")
    body, mp_type = _multipart(list((init.get("upload_params") or {}).items()), path.name, data, ctype)
    req = urllib.request.Request(up_url, data=body, method="POST")  # no Authorization on purpose
    req.add_header("Content-Type", mp_type)
    location = None
    try:
        with _upload_opener.open(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8", "replace")
            location = resp.headers.get("Location")
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            raw, location = "", e.headers.get("Location")
        else:
            detail = e.read().decode("utf-8", "replace")[:500] if e.fp else ""
            raise RuntimeError(redact(f"upload of {path.name} failed: HTTP {e.code} {e.reason}\n{detail}", cfg["token"]))
    except urllib.error.URLError as e:
        raise RuntimeError(f"network error uploading {path.name}: {e.reason}")
    try:
        result = json.loads(raw) if raw.strip().startswith("{") else {}
    except ValueError:
        result = {}
    if not result.get("id"):
        location = location or result.get("location")
        if not location:
            raise RuntimeError(f"upload of {path.name} finished but Canvas returned no file id")
        loc = urllib.parse.urlsplit(urllib.parse.urljoin(cfg["base"], location))
        if f"{loc.scheme}://{loc.netloc}" != cfg["base"] or not FILE_CONFIRM.match(loc.path):
            raise RuntimeError(f"unexpected upload confirmation location: {loc.scheme}://{loc.netloc}{loc.path}")
        confirm = urllib.request.Request(cfg["base"] + loc.path + (f"?{loc.query}" if loc.query else ""))
        confirm.add_header("Authorization", f"Bearer {cfg['token']}")
        confirm.add_header("Accept", "application/json")
        try:
            with _opener.open(confirm, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(redact(f"upload confirmation failed: HTTP {e.code} {e.reason}", cfg["token"]))
    if not result.get("id"):
        raise RuntimeError(f"upload of {path.name} finished but Canvas returned no file id")
    return result


def _pairs(items):
    out = []
    for item in items or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"expected key=value, got: {item}")
        out.append((key, value))
    return out


def _json_arg(value):
    if value is None:
        return None
    if value == "-":
        return json.load(sys.stdin)
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text())
    return json.loads(value)


def _plan_command(args):
    from . import plan as plans

    roster = load_roster()
    try:
        if args.cmd == "approve":
            plans.approve(args.plan, roster)
            return 0
        if args.cmd == "preview":
            try:
                base = load_config(args.env_file, require_courses=False)["base"]
            except ConfigError:
                base = "https://<CANVAS_BASE_URL>"
            plans.preview(args.plan, roster, base, open_browser=False if args.no_open else (True if args.open else None))
            return 0
        cfg = load_config(args.env_file)
        log = plans.apply(
            args.plan, roster,
            send=lambda method, path, body: request(cfg, method, path, body=body),
            upload=lambda course_id, path, folder, on_dup: upload_file(cfg, course_id, path, folder, on_dup),
            describe=lambda line: print(line, file=sys.stderr),
        )
        print(json.dumps(log, indent=2))
        return 0
    except (plans.PlanError, ConfigError, ScopeError, SetupError) as e:
        print(f"canvas-harness: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"canvas-harness: {e}", file=sys.stderr)
        print("Stopped. Completed steps are recorded in the .result.json file next to the plan.", file=sys.stderr)
        return 1


def _which(name):
    """Print the course a name means. Exit 0 on exactly one match, 1 otherwise."""
    roster = load_roster()
    if not roster:
        print(f"No courses in {st.roster_path()}. {SETUP_HINT}")
        return 1
    matches, candidates = st.resolve_course(name, roster)
    if matches:
        c = roster[matches[0]]
        print(f"@{c['alias']} = {c['name']} (id {c['id']})")
        return 0
    print(f"no course is called {name!r}.")
    for a in candidates:
        c = roster[a]
        print(f"  maybe @{a} = {c['name']}" + (f" (also called: {', '.join(c['nicknames'])})" if c.get("nicknames") else ""))
    if not candidates:
        print("  courses: " + ", ".join(f"@{a} ({c['name']})" for a, c in sorted(roster.items())))
    return 1


def main(argv=None):
    try:
        return _main(argv)
    except SetupError as e:
        print(f"{PROG}: {e}\n{SETUP_HINT}", file=sys.stderr)
        return 2


def _main(argv=None):
    ap = argparse.ArgumentParser(prog=PROG, description="Course-scoped Canvas API client.")
    ap.add_argument("--env-file", help="secrets file (default: local/ in this repo, or $CANVAS_HARNESS_LOCAL)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="validate config and connectivity (never prints the token)")
    sub.add_parser("whoami", help="GET users/self")
    sub.add_parser("courses", help="show each allowlisted course")
    sub.add_parser("roster", help="verify courses.json against live Canvas titles and the allowlist")
    d = sub.add_parser("discover", help="list courses you teach, to find ids for CANVAS_COURSE_IDS")
    d.add_argument("--any-role", action="store_true", help="include courses where you are not a teacher")
    d.add_argument("--json", action="store_true", help="print raw JSON instead of a table")
    pv = sub.add_parser("preview", help="render a plan file to HTML for review (sends nothing)")
    pv.add_argument("plan")
    pv.add_argument("--no-open", action="store_true", help="don't open the preview in a browser")
    pv.add_argument("--open", action="store_true", help="open the preview even if auto_preview is false")
    sub.add_parser("config", help="show your switches (auto_approve, auto_preview, auto_publish); only you edit that file")
    wh = sub.add_parser("which", help="which course a name means, e.g. which \"AP Physics\" (uses aliases, nicknames, titles)")
    wh.add_argument("name", nargs="+", help="what you call the class; several words are joined")
    sub.add_parser("doctor", help="checklist of what is set up and what to do next (never prints secrets)").add_argument(
        "--offline", action="store_true", help="skip the connection test")
    sub.add_parser("approve", help="YOU approve a previewed plan (needs a terminal)").add_argument("plan")
    sub.add_parser("apply", help="send an approved plan to Canvas").add_argument("plan")
    sub.add_parser("uploads", help="list files waiting in each course's landing folder (uploads/<alias>/)")
    pdf = sub.add_parser("pdf", help="render course HTML to PDF in its landing folder (course comes from the file's project folder)")
    pdf.add_argument("html", nargs="+", help="HTML file(s) under a roster local_project folder")
    pdf.add_argument("--course", help="expected course alias, e.g. @chem (a cross-check only; refuses on mismatch)")
    pdf.add_argument("--name", help="output file name (one HTML file only)")
    pdf.add_argument("--pages", type=int, help="expected page count; fail and write nothing on mismatch")
    pdf.add_argument("--overwrite", action="store_true", help="replace an existing landing-folder file")
    for m in ("get", "post", "put", "delete"):
        p = sub.add_parser(m, help=f"{m.upper()} a course-scoped path, e.g. courses/123/assignments")
        p.add_argument("path")
        p.add_argument("-q", "--query", action="append", metavar="K=V", help="query param (repeatable)")
        if m == "get":
            p.add_argument("--all", action="store_true", help="follow pagination")
        else:
            p.add_argument("-F", "--form", action="append", metavar="K=V",
                           help="form field, e.g. -F 'assignment[name]=Lab 3' (repeatable)")
            p.add_argument("--json", help="JSON body: literal, @file.json, or - for stdin")
            p.add_argument("--dry-run", action="store_true", help="show the request without sending")
        if m == "delete":
            p.add_argument("--yes", action="store_true", help="required to actually delete")
    args = ap.parse_args(argv)

    if args.cmd == "uploads":
        from . import plan as plans

        roster = load_roster()
        if not roster:
            print(f"No courses in {st.roster_path()}. {SETUP_HINT}")
        for alias, c in sorted(roster.items()):
            folder = st.uploads_root() / alias
            files = sorted(f for f in folder.rglob("*") if f.is_file() and not f.name.startswith("."))
            print(f"@{alias}  {c['name']}  ({folder})")
            for f in files:
                ok = "" if f.suffix.lower() in plans.UPLOAD_EXTS else "   (type not allowed)"
                print(f"    {f.relative_to(folder)}  {plans._size(f.stat().st_size)}{ok}")
            if not files:
                print("    (empty)")
        return 0
    if args.cmd == "pdf":
        from . import pdf as pdfs

        roster = load_roster()
        try:
            if args.name and len(args.html) > 1:
                raise pdfs.PdfError("--name works with one HTML file at a time")
            for h in args.html:  # check every file's course before rendering any
                alias = pdfs.course_for(h, roster)[0]
                if args.course and args.course.lstrip("@") != alias:
                    raise pdfs.PdfError(f"{h} belongs to @{alias}, not {args.course}; nothing written")
            for h in args.html:
                dest, n = pdfs.make_pdf(h, roster, course=args.course, name=args.name,
                                            pages=args.pages, overwrite=args.overwrite)
                print(f"@{dest.parent.name}  {dest.name}  {n} page{'s' * (n != 1)}  ({dest})")
        except pdfs.PdfError as e:
            print(f"canvas-harness pdf: {e}", file=sys.stderr)
            return 2
        return 0
    if args.cmd == "which":
        return _which(" ".join(args.name))
    if args.cmd == "doctor":
        from . import doctor
        return doctor.run(offline=args.offline)
    if args.cmd == "config":
        settings = st.load_switches()
        cfg_path = st.config_path()
        src = cfg_path if cfg_path.exists() else f"{cfg_path} (missing; safe defaults)"
        print(f"file: {src}")
        for k, v in settings.items():
            print(f"{k}: {json.dumps(v)}")
        return 0
    if args.cmd in ("preview", "approve", "apply"):
        return _plan_command(args)

    try:
        cfg = load_config(args.env_file, require_courses=args.cmd != "discover")
        if args.cmd == "check":
            print(f"base:   {cfg['base']}")
            print(f"course ids: {', '.join(sorted(cfg['course_ids'], key=int))}")
            me = request(cfg, "GET", "users/self")
            print(f"token:  ok (user: {me.get('name')} id={me.get('id')})")
            failed = False
            for cid in sorted(cfg["course_ids"], key=int):
                try:
                    c = request(cfg, "GET", f"courses/{cid}")
                    print(f"course: {cid}  {c.get('course_code', '')}  {c.get('name', '')}")
                except RuntimeError as e:
                    failed = True
                    print(f"course: {cid}  NOT ACCESSIBLE ({str(e).splitlines()[0]})")
            if failed:
                print("Run `canvas-harness discover` to list your real course ids.")
            return 1 if failed else 0
        if args.cmd == "discover":
            query = [("per_page", "100"), ("include[]", "term"),
                     ("state[]", "available"), ("state[]", "unpublished"), ("state[]", "completed")]
            if not args.any_role:
                query.append(("enrollment_type", "teacher"))
            rows = request(cfg, "GET", "courses", query=query, paginate=True)
            rows = [c for c in rows if c.get("id") and not c.get("access_restricted_by_date")]
            if args.json:
                print(json.dumps(rows, indent=2, ensure_ascii=False))
                return 0
            if not rows:
                print("No courses found." + ("" if args.any_role else " Try --any-role."))
                return 0
            print(f"{'id':>6}  {'allowed':<7}  {'state':<11}  {'term':<22}  name")
            for c in rows:
                term = (c.get("term") or {}).get("name") or ""
                allowed = "yes" if str(c["id"]) in cfg["course_ids"] else ""
                print(f"{c['id']:>6}  {allowed:<7}  {c.get('workflow_state', ''):<11}  "
                      f"{term[:22]:<22}  {c.get('name', '')}")
            print("\nTo allow courses, run in your own terminal:  bin/+a CANVAS_COURSE_IDS")
            print("and enter the ids comma-separated (e.g. 1234,5678).")
            return 0
        if args.cmd == "roster":
            roster, ok = load_roster(), True
            for c in roster.values():
                allowed = str(c["id"]) in cfg["course_ids"]
                try:
                    live = request(cfg, "GET", f"courses/{c['id']}").get("name")
                except (RuntimeError, ScopeError) as e:
                    live = f"UNREACHABLE: {str(e).splitlines()[0]}"
                match = live == c["name"]
                ok = ok and allowed and match
                print(f"@{c['alias']:<8} {c['id']:>6}  allowed={'yes' if allowed else 'NO '}  "
                      f"{'ok      ' if match else 'MISMATCH'}  {c['name']}"
                      + ("" if match else f"  (live: {live})"))
                if c.get("nicknames"):
                    print(f"{'':>17}also called: {', '.join(c['nicknames'])}")
            extra = cfg["course_ids"] - {str(c["id"]) for c in roster.values()}
            for cid in sorted(extra, key=int):
                ok = False
                print(f"(no alias) {cid:>6}  allowed=yes  in CANVAS_COURSE_IDS but missing from courses.json")
            return 0 if ok else 1
        if args.cmd == "whoami":
            out = request(cfg, "GET", "users/self")
        elif args.cmd == "courses":
            out = []
            for cid in sorted(cfg["course_ids"], key=int):
                try:
                    c = request(cfg, "GET", f"courses/{cid}")
                    out.append({k: c.get(k) for k in ("id", "course_code", "name", "workflow_state")})
                except RuntimeError as e:
                    out.append({"id": int(cid), "error": str(e).splitlines()[0],
                                "hint": "run `canvas-harness discover` to find your course ids"})
        else:
            method = args.cmd.upper()
            args.path = expand_alias(args.path, load_roster())
            if method != "GET":
                where = describe_target(normalize_path(args.path, cfg["base"]), load_roster())
                print(f"target: {where}", file=sys.stderr)
            if method == "DELETE" and not args.yes and not args.dry_run:
                raise ScopeError("DELETE requires --yes (or use --dry-run to preview)")
            out = request(
                cfg, method, args.path,
                query=_pairs(args.query),
                form=_pairs(getattr(args, "form", None)),
                body=_json_arg(getattr(args, "json", None)),
                paginate=getattr(args, "all", False),
                dry_run=getattr(args, "dry_run", False),
            )
    except (ConfigError, ScopeError) as e:
        print(f"canvas-harness: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"canvas-harness: {e}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
