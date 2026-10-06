#!/usr/bin/env python3
"""PreToolUse guard: keep real secret files (.env, .env.*, .envrc) and
environment-variable values out of Claude's context.

Only the human owner creates, fills in, or reads real secret files. This hook
denies any tool call that would read, search, copy, write, or print them.
Template files (.env.example, .env.sample, .env.template, .env.dist) stay
readable and writable.

Fails closed: if the hook input can't be parsed, the tool call is denied.

This is a pattern-matching guard, not a sandbox. It raises the bar and
catches accidents and common workarounds; the CLAUDE.md "Secrets and .env
files" rule still governs anything it can't see (e.g. a script file that
prints a secret). Test with: python3 -m unittest discover hooks/tests
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from typing import Iterable, List, Optional

TEMPLATE_SUFFIXES = {"example", "sample", "template", "dist", "defaults"}

# Names a glob is tested against to decide whether it could expand to a
# secret file.
SECRET_PROBE_NAMES = [
    ".env",
    ".envrc",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.prod",
]

# ".env" / ".envrc" optionally followed by ".suffix" parts, not glued to a
# preceding name character (so ".venv", "os.environ", "process.env" and
# "app.env" don't match).
_SECRET_NAME_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])\.env(?:rc)?((?:\.[A-Za-z0-9_-]+)*)(?![A-Za-z0-9_.-])"
)

# Commands / expressions that print environment variables or config with
# secrets interpolated. Checked only for shell/code tools.
_ENV_DUMP_PATTERNS = [
    (r"\bprintenv\b", "printenv"),
    (r"(?:^|[;&|(`]|\$\(|\s)env\s*(?:$|[;&|>)`])", "bare `env`"),
    (r"\benv\s+(?:-0|--null|-u\b)", "env dump"),
    (r"\bexport\s+-p\b", "export -p"),
    (r"\b(?:declare|typeset)\s+-[A-Za-z]*[px]", "declare -p/-x"),
    (r"(?:^|[;&|(]\s*)set\s*(?:$|[;&|>)])", "bare `set`"),
    (r"\bcompgen\s+-[ev]\b", "compgen -v"),
    (r"\bdocker(?:-compose|\s+compose)\b[^;&|]*\s(?:config|convert)\b", "docker compose config"),
    (r"\bdocker\s+(?:container\s+|image\s+)?inspect\b", "docker inspect"),
    (r"\bkubectl\b[^;&|]*\bget\s+secrets?\b", "kubectl get secret"),
    (r"/proc/[^\s]*/environ\b", "/proc/*/environ"),
    (r"\bps\s+(?:[A-Za-z]*e[A-Za-z]*w|-[A-Za-z]*E)", "ps with environment"),
    (r"\bos\.environ\b|\bos\.getenv\b|\bgetenv\s*\(", "reading env vars in inline code"),
    (r"\bprocess\.env\b|\bENV\s*\[|\$ENV\s*\{", "reading env vars in inline code"),
    (r"\bdotenv(?:_values)?\b|\bload_dotenv\b|\bdirenv\s+(?:exec|export|dump)\b", "dotenv loader in inline code"),
]
_ENV_DUMP_RES = [(re.compile(p), label) for p, label in _ENV_DUMP_PATTERNS]

# $VAR / ${VAR} references whose names look like secrets.
_SECRET_VAR_RE = re.compile(
    r"\$\{?[A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|_PASS|PASS_|CREDENTIAL|DSN|DB_URI|DATABASE_URL|PRIVATE)[A-Za-z0-9_]*\}?",
    re.IGNORECASE,
)

# Building a dotfile name from pieces: '.'+'env', ".e" "nv", '.'+'e'+'n'+'v'.
# Squashing quotes/joiners and re-checking catches these without flagging
# ordinary code like split('.').
_JOINER_RE = re.compile(r"""['"+,\s]""")
# Escape codes for "." used near "env"/"nv": \x2e, \056, ., chr(46), &#46;
_DOT_ESCAPE_RE = re.compile(r"\\x2e|\\056|\\u002e|chr\(\s*46\s*\)|&#0*46;", re.IGNORECASE)

_RECURSIVE_GREP_RE = re.compile(
    r"(?<!git )\b(?:e|f)?grep\b[^;&|]*?(?:\s-[A-Za-z]*[rR][A-Za-z]*\b|\s--recursive\b|\s-d\s*recurse\b|\s--directories=recurse\b)"
)
_HIDDEN_SEARCH_RE = re.compile(
    r"\b(?:rg|ag|ack|ugrep)\b[^;&|]*?(?:\s--hidden\b|\s-[A-Za-z]*uu|\s-\.(?:\s|$)|\s--no-ignore-dot\b|\s--unrestricted\b)"
)
_FIND_EXEC_READ_RE = re.compile(
    r"\bfind\b[^;&|]*(?:-exec(?:dir)?|\|\s*xargs)\s+[^;&|]*\b(?:cat|head|tail|less|more|grep|rg|sed|awk|strings|xxd|od|hexdump|base64|cp|tar|zip|python3?|node|perl|ruby)\b"
)
# Search-exclusion arguments are fine to mention secret names in.
_EXCLUDE_ARG_RE = re.compile(
    r"""--exclude(?:-dir)?=(?:'[^']*'|"[^"]*"|\S+)|(?:-g|--glob|--iglob)\s*(?:'![^']*'|"![^"]*"|!\S+)"""
)
_GLOB_TOKEN_RE = re.compile(r"""[^\s'"`;&|()<>=]*[*?\[{][^\s'"`;&|()<>=]*""")

SHELL_TOOLS = {"Bash", "Monitor", "PowerShell"}
PATH_TOOLS = {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "NotebookRead"}
CODE_KEYS = ("command", "code", "script", "cmd")
PATH_KEYS = ("file_path", "notebook_path", "path", "paths", "filename", "file", "files", "uri")


def is_template_suffix(suffix: str) -> bool:
    """suffix is the ".a.b" tail after .env/.envrc (may be empty)."""
    parts = [p.lower() for p in suffix.split(".") if p]
    return any(p in TEMPLATE_SUFFIXES for p in parts)


def find_secret_names(text: str) -> List[str]:
    hits = []
    for m in _SECRET_NAME_RE.finditer(text):
        if not is_template_suffix(m.group(1)):
            hits.append(m.group(0))
    return hits


def glob_could_match_secret(pattern: str) -> bool:
    """True if a glob's last path component could expand to a secret file."""
    base = pattern.rstrip("/").split("/")[-1]
    if not base or base.startswith("!"):
        return False
    # A bare "*" / "**" / "?" doesn't match dotfiles in the shell and is
    # too common to block; anything with a literal character is tested.
    if not re.search(r"[^*?\[\]{}]", base):
        return False
    for alt in expand_braces(base):
        for name in SECRET_PROBE_NAMES:
            if fnmatch.fnmatchcase(name, alt):
                return True
    return False


def expand_braces(pattern: str) -> List[str]:
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    out: List[str] = []
    for option in m.group(1).split(","):
        out.extend(expand_braces(pattern[: m.start()] + option + pattern[m.end():]))
    return out


def check_shell(command: str) -> Optional[str]:
    names = find_secret_names(_EXCLUDE_ARG_RE.sub(" ", command))
    if names:
        return f"references secret file {names[0]!r}"
    scrubbed = _EXCLUDE_ARG_RE.sub(" ", command)
    for token in _GLOB_TOKEN_RE.findall(scrubbed):
        if glob_could_match_secret(token):
            return f"glob {token!r} could expand to a secret file"
    for rx, label in _ENV_DUMP_RES:
        if rx.search(command):
            return f"prints environment variables or interpolated config ({label})"
    m = _SECRET_VAR_RE.search(command)
    if m:
        return f"references secret-looking variable {m.group(0)!r}"
    if find_secret_names(_JOINER_RE.sub("", scrubbed)):
        return "builds a secret file name from pieces"
    if _DOT_ESCAPE_RE.search(command) and "nv" in command.lower():
        return "builds a file name from escape codes"
    if _RECURSIVE_GREP_RE.search(command) and not _mentions_env_exclude(command):
        return "recursive grep would read secret files; use the Grep tool, `rg` (skips dotfiles), or add --exclude='.env*'"
    if _HIDDEN_SEARCH_RE.search(command) and not _mentions_env_exclude(command):
        return "searching hidden files would read secret files"
    if _FIND_EXEC_READ_RE.search(command):
        return "find/xargs piping file contents could read secret files"
    return None


def _mentions_env_exclude(command: str) -> bool:
    return any(".env" in arg for arg in _EXCLUDE_ARG_RE.findall(command))


def check_path_value(value: str) -> Optional[str]:
    names = find_secret_names(value)
    if names:
        return f"targets secret file {names[0]!r}"
    if "/proc/" in value and value.rstrip("/").endswith("environ"):
        return "targets a process environment file"
    return None


SCAN_PRUNE_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", "dist", "build", ".next", ".tox"}
SCAN_LIMIT = 50000


def tree_has_secret_file(root: str) -> Optional[bool]:
    """True/False if the tree under root does/doesn't hold a secret file;
    None if the scan hit SCAN_LIMIT before finishing."""
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SCAN_PRUNE_DIRS]
        for name in filenames:
            seen += 1
            if find_secret_names("/" + name):
                return True
        seen += len(dirnames)
        if seen > SCAN_LIMIT:
            return None
    return False


def glob_excludes_secrets(pattern: str) -> bool:
    """A negated glob like '!**/.env*' that removes every secret probe name."""
    if not pattern.startswith("!"):
        return False
    base = pattern[1:].rstrip("/").split("/")[-1]
    return all(
        any(fnmatch.fnmatchcase(name, alt) for alt in expand_braces(base))
        for name in SECRET_PROBE_NAMES
    )


def check_grep(tool_input: dict) -> Optional[str]:
    path = tool_input.get("path")
    glob = tool_input.get("glob")
    if isinstance(path, str) and path:
        reason = check_path_value(path)
        if reason:
            return reason
    if isinstance(glob, str) and glob:
        if glob_excludes_secrets(glob):
            return None
        if not glob.startswith("!"):
            if find_secret_names(glob) or glob_could_match_secret(glob):
                return f"glob {glob!r} could match a secret file"
            return None  # a positive glob that can't match secrets narrows the search safely
    if tool_input.get("type"):
        return None  # ripgrep file types (py, js, ...) never include dotenv files
    # Unrestricted search: the built-in Grep searches hidden files, so check
    # whether the search root actually contains one.
    root = path if isinstance(path, str) and path else os.getcwd()
    if os.path.isfile(root):
        return None
    if not os.path.isdir(root):
        return None
    found = tree_has_secret_file(root)
    advice = "add glob '!**/.env*' or narrow the path/type"
    if found:
        return f"search under {root!r} would include a secret file; {advice}"
    if found is None:
        return f"search under {root!r} is too large to rule out secret files; {advice}"
    return None


def iter_strings(value) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)


def evaluate(tool_name: str, tool_input: dict) -> Optional[str]:
    """Return a denial reason, or None to allow."""
    if tool_name in SHELL_TOOLS:
        for key in CODE_KEYS:
            value = tool_input.get(key)
            if isinstance(value, str):
                reason = check_shell(value)
                if reason:
                    return reason
        return None
    if tool_name == "Grep":
        return check_grep(tool_input)
    if tool_name in PATH_TOOLS:
        for key in PATH_KEYS:
            for value in iter_strings(tool_input.get(key)):
                reason = check_path_value(value)
                if reason:
                    return reason
        return None
    # Any other tool (MCP filesystem/code runners, etc.): check path-like and
    # code-like fields.
    for key in PATH_KEYS:
        for value in iter_strings(tool_input.get(key)):
            reason = check_path_value(value)
            if reason:
                return reason
    for key in CODE_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str):
            reason = check_shell(value)
            if reason:
                return reason
    return None


def deny(reason: str) -> None:
    message = (
        f"Blocked by secret-file guard: {reason}. Real .env/.env.*/.envrc files and "
        "environment-variable values are human-only (see CLAUDE.md 'Secrets and .env "
        "files'). Use the .env.example template, or ask the human to confirm a value "
        "is set without showing it."
    )
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": message,
            }
        },
        sys.stdout,
    )


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "null")
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
        tool_name = str(payload.get("tool_name") or "")
        tool_input = payload.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            raise ValueError("tool_input is not an object")
    except Exception as exc:  # fail closed
        print(f"block_env_read: unparseable input: {exc}", file=sys.stderr)
        deny("hook input could not be parsed, so the call was denied")
        return 0
    reason = evaluate(tool_name, tool_input)
    if reason:
        deny(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
