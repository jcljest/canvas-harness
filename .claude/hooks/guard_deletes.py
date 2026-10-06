#!/usr/bin/env python3
"""PreToolUse guard for Bash: Claude never deletes files without the user saying so.

- DENY outright (catastrophic or unrecoverable):
  recursive rm of /, ~, $HOME, ., .., *, .git, local/, the repo itself, any
  path outside the project (except temp folders), or a target built from a
  $variable or `command`; `git clean` with -x/-X (it would wipe .env and local/).
- ASK the user (shown as a permission prompt, even in auto mode):
  any other rm / rmdir / unlink / shred, find -delete or -exec rm, git clean,
  git rm, and Python/Node one-liners that delete (rmtree, os.remove, unlink, fs.rm).
- Everything else is allowed.

Pattern-based: it catches mistakes and common forms, not a determined bypass.
Test with: python3 -m unittest discover -s .claude/hooks/tests
"""
import json
import os
import re
import shlex
import sys

TEMP_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/", "/private/var/folders/")
SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|&\n]")
CODE_DELETE = re.compile(r"\b(shutil\.rmtree|os\.(remove|unlink|rmdir|removedirs)|\.unlink\(|\.rmdir\(|"
                         r"fs\.(rm|rmSync|unlink|unlinkSync|rmdir|rmdirSync)|send2trash)\b")
DANGEROUS_NAMES = {"/", "/*", "~", "~/", "~/*", ".", "./", "./*", "..", "../", "../*", "*", ".*",
                   ".git", ".git/", "local", "local/", "local/*", ".claude", ".claude/"}


def _project_dir():
    return os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def _words(segment):
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def _strip_prefix(words):
    """Drop sudo/env/command/xargs-style wrappers and VAR=value assignments."""
    while words and (words[0] in ("sudo", "command", "builtin", "nohup", "time", "xargs", "exec")
                     or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0])):
        words = words[1:]
        while words and words[0].startswith("-") and len(words) > 1:  # wrapper flags, e.g. xargs -0
            words = words[1:]
    return words


def _outside_project(target, project):
    if target.startswith("~") or target.startswith("$HOME"):
        return True
    path = os.path.realpath(os.path.join(project, target))
    if any(path.startswith(p) for p in TEMP_PREFIXES) or any((path + "/").startswith(p) for p in TEMP_PREFIXES):
        return False
    return path != project and not path.startswith(project + os.sep)


def _rm_verdict(args, project, raw_segment):
    flags = [a for a in args if a.startswith("-") and a != "-"]
    targets = [a for a in args if not a.startswith("-") or a == "-"]
    recursive = any(f in ("--recursive",) or (not f.startswith("--") and re.search(r"[rR]", f)) for f in flags)
    if recursive:
        if "$" in raw_segment or "`" in raw_segment:
            return "deny", "recursive delete with a $variable or `command` target; spell out the path"
        for t in targets:
            clean = (t[2:] if t.startswith("./") and len(t) > 2 else t).rstrip("/") or "/"
            if t in DANGEROUS_NAMES or clean in DANGEROUS_NAMES:
                return "deny", f"recursive delete of {t!r} is never allowed (local/ holds the user's courses, plans and uploads)"
            if os.path.realpath(os.path.join(project, t)) == project:
                return "deny", "recursive delete of the whole project is never allowed"
            if _outside_project(t, project):
                return "deny", f"recursive delete outside the project ({t!r})"
    return "ask", "deletes " + (", ".join(targets) if targets else "files")


def decide(command, project=None):
    """Return ("allow"|"ask"|"deny", reason)."""
    project = project or _project_dir()
    worst = ("allow", "")
    rank = {"allow": 0, "ask": 1, "deny": 2}
    if CODE_DELETE.search(command):
        worst = ("ask", "code that deletes files")
    for segment in SEGMENT_SPLIT.split(command):
        words = _strip_prefix(_words(segment.strip()))
        if not words:
            continue
        cmd, args = os.path.basename(words[0]), words[1:]
        verdict = None
        if cmd == "rm":
            verdict = _rm_verdict(args, project, segment)
        elif cmd in ("rmdir", "unlink", "shred", "srm"):
            verdict = ("ask", f"{cmd} {' '.join(args)}".strip())
        elif cmd == "find" and ("-delete" in args or ("-exec" in args and any(a in ("rm", "/bin/rm") for a in args))):
            root = next((a for a in args if not a.startswith("-")), ".")
            filtered = any(a in ("-name", "-iname", "-path", "-ipath", "-regex", "-iregex") for a in args)
            if root in ("/", "~", "~/") or _outside_project(root, project):
                verdict = ("deny", f"find ... -delete from {root!r} is never allowed")
            elif not filtered:
                verdict = ("deny", f"find {root} -delete with no -name/-path filter would delete everything")
            else:
                verdict = ("ask", f"find {root} deletes matching files")
        elif cmd == "git" and args[:1] == ["clean"]:
            if any(re.match(r"-[a-zA-Z]*[xX]", a) for a in args[1:]):
                verdict = ("deny", "git clean -x/-X would delete ignored files such as the secrets file and local/")
            else:
                verdict = ("ask", "git clean deletes untracked files")
        elif cmd == "git" and args[:1] == ["rm"]:
            verdict = ("ask", "git rm " + " ".join(args[1:]))
        if verdict and rank[verdict[0]] > rank[worst[0]]:
            worst = verdict
    return worst


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        event = None
    if event is None:
        decision, reason = "deny", "could not parse hook input"
    elif event.get("tool_name") != "Bash":
        return
    else:
        decision, reason = decide(str((event.get("tool_input") or {}).get("command", "")))
    if decision == "allow":
        return
    prefix = "Blocked by delete guard: " if decision == "deny" else "Delete guard: confirm before Claude "
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                             "permissionDecisionReason": prefix + reason}}))


if __name__ == "__main__":
    main()
