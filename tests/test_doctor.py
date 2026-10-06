import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from canvas_harness import doctor  # noqa: E402

TOKEN = "fake~doctor~token~987"


class Doctor(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.secrets = self.d / "secrets"
        (self.d / "chemistry").mkdir()
        (self.d / "courses.json").write_text(json.dumps({"courses": [
            {"alias": "chem", "id": 1001, "name": "Chemistry 101 Fall", "local_project": str(self.d / "chemistry")}]}))
        (self.d / "profile.json").write_text(json.dumps({"timezone": "America/Chicago"}))
        self.env = mock.patch.dict(os.environ, {"CANVAS_HARNESS_LOCAL": str(self.d),
                                                "CANVAS_HARNESS_ENV": str(self.secrets)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_doctor(self, secrets_text):
        self.secrets.write_text(secrets_text)
        os.chmod(self.secrets, 0o600)
        out = io.StringIO()
        fake_request = mock.Mock(return_value={"name": "Test Teacher"})
        with redirect_stdout(out):
            rc = doctor.run(request=fake_request)
        return rc, out.getvalue()

    def test_all_set_and_never_prints_token(self):
        rc, out = self.run_doctor(f"CANVAS_BASE_URL=https://x.instructure.com\nCANVAS_API_TOKEN={TOKEN}\n"
                                  "CANVAS_COURSE_IDS=1001\n")
        self.assertEqual(rc, 0, out)
        self.assertIn("token works for Test Teacher", out)
        self.assertIn("All set.", out)
        self.assertNotIn(TOKEN, out)

    def test_course_not_in_allowlist_is_todo(self):
        rc, out = self.run_doctor(f"CANVAS_BASE_URL=https://x.instructure.com\nCANVAS_API_TOKEN={TOKEN}\n")
        self.assertEqual(rc, 1)
        self.assertIn("[TODO] CANVAS_COURSE_IDS", out)
        self.assertIn("add 1001 to CANVAS_COURSE_IDS", out)
        self.assertNotIn(TOKEN, out)

    def test_loose_permissions_warn(self):
        self.secrets.write_text("CANVAS_BASE_URL=https://x.instructure.com\n")
        os.chmod(self.secrets, 0o644)
        out = io.StringIO()
        with redirect_stdout(out):
            doctor.run(offline=True)
        self.assertIn("chmod 600", out.getvalue())


if __name__ == "__main__":
    unittest.main()
