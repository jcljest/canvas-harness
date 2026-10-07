import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from canvas_harness import cli as lc  # noqa: E402

# Never touch a real local/ folder in tests.
os.environ["CANVAS_HARNESS_LOCAL"] = tempfile.mkdtemp()
os.environ["CANVAS_HARNESS_ENV"] = os.path.join(os.environ["CANVAS_HARNESS_LOCAL"], "secrets")

TOKEN = "fake~token~1234567890"
CFG = {"base": "https://school.instructure.com", "token": TOKEN, "course_ids": {"111", "222"}}


def write_secrets(text):
    fd, path = tempfile.mkstemp()
    os.write(fd, text.encode())
    os.close(fd)
    return path


class ParseSecrets(unittest.TestCase):
    def test_parses_quotes_export_comments(self):
        got = lc.parse_secrets("# c\n\nexport A=1\nB='two words'\nC=\"x=y\"\nbad line\n")
        self.assertEqual(got, {"A": "1", "B": "two words", "C": "x=y"})

    def test_load_config_reports_missing_names_only(self):
        path = write_secrets(f"CANVAS_API_TOKEN={TOKEN}\n")
        with self.assertRaises(lc.ConfigError) as cm:
            lc.load_config(path, environ={})
        self.assertIn("CANVAS_BASE_URL", str(cm.exception))
        self.assertNotIn(TOKEN, str(cm.exception))

    def test_load_config_requires_https_and_numeric_ids(self):
        path = write_secrets(f"CANVAS_BASE_URL=http://x.com\nCANVAS_API_TOKEN={TOKEN}\nCANVAS_COURSE_IDS=1\n")
        with self.assertRaises(lc.ConfigError):
            lc.load_config(path, environ={})
        path = write_secrets(f"CANVAS_BASE_URL=https://x.com/\nCANVAS_API_TOKEN={TOKEN}\nCANVAS_COURSE_IDS=1, 2 abc\n")
        with self.assertRaises(lc.ConfigError):
            lc.load_config(path, environ={})

    def test_load_config_ok(self):
        path = write_secrets(f"CANVAS_BASE_URL=https://x.com/\nCANVAS_API_TOKEN={TOKEN}\nCANVAS_COURSE_IDS=1, 2\n")
        cfg = lc.load_config(path, environ={})
        self.assertEqual(cfg["base"], "https://x.com")
        self.assertEqual(cfg["course_ids"], {"1", "2"})


class Scope(unittest.TestCase):
    def norm(self, p):
        return lc.normalize_path(p, CFG["base"])

    def test_normalize_forms(self):
        self.assertEqual(self.norm("courses/111/pages"), "/api/v1/courses/111/pages")
        self.assertEqual(self.norm("/api/v1/courses/111?x=1"), "/api/v1/courses/111?x=1")
        self.assertEqual(self.norm("https://school.instructure.com/api/v1/courses/111"), "/api/v1/courses/111")

    def test_rejects_other_host_and_dot_segments(self):
        with self.assertRaises(lc.ScopeError):
            self.norm("https://evil.example.com/api/v1/courses/111")
        with self.assertRaises(lc.ScopeError):
            self.norm("courses/111/../999/pages")

    def test_allowed_course_writes(self):
        for m in ("GET", "POST", "PUT", "DELETE"):
            lc.check_scope(m, "/api/v1/courses/111/assignments/5", CFG["course_ids"])
        lc.check_scope("PUT", "/api/v1/courses/222", CFG["course_ids"])

    def test_blocks_other_courses_and_globals(self):
        bad = [
            ("PUT", "/api/v1/courses/333/pages/x"),
            ("GET", "/api/v1/courses/1111"),
            ("POST", "/api/v1/users/self"),
            ("GET", "/api/v1/accounts/1/users"),
            ("POST", "/api/v1/conversations"),
            ("POST", "/api/v1/courses"),
            ("GET", "/api/v1/courses/abc"),
        ]
        for m, p in bad:
            with self.assertRaises(lc.ScopeError, msg=f"{m} {p}"):
                lc.check_scope(m, p, CFG["course_ids"])

    def test_new_quizzes_api(self):
        self.assertEqual(self.norm("/api/quiz/v1/courses/111/quizzes"), "/api/quiz/v1/courses/111/quizzes")
        self.assertEqual(self.norm("https://school.instructure.com/api/quiz/v1/courses/111/quizzes/5/items"),
                         "/api/quiz/v1/courses/111/quizzes/5/items")
        for m in ("GET", "POST", "PATCH", "DELETE"):
            lc.check_scope(m, "/api/quiz/v1/courses/111/quizzes/5/items", CFG["course_ids"])
        for m, p in (("POST", "/api/quiz/v1/courses/333/quizzes"), ("GET", "/api/quiz/v1/quizzes"),
                     ("GET", "/api/quiz/v2/courses/111/quizzes")):
            with self.assertRaises(lc.ScopeError, msg=f"{m} {p}"):
                lc.check_scope(m, self.norm(p), CFG["course_ids"])

    def test_read_only_self(self):
        lc.check_scope("GET", "/api/v1/users/self", CFG["course_ids"])
        lc.check_scope("GET", "/api/v1/courses?enrollment_type=teacher", CFG["course_ids"])

    def test_discover_needs_no_course_ids(self):
        path = write_secrets(f"CANVAS_BASE_URL=https://x.com\nCANVAS_API_TOKEN={TOKEN}\n")
        with self.assertRaises(lc.ConfigError):
            lc.load_config(path, environ={})
        self.assertEqual(lc.load_config(path, environ={}, require_courses=False)["course_ids"], set())

    def test_request_enforces_scope_before_network(self):
        with mock.patch.object(lc._opener, "open") as op:
            with self.assertRaises(lc.ScopeError):
                lc.request(CFG, "PUT", "courses/999/pages/x", body={"a": 1})
            op.assert_not_called()


class Roster(unittest.TestCase):
    ROSTER = {"chem": {"alias": "chem", "id": 1001, "name": "Chemistry 101 Fall"}}

    def test_expand_alias(self):
        self.assertEqual(lc.expand_alias("@chem/assignments", self.ROSTER), "courses/1001/assignments")
        self.assertEqual(lc.expand_alias("@chem", self.ROSTER), "courses/1001")
        self.assertEqual(lc.expand_alias("courses/1/x", self.ROSTER), "courses/1/x")
        with self.assertRaises(lc.ScopeError):
            lc.expand_alias("@nope/pages", self.ROSTER)
        self.assertEqual(lc.expand_alias("/api/quiz/v1/@chem/quizzes", self.ROSTER),
                         "/api/quiz/v1/courses/1001/quizzes")
        self.assertEqual(lc.expand_alias("api/quiz/v1/@chem", self.ROSTER), "/api/quiz/v1/courses/1001")
        self.assertIn("Chemistry 101", lc.describe_target("/api/quiz/v1/courses/1001/quizzes", self.ROSTER))

    def test_describe_target(self):
        self.assertIn("Chemistry 101", lc.describe_target("/api/v1/courses/1001/assignments", self.ROSTER))
        self.assertIn("WARNING", lc.describe_target("/api/v1/courses/1/assignments", self.ROSTER))

    def test_template_roster_is_valid(self):
        roster = lc.load_roster(REPO / "templates" / "courses.example.json")
        self.assertTrue(roster)
        ids = [c["id"] for c in roster.values()]
        self.assertEqual(len(ids), len(set(ids)))
        for c in roster.values():
            self.assertTrue(isinstance(c["id"], int) and c["name"] and c["alias"].isidentifier())


class Setup(unittest.TestCase):
    def test_templates_load(self):
        from canvas_harness import settings as st
        self.assertEqual(st.load_switches(REPO / "templates" / "canvas-config.example.json"), st.DEFAULT_SWITCHES)
        self.assertEqual(st.load_profile(REPO / "templates" / "profile.example.json")["timezone"], "America/Chicago")

    def test_missing_local_gives_setup_hint(self):
        empty = tempfile.mkdtemp()
        err = io.StringIO()
        env = {"CANVAS_HARNESS_LOCAL": empty, "CANVAS_HARNESS_ENV": os.path.join(empty, "none")}
        with mock.patch.dict(os.environ, env), redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = lc.main(["check"])
        self.assertEqual(rc, 2)
        self.assertIn("/setup", err.getvalue())

    def test_bad_local_files_give_setup_hint(self):
        from canvas_harness import settings as st
        d = Path(tempfile.mkdtemp())
        (d / "courses.json").write_text("[1, 2]")
        (d / "profile.json").write_text('{"timezone": "Mars/Base"}')
        with self.assertRaises(st.SetupError):
            st.load_roster(d / "courses.json")
        with self.assertRaises(st.SetupError):
            st.load_profile(d / "profile.json")
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"CANVAS_HARNESS_LOCAL": str(d)}), redirect_stderr(err):
            rc = lc.main(["uploads"])
        self.assertEqual(rc, 2)
        self.assertIn("/setup", err.getvalue())


class FakeResp:
    def __init__(self, body, link=None):
        self._body = json.dumps(body).encode()
        self.headers = {"Link": link} if link else {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Requests(unittest.TestCase):
    def test_sends_bearer_and_json(self):
        with mock.patch.object(lc._opener, "open", return_value=FakeResp({"ok": 1})) as op:
            out = lc.request(CFG, "put", "courses/111/pages/home", body={"wiki_page": {"body": "hi"}})
        req = op.call_args[0][0]
        self.assertEqual(out, {"ok": 1})
        self.assertEqual(req.get_method(), "PUT")
        self.assertEqual(req.full_url, "https://school.instructure.com/api/v1/courses/111/pages/home")
        self.assertEqual(req.get_header("Authorization"), f"Bearer {TOKEN}")
        self.assertEqual(json.loads(req.data), {"wiki_page": {"body": "hi"}})

    def test_pagination_stays_in_scope(self):
        pages = [
            FakeResp([1], '<https://school.instructure.com/api/v1/courses/111/x?page=2>; rel="next"'),
            FakeResp([2], '<https://school.instructure.com/api/v1/courses/999/x?page=3>; rel="next"'),
        ]
        with mock.patch.object(lc._opener, "open", side_effect=pages):
            with self.assertRaises(lc.ScopeError):
                lc.request(CFG, "GET", "courses/111/x", paginate=True)

    def test_http_error_is_redacted(self):
        err = lc.urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(f"bad {TOKEN}".encode()))
        with mock.patch.object(lc._opener, "open", side_effect=err):
            with self.assertRaises(RuntimeError) as cm:
                lc.request(CFG, "GET", "courses/111")
        self.assertNotIn(TOKEN, str(cm.exception))
        self.assertIn("[REDACTED]", str(cm.exception))

    def test_dry_run_and_delete_guard_via_cli(self):
        path = write_secrets(
            f"CANVAS_BASE_URL=https://school.instructure.com\nCANVAS_API_TOKEN={TOKEN}\nCANVAS_COURSE_IDS=111\n"
        )
        with mock.patch.object(lc._opener, "open") as op:
            err, out = io.StringIO(), io.StringIO()
            with redirect_stderr(err), redirect_stdout(out):
                rc = lc.main(["--env-file", path, "delete", "courses/111/pages/x"])
            self.assertEqual(rc, 2)
            self.assertIn("--yes", err.getvalue())
            out = io.StringIO()
            with redirect_stdout(out):
                rc = lc.main(["--env-file", path, "post", "courses/111/pages", "-F", "wiki_page[title]=Hi", "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertNotIn(TOKEN, out.getvalue())
            op.assert_not_called()


class PlusA(unittest.TestCase):
    """Drive bin/+a through a pseudo-terminal so the hidden prompt is exercised."""

    def run_plus_a(self, secrets, args, answers):
        import pty
        pid, fd = pty.fork()
        if pid == 0:
            os.environ["CANVAS_HARNESS_ENV"] = secrets
            os.execv("/bin/bash", ["bash", str(REPO / "bin" / "+a"), *args])
        out = b""
        for a in answers:
            out += os.read(fd, 4096)
            os.write(fd, a.encode() + b"\n")
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
        _, status = os.waitpid(pid, 0)
        return os.waitstatus_to_exitcode(status), out.decode()

    def test_upsert_hidden_and_mode(self):
        d = tempfile.mkdtemp()
        secrets = os.path.join(d, ".env")
        Path(secrets).write_text("KEEP=1\nCANVAS_API_TOKEN=old\n")
        rc, out = self.run_plus_a(secrets, ["CANVAS_API_TOKEN"], ["s3cr3t-value"])
        self.assertEqual(rc, 0, out)
        self.assertNotIn("s3cr3t-value", out)
        self.assertEqual(lc.parse_secrets(Path(secrets).read_text()), {"KEEP": "1", "CANVAS_API_TOKEN": "s3cr3t-value"})
        self.assertEqual(stat.S_IMODE(os.stat(secrets).st_mode), 0o600)

        listing = subprocess.run(["bash", str(REPO / "bin" / "+a"), "-l"], env={**os.environ, "CANVAS_HARNESS_ENV": secrets},
                                 capture_output=True, text=True)
        self.assertIn("CANVAS_API_TOKEN", listing.stdout)
        self.assertNotIn("s3cr3t-value", listing.stdout)

    def test_rejects_name_equals_value(self):
        d = tempfile.mkdtemp()
        r = subprocess.run(["bash", str(REPO / "bin" / "+a"), "A=b"],
                           env={**os.environ, "CANVAS_HARNESS_ENV": os.path.join(d, "s")}, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
