import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from canvas_harness import cli as lc  # noqa: E402
from canvas_harness import plan as lp  # noqa: E402

# Never touch a real local/ folder in tests.
os.environ["CANVAS_HARNESS_LOCAL"] = tempfile.mkdtemp()
os.environ["CANVAS_HARNESS_ENV"] = os.path.join(os.environ["CANVAS_HARNESS_LOCAL"], "secrets")

ROSTER = {"chem": {"alias": "chem", "id": 1001, "name": "Chemistry 101 Fall"}}
TOKEN = "fake~token~abc"
CFG = {"base": "https://school.instructure.com", "token": TOKEN, "course_ids": {"1001"}}


def setup(plan_steps, pdf=b"%PDF-1.4 fake"):
    d = Path(tempfile.mkdtemp())
    uploads = d / "uploads"
    (uploads / "chem").mkdir(parents=True)
    (uploads / "chem" / "lab3.pdf").write_bytes(pdf)
    plan_dir = d / "plan"
    plan_dir.mkdir()
    (plan_dir / "desc.html").write_text(
        '<p>Handout: <a class="instructure_file_link" href="{{1.course_file_url}}">Lab 3 (PDF)</a></p>')
    p = plan_dir / "plan.json"
    p.write_text(json.dumps({"title": "t", "steps": plan_steps}))
    return p, uploads


UPLOAD = {"course": "@chem", "upload": "lab3.pdf", "folder": "Assignments/Lab 3"}
ASSIGN = {"course": "@chem", "method": "POST", "path": "assignments",
          "body": {"assignment": {"name": "Lab 3", "published": False}},
          "files": {"assignment.description": "desc.html"}}


class UploadSteps(unittest.TestCase):
    def test_resolves_landing_file(self):
        p, up = setup([UPLOAD])
        plan, _ = lp.load_plan(p, ROSTER, up)
        s = plan["steps"][0]
        self.assertEqual((s["kind"], s["file"], s["folder"], s["on_duplicate"]),
                         ("upload", "lab3.pdf", "Assignments/Lab 3", "rename"))

    def test_rejects_escape_type_and_missing(self):
        p, up = setup([UPLOAD])
        (up / "chem" / "notes.exe").write_bytes(b"x")
        secret = up.parent / "secret.pdf"
        secret.write_bytes(b"x")
        os.symlink(secret, up / "chem" / "link.pdf")
        for bad in ["../secret.pdf", "/etc/hosts", "notes.exe", "missing.pdf", "link.pdf"]:
            p.write_text(json.dumps({"steps": [{**UPLOAD, "upload": bad}]}))
            with self.assertRaises(lp.PlanError, msg=bad):
                lp.load_plan(p, ROSTER, up)
        for bad in [{"folder": "../x"}, {"on_duplicate": "replace"}]:
            p.write_text(json.dumps({"steps": [{**UPLOAD, **bad}]}))
            with self.assertRaises(lp.PlanError, msg=str(bad)):
                lp.load_plan(p, ROSTER, up)

    def test_changed_pdf_invalidates_approval(self):
        p, up = setup([UPLOAD])
        _, d1 = lp.load_plan(p, ROSTER, up)
        (up / "chem" / "lab3.pdf").write_bytes(b"%PDF-1.4 changed")
        _, d2 = lp.load_plan(p, ROSTER, up)
        self.assertNotEqual(d1, d2)

    def test_preview_shows_upload_and_overwrite_warning(self):
        p, up = setup([{**UPLOAD, "on_duplicate": "overwrite"}, ASSIGN])
        plan, digest = lp.load_plan(p, ROSTER, up)
        page = lp.render_preview(plan, digest, CFG["base"])
        self.assertIn("upload lab3.pdf", page)
        self.assertIn("Files / Assignments/Lab 3", page)
        self.assertIn("OVERWRITES", page)
        self.assertIn('<embed src="file://', page)
        self.assertIn("OVERWRITES", lp.text_summary(plan, digest))

    def test_answer_key_warning(self):
        base = {"kind": "upload", "on_duplicate": "rename", "size": 1}
        for name in ["CHEM-thermo-bar-chart-ans.pdf", "Lab3_KEY.pdf", "unit 2 solutions.pdf", "answers.pdf"]:
            self.assertTrue(any("ANSWER KEY" in w for w in lp.warnings_for({**base, "file": name})), name)
        for name in ["CHEM-Thermo-Bar-Charts.pdf", "keyboard-lab.pdf", "answering-questions.pdf"]:
            self.assertFalse(any("ANSWER KEY" in w for w in lp.warnings_for({**base, "file": name})), name)

    def test_apply_links_uploaded_file_in_assignment(self):
        p, up = setup([UPLOAD, ASSIGN])
        _, digest = lp.load_plan(p, ROSTER, up)
        lp.stamp_path(p).write_text(json.dumps({"digest": digest, "applied_at": None}))
        sent, uploaded = [], []

        def upload(cid, path, folder, od):
            uploaded.append((cid, Path(path).name, folder, od))
            return {"id": 777, "display_name": "lab3.pdf"}

        def send(method, path, body):
            sent.append(body)
            return {"id": 1, "html_url": "https://x/a/1"}

        log = lp.apply(p, ROSTER, send, describe=lambda _: None, upload=upload, uploads_root=up)
        self.assertEqual(uploaded, [(1001, "lab3.pdf", "Assignments/Lab 3", "rename")])
        self.assertIn('href="/courses/1001/files/777"', sent[0]["assignment"]["description"])
        self.assertEqual(log[0]["html_url"], "/courses/1001/files/777")

    def test_root_folder_and_path_placeholders(self):
        p, up = setup([{**UPLOAD, "folder": "/"},
                       {"course": "@chem", "method": "POST", "path": "modules/5/items",
                        "body": {"module_item": {"type": "File", "content_id": "{{1.id}}"}}},
                       {"course": "@chem", "method": "PUT", "path": "modules/5/items/{{2.id}}",
                        "body": {"module_item": {"published": True}}}])
        plan, digest = lp.load_plan(p, ROSTER, up)
        self.assertEqual(plan["steps"][0]["folder"], "/")
        lp.stamp_path(p).write_text(json.dumps({"digest": digest, "applied_at": None}))
        paths = []

        def send(method, path, body):
            paths.append(path)
            return {"id": 42}
        lp.apply(p, ROSTER, send, describe=lambda _: None, upload=lambda *a: {"id": 7}, uploads_root=up)
        self.assertEqual(paths, ["courses/1001/modules/5/items", "courses/1001/modules/5/items/42"])
        # a path placeholder may not point at its own or a later step
        p.write_text(json.dumps({"steps": [{"course": "@chem", "method": "PUT", "path": "modules/5/items/{{1.id}}",
                                            "body": {}}]}))
        with self.assertRaises(lp.PlanError):
            lp.load_plan(p, ROSTER, up)

    def test_inline_and_whole_placeholders(self):
        results = {1: {"id": 5, "course_file_url": "/courses/1/files/5"}}
        self.assertEqual(lp.substitute("{{1.id}}", results), 5)
        self.assertEqual(lp.substitute("a {{1.course_file_url}} b {{1.id}}", results), "a /courses/1/files/5 b 5")
        with self.assertRaises(lp.PlanError):
            lp.substitute("x {{1.nope}}", results)


class FakeResp:
    def __init__(self, body=b"", headers=None):
        self._b, self.headers = body, headers or {}

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class UploadFile(unittest.TestCase):
    def pdf(self):
        f = Path(tempfile.mkdtemp()) / "lab3.pdf"
        f.write_bytes(b"%PDF-1.4 data")
        return f

    def init_resp(self, url="https://inst-fs.example.com/upload/abc"):
        return {"upload_url": url, "upload_params": {"filename": "lab3.pdf", "token": "signed"}}

    def test_201_json_and_no_auth_to_upload_host(self):
        with mock.patch.object(lc, "request", return_value=self.init_resp()) as rq, \
             mock.patch.object(lc._upload_opener, "open",
                               return_value=FakeResp(json.dumps({"id": 9, "display_name": "lab3.pdf"}).encode())) as up:
            out = lc.upload_file(CFG, 1001, self.pdf(), "Assignments/Lab 3")
        self.assertEqual(out["id"], 9)
        init_args = rq.call_args
        self.assertEqual(init_args[0][1:3], ("POST", "courses/1001/files"))
        self.assertEqual(init_args[1]["body"]["parent_folder_path"], "Assignments/Lab 3")
        req = up.call_args[0][0]
        self.assertIsNone(req.get_header("Authorization"))
        self.assertIn(b'name="token"', req.data)
        self.assertIn(b"%PDF-1.4 data", req.data)

    def test_redirect_confirm_on_canvas_host_uses_auth(self):
        redirect = lc.urllib.error.HTTPError(
            "u", 302, "Found", {"Location": "https://school.instructure.com/api/v1/files/9/create_success?uuid=x"}, None)
        with mock.patch.object(lc, "request", return_value=self.init_resp()), \
             mock.patch.object(lc._upload_opener, "open", side_effect=redirect), \
             mock.patch.object(lc._opener, "open", return_value=FakeResp(b'{"id": 9}')) as conf:
            out = lc.upload_file(CFG, 1001, self.pdf(), "Uploads")
        self.assertEqual(out["id"], 9)
        req = conf.call_args[0][0]
        self.assertEqual(req.full_url, "https://school.instructure.com/api/v1/files/9/create_success?uuid=x")
        self.assertEqual(req.get_header("Authorization"), f"Bearer {TOKEN}")

    def test_redirect_elsewhere_is_refused(self):
        for loc in ["https://evil.example.com/api/v1/files/9", "https://school.instructure.com/api/v1/courses/1"]:
            redirect = lc.urllib.error.HTTPError("u", 302, "Found", {"Location": loc}, None)
            with mock.patch.object(lc, "request", return_value=self.init_resp()), \
                 mock.patch.object(lc._upload_opener, "open", side_effect=redirect), \
                 mock.patch.object(lc._opener, "open") as conf:
                with self.assertRaises(RuntimeError, msg=loc):
                    lc.upload_file(CFG, 1001, self.pdf(), "Uploads")
                conf.assert_not_called()

    def test_http_upload_url_refused(self):
        with mock.patch.object(lc, "request", return_value=self.init_resp("http://plain.example.com/up")), \
             mock.patch.object(lc._upload_opener, "open") as up:
            with self.assertRaises(RuntimeError):
                lc.upload_file(CFG, 1001, self.pdf(), "Uploads")
            up.assert_not_called()

    def test_upload_error_redacted(self):
        err = lc.urllib.error.HTTPError("u", 400, "Bad", {}, io.BytesIO(f"oops {TOKEN}".encode()))
        with mock.patch.object(lc, "request", return_value=self.init_resp()), \
             mock.patch.object(lc._upload_opener, "open", side_effect=err):
            with self.assertRaises(RuntimeError) as cm:
                lc.upload_file(CFG, 1001, self.pdf(), "Uploads")
        self.assertNotIn(TOKEN, str(cm.exception))


if __name__ == "__main__":
    unittest.main()


class AutoApproveUploads(unittest.TestCase):
    ON = {"auto_approve": True, "auto_preview": False}

    def test_answer_key_and_overwrite_need_typed_approval(self):
        for step, fname in [({**UPLOAD, "upload": "lab3-ans.pdf"}, "lab3-ans.pdf"),
                            ({**UPLOAD, "on_duplicate": "overwrite"}, "lab3.pdf")]:
            p, up = setup([step])
            (up / "chem" / fname).write_bytes(b"%PDF-1.4 fake")
            sent = []
            with self.assertRaisesRegex(lp.PlanError, "auto_approve is on, but"):
                lp.apply(p, ROSTER, lambda *a: sent.append(a), describe=lambda _: None,
                         upload=lambda *a: sent.append(a) or {"id": 7}, uploads_root=up, settings=self.ON)
            self.assertEqual(sent, [])

    def test_clean_upload_is_auto_approved(self):
        p, up = setup([UPLOAD])
        sent = []
        lp.apply(p, ROSTER, lambda *a: {}, describe=lambda _: None,
                 upload=lambda *a: sent.append(a) or {"id": 7}, uploads_root=up, settings=self.ON)
        self.assertEqual(len(sent), 1)
