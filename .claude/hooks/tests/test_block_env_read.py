"""Fixture tests for hooks/block_env_read.py (and its block-env-read.sh wrapper).

Run: python3 -m unittest discover -s .claude/hooks/tests -v
Each case feeds hook-input JSON on stdin, exactly as Claude Code does.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_HOOK = os.path.join(HOOKS, "block_env_read.py")
SH_HOOK = os.path.join(HOOKS, "block-env-read.sh")


def run_hook(tool_name, tool_input, hook=PY_HOOK, raw=None, cwd=None):
    stdin = raw if raw is not None else json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    cmd = ["bash", hook] if hook.endswith(".sh") else ["python3", hook]
    proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True, cwd=cwd, timeout=20)
    assert proc.returncode == 0, proc.stderr
    if not proc.stdout.strip():
        return "allow"
    out = json.loads(proc.stdout)
    return out["hookSpecificOutput"]["permissionDecision"]


class ShellCommands(unittest.TestCase):
    BLOCK = [
        "cat .env",
        "cat ./.env",
        "cat /Users/x/proj/.env",
        "cat .env.local",
        "cat .env.production",
        "cat .envrc",
        "source .env && echo done",
        "set -a; . ./.env; set +a",
        "cp .env /tmp/x",
        "docker compose --env-file .env up",
        "cat .en*",
        "cat .en?",
        "cat .e*",
        "cat .*",
        "cat [.]env",
        "cat .{env,x}",
        "find . -name '*.env'",
        "find . -name '*env*' -print",
        "python3 -c \"print(open('.'+'env').read())\"",
        "python3 -c \"open('.e' 'nv')\"",
        "python3 -c \"open('.'+'e'+'n'+'v')\"",
        "python3 -c \"open(chr(46)+'env')\"",
        "printenv",
        "printenv DB_PASS",
        "env",
        "env | grep TOKEN",
        "docker exec api env",
        "env -0",
        "export -p",
        "declare -px",
        "set",
        "set | grep KEY",
        "docker compose config",
        "docker-compose config",
        "docker compose -f compose.yml config",
        "docker inspect nv-live-api-2",
        "docker container inspect api",
        "cat /proc/1/environ",
        "ps eww",
        "python3 -c \"import os; print(os.environ)\"",
        "python3 -c \"import os; print(os.getenv('X'))\"",
        "node -e \"console.log(process.env)\"",
        "python3 -c \"from dotenv import dotenv_values; print(dotenv_values())\"",
        "echo $CANVAS_TOKEN",
        "echo \"${DB_PASS}\"",
        "curl -H \"Authorization: Bearer $API_KEY\" https://x",
        "psql $DATABASE_URL",
        "grep -r PASSWORD slawek/",
        "grep -rn secret .",
        "grep -R token /Users/x/proj",
        "grep --recursive key .",
        "rg --hidden PASSWORD",
        "rg -uu token .",
        "find . -type f -exec cat {} +",
        "find . -type f | xargs grep KEY",
    ]
    ALLOW = [
        "ls -la",
        "cat .env.example",
        "cp .env.example .env.example.bak",
        "cat .env.sample",
        "cat .envrc.example",
        "source .venv/bin/activate",
        "python3 -m venv .venv",
        "ls *.py",
        "ls *",
        "git status",
        "git grep -n TODO",
        "grep -n foo file.py",
        "grep -rn foo . --exclude='.env*'",
        "rg foo src/",
        "rg -g '!.env*' --hidden foo",
        "python3 -c \"print('a.b'.split('.'))\"",
        "set -euo pipefail",
        "/usr/bin/env python3 script.py",
        "env FOO=1 python3 script.py",
        "conda env list",
        "docker compose up -d",
        "docker compose logs api --tail=50",
        "echo $HOME $PWD $PATH",
        "python3 profile_data.py",
        "find . -name '*.py'",
        "find . -name '*.py' -exec wc -l {} +",
        "cat app.env.py",
    ]

    def test_blocked(self):
        for cmd in self.BLOCK:
            with self.subTest(cmd=cmd):
                self.assertEqual(run_hook("Bash", {"command": cmd}), "deny")

    def test_allowed(self):
        for cmd in self.ALLOW:
            with self.subTest(cmd=cmd):
                self.assertEqual(run_hook("Bash", {"command": cmd}), "allow")

    def test_monitor_uses_command(self):
        self.assertEqual(run_hook("Monitor", {"command": "tail -f .env"}), "deny")
        self.assertEqual(run_hook("Monitor", {"command": "tail -f app.log"}), "allow")


class FileTools(unittest.TestCase):
    def test_read(self):
        self.assertEqual(run_hook("Read", {"file_path": "/p/.env"}), "deny")
        self.assertEqual(run_hook("Read", {"file_path": "/p/.env.local"}), "deny")
        self.assertEqual(run_hook("Read", {"file_path": "/p/.envrc"}), "deny")
        self.assertEqual(run_hook("Read", {"file_path": "/proc/self/environ"}), "deny")
        self.assertEqual(run_hook("Read", {"file_path": "/p/.env.example"}), "allow")
        self.assertEqual(run_hook("Read", {"file_path": "/p/.venv/lib/x.py"}), "allow")
        self.assertEqual(run_hook("Read", {"file_path": "/p/config/environment.py"}), "allow")

    def test_write_and_edit(self):
        for tool in ("Write", "Edit", "MultiEdit"):
            with self.subTest(tool=tool):
                self.assertEqual(run_hook(tool, {"file_path": "/p/.env", "content": "X=1"}), "deny")
                self.assertEqual(run_hook(tool, {"file_path": "/p/.env.production"}), "deny")
                self.assertEqual(run_hook(tool, {"file_path": "/p/.env.example"}), "allow")
        # Mentioning .env in *content* (e.g. a .gitignore or docs) is fine.
        self.assertEqual(run_hook("Write", {"file_path": "/p/.gitignore", "content": ".env\n"}), "allow")
        self.assertEqual(run_hook("NotebookEdit", {"notebook_path": "/p/.env"}), "deny")

    def test_unknown_tools_check_paths_and_code(self):
        self.assertEqual(run_hook("mcp__fs__read_file", {"path": "/p/.env"}), "deny")
        self.assertEqual(run_hook("mcp__ide__executeCode", {"code": "import os; print(os.environ)"}), "deny")
        self.assertEqual(run_hook("mcp__ide__executeCode", {"code": "print(1+1)"}), "allow")
        self.assertEqual(run_hook("WebFetch", {"url": "https://example.com", "prompt": "x"}), "allow")


class GrepTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.with_secret = os.path.join(self.tmp.name, "proj")
        self.clean = os.path.join(self.tmp.name, "clean")
        os.makedirs(os.path.join(self.with_secret, "sub"))
        os.makedirs(self.clean)
        # Dummy secret file created by the test itself (no real values).
        with open(os.path.join(self.with_secret, "sub", ".env"), "w") as f:
            f.write("DUMMY=1\n")
        with open(os.path.join(self.with_secret, "a.py"), "w") as f:
            f.write("x = 1\n")
        with open(os.path.join(self.clean, "a.py"), "w") as f:
            f.write("x = 1\n")

    def tearDown(self):
        self.tmp.cleanup()

    def g(self, **tool_input):
        return run_hook("Grep", dict(pattern="x", **tool_input))

    def test_direct_targets(self):
        self.assertEqual(self.g(path="/p/.env"), "deny")
        self.assertEqual(self.g(path=self.clean, glob=".env*"), "deny")
        self.assertEqual(self.g(path=self.clean, glob="**/.env.local"), "deny")
        self.assertEqual(self.g(path=self.clean, glob="*"), "allow")

    def test_directory_scan(self):
        self.assertEqual(self.g(path=self.with_secret), "deny")
        self.assertEqual(self.g(path=self.clean), "allow")
        self.assertEqual(self.g(path=self.with_secret, glob="*.py"), "allow")
        self.assertEqual(self.g(path=self.with_secret, type="py"), "allow")
        self.assertEqual(self.g(path=self.with_secret, glob="!**/.env*"), "allow")
        self.assertEqual(self.g(path=self.with_secret, glob="!*.md"), "deny")

    def test_default_path_is_cwd(self):
        self.assertEqual(run_hook("Grep", {"pattern": "x"}, cwd=self.with_secret), "deny")
        self.assertEqual(run_hook("Grep", {"pattern": "x"}, cwd=self.clean), "allow")


class Robustness(unittest.TestCase):
    def test_fails_closed_on_bad_input(self):
        self.assertEqual(run_hook(None, None, raw="not json"), "deny")
        self.assertEqual(run_hook(None, None, raw="[]"), "deny")

    @unittest.skipUnless(os.path.exists(SH_HOOK), "this repo calls block_env_read.py directly")
    def test_shell_wrapper_delegates(self):
        self.assertEqual(run_hook("Read", {"file_path": "/p/.env"}, hook=SH_HOOK), "deny")
        self.assertEqual(run_hook("Read", {"file_path": "/p/README.md"}, hook=SH_HOOK), "allow")

    def test_unrelated_tools_allowed(self):
        self.assertEqual(run_hook("Glob", {"pattern": "**/*.py"}), "allow")
        self.assertEqual(run_hook("Agent", {"prompt": "summarise README"}), "allow")


if __name__ == "__main__":
    unittest.main()
