import json
import os
import subprocess
import sys
import unittest

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guard_approvals.py")


def run(tool, inp):
    out = subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_name": tool, "tool_input": inp}),
                         capture_output=True, text=True).stdout
    return "deny" if '"deny"' in out else "allow"


class GuardApprovals(unittest.TestCase):
    def test_edit_tools(self):
        self.assertEqual(run("Edit", {"file_path": "/r/local/canvas-config.json"}), "deny")
        self.assertEqual(run("Write", {"file_path": "/r/local/plans/x/plan.json.approved"}), "deny")
        self.assertEqual(run("Write", {"file_path": "/r/templates/canvas-config.example.json"}), "allow")
        self.assertEqual(run("Write", {"file_path": "/r/local/plans/x/plan.json"}), "allow")

    def test_bash(self):
        for cmd in ["echo '{}' > local/canvas-config.json",
                    "sed -i '' s/false/true/ local/canvas-config.json",
                    "cat local/canvas-config.json | tee local/canvas-config.json",
                    "cp /tmp/x local/plans/a/plan.json.approved",
                    "python3 -c 'open(\"p.approved\",\"w\")'"]:
            self.assertEqual(run("Bash", {"command": cmd}), "deny", cmd)
        for cmd in ["cat local/canvas-config.json", "ls local/plans/a/plan.json.approved",
                    "bin/canvas-harness config", "bin/canvas-harness apply local/plans/a/plan.json"]:
            self.assertEqual(run("Bash", {"command": cmd}), "allow", cmd)

    def test_bad_input_fails_closed(self):
        out = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True, text=True).stdout
        self.assertIn('"deny"', out)


if __name__ == "__main__":
    unittest.main()
