"""Where each user's files live, and how their profile and switches are read.

Secrets live in `.env` at the repo root (copied from `.env.example` and
filled in by the user; override with $CANVAS_HARNESS_ENV). Everything else
personal sits in one gitignored folder, `local/` (override with $CANVAS_HARNESS_LOCAL):

    local/profile.json         timezone, naming conventions (written by /setup)
    local/courses.json         course roster: alias -> id, exact title, project folder
    local/canvas-config.json   the user's switches; override the shipped ones key by key
    local/plans/               plan files
    local/uploads/<alias>/     files waiting to be uploaded

The repo ships recommended switches in a tracked canvas-config.json at the
repo root (edited only by the maintainer). Code never hardcodes a person, school, course or path; it reads these files.
"""

import json
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

DEFAULT_SWITCHES = {"auto_approve": False, "auto_preview": True, "auto_publish": False}
DEFAULT_PROFILE = {
    "timezone": None,                 # IANA name, e.g. "America/Chicago"; enables date-offset checks
    "projects_root": "~",             # relative `local_project` folders are resolved against this
    "default_upload_folder": "Uploads",
    "answer_key_label": "ANS",        # suffix for rendered answer-key PDFs
    "answer_key_words": ["ans", "answer", "answers", "key", "keys", "solution", "solutions", "soln", "sol"],
}


class SetupError(Exception):
    """A user file is missing or malformed; the message says how to fix it."""


def local_dir():
    return Path(os.environ.get("CANVAS_HARNESS_LOCAL") or REPO / "local").expanduser()


def secrets_path():
    return Path(os.environ.get("CANVAS_HARNESS_ENV") or REPO / ".env").expanduser()


def profile_path():
    return local_dir() / "profile.json"


def roster_path():
    return local_dir() / "courses.json"


def config_path():
    return local_dir() / "canvas-config.json"


def shipped_config_path():
    return REPO / "canvas-config.json"


def switch_sources():
    """The switch files that exist, lowest priority first: shipped, then the user's."""
    return [p for p in (shipped_config_path(), config_path()) if p.exists()]


def uploads_root():
    return local_dir() / "uploads"


def plans_root():
    return local_dir() / "plans"


def _read_json(path, what):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise SetupError(f"cannot read {what} {path}: {e}")


def load_profile(path=None):
    path = Path(path or profile_path())
    if not path.exists():
        return dict(DEFAULT_PROFILE)
    raw = _read_json(path, "profile")
    if not isinstance(raw, dict):
        raise SetupError(f"{path.name} must be a JSON object")
    unknown = set(raw) - set(DEFAULT_PROFILE)
    if unknown:
        raise SetupError(f"{path.name}: unknown key(s) {sorted(unknown)}; allowed: {sorted(DEFAULT_PROFILE)}")
    prof = {**DEFAULT_PROFILE, **raw}
    if prof["timezone"] is not None:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(prof["timezone"])
        except Exception:
            raise SetupError(f"{path.name}: timezone {prof['timezone']!r} is not an IANA name like 'America/Chicago'")
    if not isinstance(prof["answer_key_words"], list) or not all(isinstance(w, str) for w in prof["answer_key_words"]):
        raise SetupError(f"{path.name}: answer_key_words must be a list of strings")
    return prof


def _read_switches(path):
    raw = _read_json(path, "switches file")
    if not isinstance(raw, dict):
        raise SetupError(f"{path} must be a JSON object like {json.dumps(DEFAULT_SWITCHES)}")
    unknown = set(raw) - set(DEFAULT_SWITCHES)
    if unknown:
        raise SetupError(f"{path}: unknown setting(s) {sorted(unknown)}; allowed: {sorted(DEFAULT_SWITCHES)}")
    for k, v in raw.items():
        if not isinstance(v, bool):
            raise SetupError(f"{path}: {k} must be true or false, got {json.dumps(v)}")
    return raw


def load_switches(path=None):
    """Switches, layered: safe code defaults <- shipped canvas-config.json <- local/canvas-config.json.

    With `path`, only that one file is layered over the code defaults. Missing files are skipped."""
    out = dict(DEFAULT_SWITCHES)
    for p in ([Path(path)] if path else switch_sources()):
        if p.exists():
            out.update(_read_switches(p))
    return out


def name_key(text):
    """Compare course names loosely: case, spaces, punctuation and a leading @ don't matter.
    'AP Physics 2', 'ap-physics-2' and '@AP_Physics2' all give 'apphysics2'."""
    return re.sub(r"[^0-9a-z]", "", str(text).lower())


def course_names(course):
    """Every name a course answers to: alias, nicknames and exact Canvas title."""
    return [course["alias"], *course.get("nicknames", []), course["name"]]


def load_roster(path=None):
    """courses.json: alias -> {alias, id, name, nicknames?, local_project?, pdf_prefix?}. Missing file = empty.

    Rejects a roster where any name (alias, nickname or title) would point to two courses."""
    path = Path(path or roster_path())
    if not path.exists():
        return {}
    raw = _read_json(path, "course roster")
    courses = raw.get("courses") if isinstance(raw, dict) else None
    if not isinstance(courses, list):
        raise SetupError(f"{path.name} must look like {{\"courses\": [{{\"alias\": ..., \"id\": ..., \"name\": ...}}]}}")
    out, owner = {}, {}
    for c in courses:
        if not isinstance(c, dict) or not all(k in c for k in ("alias", "id", "name")):
            raise SetupError(f"{path.name}: every course needs alias, id and name")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", str(c["alias"])):
            raise SetupError(f"{path.name}: alias {c['alias']!r} must be letters, digits or _ (starting with a letter)")
        if c["alias"] in out:
            raise SetupError(f"{path.name}: alias @{c['alias']} is used twice")
        nicks = c.get("nicknames", [])
        if not isinstance(nicks, list) or not all(isinstance(n, str) and name_key(n) for n in nicks):
            raise SetupError(f"{path.name}: @{c['alias']} nicknames must be a list of names, e.g. [\"AP\", \"AP Physics\"]")
        for n in course_names(c):
            other = owner.setdefault(name_key(n), c["alias"])
            if other != c["alias"]:
                raise SetupError(f"{path.name}: the name {n!r} would mean both @{other} and @{c['alias']}; "
                                 "give it to one course only")
        out[c["alias"]] = c
    return out


def resolve_course(text, roster):
    """Map what the user calls a class to roster aliases.

    Returns (matches, candidates): `matches` holds the one alias whose alias, nickname or
    title equals the text (ignoring case, spaces and punctuation), or is empty;
    `candidates` lists aliases with a name that contains the text or is contained in it,
    for a helpful "did you mean" when nothing matched exactly."""
    key = name_key(text)
    if not key:
        return [], []
    matches = [a for a, c in roster.items() if any(name_key(n) == key for n in course_names(c))]
    candidates = [a for a, c in roster.items() if a not in matches and any(
        key in name_key(n) or name_key(n) in key for n in course_names(c) if name_key(n))]
    return matches, candidates


def project_dir(course, profile=None):
    """A course's local project folder, or None. Relative paths resolve against projects_root."""
    proj = course.get("local_project")
    if not proj:
        return None
    p = Path(proj).expanduser()
    if not p.is_absolute():
        root = Path((profile or load_profile())["projects_root"]).expanduser()
        p = root / p
    return p.resolve()
