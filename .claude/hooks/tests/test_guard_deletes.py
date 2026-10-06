import json
import os
import subprocess
import sys
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HOOKS)

import guard_deletes as gd  # noqa: E402

PROJECT = "/work/canvas-harness"


def verdict(cmd):
    return gd.decide(cmd, project=PROJECT)[0]


class GuardDeletes(unittest.TestCase):
    def test_deny_catastrophic(self):
        for cmd in ["rm -rf /", "rm -rf ~", "rm -rf ~/", "sudo rm -rf /*", "rm -fr ..", "rm -R .",
                    "rm -rf .git", "rm -rf local", "rm -rf ./local/", "rm -rf *", "rm -rf $HOME",
                    'rm -rf "$DIR"', "rm -rf `pwd`", "rm -rf /Users/someone/Documents",
                    "rm --recursive /etc", f"rm -rf {PROJECT}", "git clean -fdx", "git clean -fX",
                    "echo hi && rm -rf /", "find / -delete", "find ~ -name '*.pdf' -delete",
                    "find . -delete", "find .. -name '*.py' -delete"]:
            self.assertEqual(verdict(cmd), "deny", cmd)

    def test_ask_for_ordinary_deletes(self):
        for cmd in ["rm notes.txt", "rm -f local/plans/a/plan.json.preview.html", "rm -r local/plans/old",
                    "rmdir empty", "unlink x", "find . -name '*.pyc' -delete", "find build -name '*.o' -exec rm {} +",
                    "git clean -fd", "git rm old.py", "python3 -c 'import shutil; shutil.rmtree(\"build\")'",
                    "python3 -c 'import os; os.remove(\"x\")'", "node -e 'fs.rmSync(\"x\")'",
                    "ls && rm a.txt", "xargs rm < list.txt"]:
            self.assertEqual(verdict(cmd), "ask", cmd)

    def test_temp_folders_are_only_ask(self):
        for cmd in ["rm -rf /tmp/build123", "rm -rf /private/tmp/claude-1/scratch", "rm -rf /var/folders/ab/T/tmpx"]:
            self.assertEqual(verdict(cmd), "ask", cmd)

    def test_allow_everything_else(self):
        for cmd in ["ls -la", "git status", "python3 -m unittest", "echo rm is a word",
                    "grep -r 'rm -rf' docs", "bin/canvas-harness preview local/plans/a/plan.json",
                    "cat removal.txt", "npm run format"]:
            self.assertEqual(verdict(cmd), "allow", cmd)

    def test_hook_protocol(self):
        def run(payload):
            return subprocess.run([sys.executable, os.path.join(HOOKS, "guard_deletes.py")], input=payload,
                                  capture_output=True, text=True, env={**os.environ, "CLAUDE_PROJECT_DIR": PROJECT}).stdout
        out = run(json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}))
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
        out = run(json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm a.txt"}}))
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertEqual(run(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})), "")
        self.assertEqual(run(json.dumps({"tool_name": "Read", "tool_input": {"file_path": "x"}})), "")
        self.assertIn('"deny"', run("not json"))


if __name__ == "__main__":
    unittest.main()
