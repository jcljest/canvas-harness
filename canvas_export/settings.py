"""Where each user's files live, and how their profile and switches are read.

Everything personal sits in one gitignored folder, `local/` in the repo
(override with $CANVAS_EXPORT_LOCAL):

    local/.env                 secrets, written only by the user with `bin/+a`
    local/profile.json         timezone, naming conventions (written by /setup)
    local/courses.json         course roster: alias -> id, exact title, project folder
    local/canvas-config.json   switches; only the user edits this file
    local/plans/               plan files
    local/uploads/<alias>/     files waiting to be uploaded

Code never hardcodes a person, school, course or path; it reads these files.
"""

import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SECRETS_NAME = ".env"
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
    return Path(os.environ.get("CANVAS_EXPORT_LOCAL") or REPO / "local").expanduser()


def secrets_path():
    return local_dir() / SECRETS_NAME


def profile_path():
    return local_dir() / "profile.json"


def roster_path():
    return local_dir() / "courses.json"


def config_path():
    return local_dir() / "canvas-config.json"


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


def load_switches(path=None):
    """canvas-config.json; a missing file means the safe defaults."""
    path = Path(path or config_path())
    if not path.exists():
        return dict(DEFAULT_SWITCHES)
    raw = _read_json(path, "switches file")
    if not isinstance(raw, dict):
        raise SetupError(f"{path.name} must be a JSON object like {json.dumps(DEFAULT_SWITCHES)}")
    unknown = set(raw) - set(DEFAULT_SWITCHES)
    if unknown:
        raise SetupError(f"{path.name}: unknown setting(s) {sorted(unknown)}; allowed: {sorted(DEFAULT_SWITCHES)}")
    for k, v in raw.items():
        if not isinstance(v, bool):
            raise SetupError(f"{path.name}: {k} must be true or false, got {json.dumps(v)}")
    return {**DEFAULT_SWITCHES, **raw}


def load_roster(path=None):
    """courses.json: alias -> {alias, id, name, local_project?, pdf_prefix?}. Missing file = empty."""
    path = Path(path or roster_path())
    if not path.exists():
        return {}
    raw = _read_json(path, "course roster")
    courses = raw.get("courses") if isinstance(raw, dict) else None
    if not isinstance(courses, list):
        raise SetupError(f"{path.name} must look like {{\"courses\": [{{\"alias\": ..., \"id\": ..., \"name\": ...}}]}}")
    out = {}
    for c in courses:
        if not isinstance(c, dict) or not all(k in c for k in ("alias", "id", "name")):
            raise SetupError(f"{path.name}: every course needs alias, id and name")
        out[c["alias"]] = c
    return out


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
