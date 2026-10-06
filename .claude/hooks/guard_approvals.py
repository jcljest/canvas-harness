#!/usr/bin/env python3
"""PreToolUse guard: Claude must not change the files that decide what gets approved.

- canvas-config.json: auto_approve / auto_publish switches. Only the user edits it.
- *.approved: approval stamps. Only `canvas-export approve` (typed by the user)
  or an auto-approval inside `canvas-export apply` writes them.

File-editing tools are also blocked by permissions.deny in settings.json. For
Bash, read-only commands (cat, head, ls, stat, wc, git diff/log/show/status)
are allowed; anything else that names a protected file is denied. This is
pattern-based: it stops accidents and casual workarounds, not a determined
bypass. Test with: python3 -m unittest discover -s .claude/hooks/tests
"""
import json
import re
import sys

PROTECTED = re.compile(r"canvas-config\.json|\.approved\b")
READ_ONLY = re.compile(r"^\s*(cat|head|tail|less|ls|stat|wc|git\s+(diff|log|show|status))\b[^;&|<>`$()]*$")
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
MESSAGE = ("{name} is user-only: it decides what gets approved and published. "
           "Ask the user to change it themselves; read switches with `bin/canvas-export config`.")


def decide(event):
    """Return a deny reason, or None to allow."""
    tool, inp = event.get("tool_name", ""), event.get("tool_input") or {}
    if tool in EDIT_TOOLS:
        target = str(inp.get("file_path") or inp.get("notebook_path") or "")
        m = PROTECTED.search(target)
        if m:
            return MESSAGE.format(name=m.group(0))
    elif tool == "Bash":
        cmd = str(inp.get("command", ""))
        m = PROTECTED.search(cmd)
        if m and not READ_ONLY.match(cmd):
            return MESSAGE.format(name=m.group(0))
    return None


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        event = None
    reason = "guard_approvals: could not parse hook input" if event is None else decide(event)
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))


if __name__ == "__main__":
    main()
