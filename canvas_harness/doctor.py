"""`canvas-harness doctor`: a read-only checklist of what is set up and what to do next.

It never prints secret values: only whether each name is set. /setup runs it
after each step, so every line says what to do next when something is missing.
"""

import os
import stat
import sys

from . import settings as st

OK, TODO, WARN, SKIP = "ok  ", "TODO", "warn", "skip"


def _line(status, label, detail=""):
    print(f"[{status}] {label}" + (f": {detail}" if detail else ""))


def run(offline=False, request=None, load_config=None, parse_secrets=None):
    """Print the checklist. Returns 0 when everything required is done, else 1."""
    from . import cli

    request = request or cli.request
    load_config = load_config or cli.load_config
    parse_secrets = parse_secrets or cli.parse_secrets
    done = True

    _line(OK if sys.version_info >= (3, 9) else TODO, "python", sys.version.split()[0]
          + ("" if sys.version_info >= (3, 9) else " (need 3.9+)"))

    secrets = st.secrets_path()
    names = set()
    if not secrets.exists():
        done = False
        _line(TODO, "secrets file", f"copy .env.example to {secrets.name} in {secrets.parent} and fill in "
              "CANVAS_BASE_URL and CANVAS_API_TOKEN in your editor")
    else:
        names = {k for k, v in parse_secrets(secrets.read_text()).items() if v}
        mode = stat.S_IMODE(os.stat(secrets).st_mode)
        _line(OK, "secrets file", str(secrets))
        if mode & 0o077:
            _line(WARN, "secrets file permissions", f"{oct(mode)}; run `chmod 600 {secrets}` so only you can read it")
    for key in ("CANVAS_BASE_URL", "CANVAS_API_TOKEN"):
        if key in names:
            _line(OK, key, "set")
        else:
            done = False
            _line(TODO, key, f"add it to {secrets.name} (or run `bin/+a {key}` in your own terminal)")

    cfg = None
    if offline:
        _line(SKIP, "connection", "offline")
    elif {"CANVAS_BASE_URL", "CANVAS_API_TOKEN"} <= names:
        try:
            cfg = load_config(require_courses=False)
            me = request(cfg, "GET", "users/self")
            _line(OK, "connection", f"token works for {me.get('name')} at {cfg['base']}")
        except Exception as e:  # ConfigError, ScopeError, RuntimeError: all already redacted
            done = False
            cfg = None
            _line(TODO, "connection", str(e).splitlines()[0])
    else:
        _line(SKIP, "connection", "needs CANVAS_BASE_URL and CANVAS_API_TOKEN first")

    roster = st.load_roster()
    ids = set()
    if "CANVAS_COURSE_IDS" in names:
        ids = {s.strip() for s in parse_secrets(secrets.read_text())["CANVAS_COURSE_IDS"].replace(" ", ",").split(",")
               if s.strip()}
        _line(OK, "CANVAS_COURSE_IDS", f"{len(ids)} course(s) allowed")
    else:
        done = False
        _line(TODO, "CANVAS_COURSE_IDS", "run /setup: it lists your courses and tells you which ids to add")

    if not roster:
        done = False
        _line(TODO, "courses", f"no {st.roster_path().name} yet; run /setup")
    else:
        for alias, c in sorted(roster.items()):
            allowed = str(c["id"]) in ids
            if not allowed:
                done = False
            proj = st.project_dir(c)
            where = f", folder {proj}" + ("" if proj.is_dir() else " (MISSING)") if proj else ""
            _line(OK if allowed else TODO, f"course @{alias}",
                  f"{c['name']} (id {c['id']}){where}" + ("" if allowed else f"; add {c['id']} to CANVAS_COURSE_IDS"))
            if not c.get("nicknames"):
                _line(WARN, f"course @{alias} nicknames", "none; run /setup so Claude knows what you call this class")
            else:
                _line(OK, f"course @{alias} nicknames", ", ".join(c["nicknames"]))
        extra = ids - {str(c["id"]) for c in roster.values()}
        if extra:
            _line(WARN, "allowed ids without an alias", ", ".join(sorted(extra)) + "; run /setup to name them or remove them")

    if st.profile_path().exists():
        prof = st.load_profile()
        _line(OK if prof["timezone"] else WARN, "profile",
              f"timezone {prof['timezone']}" if prof["timezone"] else "no timezone set; date offsets won't be checked")
    else:
        done = False
        _line(TODO, "profile", "run /setup to set your timezone and naming conventions")

    sw = st.load_switches()
    src = "" if st.config_path().exists() else " (no file; safe defaults)"
    _line(OK, "switches", ", ".join(f"{k}={str(v).lower()}" for k, v in sw.items()) + src)

    try:
        from .pdf import chrome_path
        _line(OK, "chrome (for pdf only)", chrome_path())
    except Exception:
        _line(SKIP, "chrome (for pdf only)", "not found; only needed for `canvas-harness pdf`")

    if done:
        print("\nAll set (connection not checked; run without --offline)." if offline else "\nAll set.")
    else:
        print("\nNot finished yet: see the TODO lines (or run /setup).")
    return 0 if done else 1
