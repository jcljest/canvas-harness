import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from canvas_harness import plan as lp  # noqa: E402
from canvas_harness import settings as st  # noqa: E402

# Never touch a real local/ folder in tests.
os.environ["CANVAS_HARNESS_LOCAL"] = tempfile.mkdtemp()
os.environ["CANVAS_HARNESS_ENV"] = os.path.join(os.environ["CANVAS_HARNESS_LOCAL"], "secrets")

ROSTER = {
    "chem": {"alias": "chem", "id": 1001, "name": "Chemistry 101 Fall"},
    "biology": {"alias": "biology", "id": 1002, "name": "Biology 101 Fall"},
}


def make_plan(steps, files=None, title="Test plan"):
    d = Path(tempfile.mkdtemp())
    for name, text in (files or {}).items():
        (d / name).write_text(text)
    p = d / "plan.json"
    p.write_text(json.dumps({"title": title, "steps": steps}))
    return p


ASSIGN = {
    "course": "@chem", "method": "POST", "path": "assignments", "note": "lab",
    "body": {"assignment": {"name": "Lab 3", "points_possible": 10,
                            "due_at": "2030-10-02T23:59:00-04:00", "published": False}},
    "files": {"assignment.description": "lab3.html"},
}
MODULE_ITEM = {"course": "@chem", "method": "POST", "path": "modules/55/items",
               "body": {"module_item": {"type": "Assignment", "content_id": "{{1.id}}"}}}


def approve_directly(path, roster=ROSTER):
    _, digest = lp.load_plan(path, roster)
    lp.stamp_path(path).write_text(json.dumps({"digest": digest, "applied_at": None}))


class Load(unittest.TestCase):
    def test_resolves_files_and_course(self):
        p = make_plan([ASSIGN], {"lab3.html": "<p>Do the lab</p>"})
        plan, digest = lp.load_plan(p, ROSTER)
        s = plan["steps"][0]
        self.assertEqual(s["course_id"], 1001)
        self.assertEqual(s["body"]["assignment"]["description"], "<p>Do the lab</p>")
        self.assertEqual(len(digest), 64)

    def test_rejects_bad_steps(self):
        bad = [
            {**ASSIGN, "course": "@nope"},
            {**ASSIGN, "course": "1001"},
            {**ASSIGN, "method": "GET"},
            {**ASSIGN, "path": "courses/999/assignments"},
            {**ASSIGN, "path": "../../accounts/1"},
            {**MODULE_ITEM, "body": {"module_item": {"content_id": "{{1.id}}"}}},  # refers to itself
        ]
        for step in bad:
            p = make_plan([step], {"lab3.html": "x"})
            with self.assertRaises(lp.PlanError, msg=json.dumps(step)):
                lp.load_plan(p, ROSTER)

    def test_digest_changes_with_referenced_file(self):
        p = make_plan([ASSIGN], {"lab3.html": "v1"})
        _, d1 = lp.load_plan(p, ROSTER)
        (p.parent / "lab3.html").write_text("v2")
        _, d2 = lp.load_plan(p, ROSTER)
        self.assertNotEqual(d1, d2)


class Preview(unittest.TestCase):
    def test_html_escapes_and_sandboxes(self):
        p = make_plan([ASSIGN], {"lab3.html": '<p>Hi</p><script>alert(1)</script>'})
        plan, digest = lp.load_plan(p, ROSTER)
        page = lp.render_preview(plan, digest, "https://x.instructure.com")
        self.assertIn("Chemistry 101 Fall", page)
        self.assertIn("<iframe sandbox", page)
        self.assertNotIn("<script>alert", page)
        self.assertIn("Wed Oct 2, 2030 11:59 PM", page)

    def test_warnings(self):
        s = {"method": "POST", "body": {"assignment": {"published": True, "due_at": "2020-01-01T00:00:00",
                                                        "lock_at": "2020-01-01T00:00:00Z"}}}
        w = " | ".join(lp.warnings_for(s))
        self.assertIn("PUBLISHED", w)
        self.assertIn("no timezone offset", w)
        self.assertIn("in the past", w)
        self.assertIn("DELETES", " ".join(lp.warnings_for({"method": "DELETE", "body": {}})))

    def test_preview_writes_file(self):
        p = make_plan([ASSIGN], {"lab3.html": "x"})
        out = lp.preview(p, ROSTER, "https://x", open_browser=False)
        self.assertTrue(out.exists())
        self.assertIsNone(lp.read_stamp(p))


class Apply(unittest.TestCase):
    def fake_send(self):
        calls = []

        def send(method, path, body):
            calls.append((method, path, body))
            return {"id": 100 + len(calls), "html_url": f"https://x/{len(calls)}"}
        return calls, send

    def test_refuses_without_approval(self):
        p = make_plan([ASSIGN], {"lab3.html": "x"})
        calls, send = self.fake_send()
        with self.assertRaisesRegex(lp.PlanError, "not approved"):
            lp.apply(p, ROSTER, send, describe=lambda _: None)
        self.assertEqual(calls, [])

    def test_refuses_changed_plan(self):
        p = make_plan([ASSIGN], {"lab3.html": "x"})
        approve_directly(p)
        (p.parent / "lab3.html").write_text("sneaky edit")
        calls, send = self.fake_send()
        with self.assertRaisesRegex(lp.PlanError, "changed since approval"):
            lp.apply(p, ROSTER, send, describe=lambda _: None)
        self.assertEqual(calls, [])

    def test_applies_once_with_placeholders(self):
        p = make_plan([ASSIGN, MODULE_ITEM], {"lab3.html": "x"})
        approve_directly(p)
        calls, send = self.fake_send()
        log = lp.apply(p, ROSTER, send, describe=lambda _: None)
        self.assertEqual([c[1] for c in calls], ["courses/1001/assignments", "courses/1001/modules/55/items"])
        self.assertEqual(calls[1][2]["module_item"]["content_id"], 101)
        self.assertTrue(all(r["ok"] for r in log))
        with self.assertRaisesRegex(lp.PlanError, "already applied"):
            lp.apply(p, ROSTER, send, describe=lambda _: None)

    def test_partial_failure_consumes_approval(self):
        p = make_plan([ASSIGN, MODULE_ITEM], {"lab3.html": "x"})
        approve_directly(p)
        n = {"i": 0}

        def send(method, path, body):
            n["i"] += 1
            if n["i"] == 2:
                raise RuntimeError("HTTP 500")
            return {"id": 1}
        with self.assertRaises(RuntimeError):
            lp.apply(p, ROSTER, send, describe=lambda _: None)
        self.assertTrue(lp.read_stamp(p)["applied_at"])
        result = json.loads(p.with_name("plan.json.result.json").read_text())
        self.assertEqual([r["ok"] for r in result["steps"]], [True, False])


class Approve(unittest.TestCase):
    def test_requires_terminal(self):
        p = make_plan([ASSIGN], {"lab3.html": "x"})
        with self.assertRaisesRegex(lp.PlanError, "interactive terminal"):
            lp.approve(p, ROSTER, tty_path="/nonexistent/tty")

    def test_typed_approve_writes_stamp(self):
        p = make_plan([ASSIGN], {"lab3.html": "x"})
        fake_tty = p.parent / "tty"
        fake_tty.write_text("approve\n")
        lp.approve(p, ROSTER, tty_path=str(fake_tty))
        _, digest = lp.load_plan(p, ROSTER)
        self.assertEqual(lp.read_stamp(p)["digest"], digest)

    def test_other_answer_rejected(self):
        p = make_plan([ASSIGN], {"lab3.html": "x"})
        fake_tty = p.parent / "tty"
        fake_tty.write_text("yes\n")
        with self.assertRaisesRegex(lp.PlanError, "not approved"):
            lp.approve(p, ROSTER, tty_path=str(fake_tty))
        self.assertIsNone(lp.read_stamp(p))


if __name__ == "__main__":
    unittest.main()


class Settings(unittest.TestCase):
    def write(self, obj):
        p = Path(tempfile.mkdtemp()) / "canvas-config.json"
        p.write_text(obj if isinstance(obj, str) else json.dumps(obj))
        return p

    def test_missing_file_is_defaults(self):
        self.assertEqual(st.load_switches(Path(tempfile.mkdtemp()) / "none.json"),
                         {"auto_approve": False, "auto_preview": True, "auto_publish": False})

    def test_partial_file_fills_defaults(self):
        self.assertEqual(st.load_switches(self.write({"auto_preview": False})),
                         {"auto_approve": False, "auto_preview": False, "auto_publish": False})

    def test_bad_values_fail_closed(self):
        for bad in ({"auto_publish": "yes"}, {"auto_approve": "true"}, {"auto_approve": 1}, {"auto_aprove": True}, [], "{not json"):
            with self.assertRaises(st.SetupError, msg=repr(bad)):
                st.load_switches(self.write(bad))


class AutoApprove(unittest.TestCase):
    ON = {"auto_approve": True, "auto_preview": False}
    OFF = {"auto_approve": False, "auto_preview": False}

    def send(self):
        calls = []
        return calls, lambda m, p, b: calls.append((m, p)) or {"id": 100 + len(calls)}

    def test_off_still_needs_typed_approval(self):
        p = make_plan([ASSIGN], {"lab3.html": "x"})
        calls, send = self.send()
        with self.assertRaisesRegex(lp.PlanError, "not approved"):
            lp.apply(p, ROSTER, send, describe=lambda _: None, settings=self.OFF)
        self.assertEqual(calls, [])

    def test_clean_published_plan_is_auto_approved(self):
        step = json.loads(json.dumps(ASSIGN))
        step["body"]["assignment"]["published"] = True
        p = make_plan([step, MODULE_ITEM], {"lab3.html": "x"})
        calls, send = self.send()
        lp.apply(p, ROSTER, send, describe=lambda _: None, settings=self.ON)
        self.assertEqual(len(calls), 2)
        stamp = lp.read_stamp(p)
        self.assertTrue(stamp["approved_by"].startswith("auto"))
        self.assertIsNotNone(stamp["applied_at"])

    def test_flagged_plans_apply_then_alert(self):
        past = json.loads(json.dumps(ASSIGN))
        past["body"]["assignment"]["due_at"] = "2020-01-01T23:59:00-05:00"
        flagged = [
            {"course": "@chem", "method": "DELETE", "path": "pages/old", "body": {}},
            past,
            {"course": "@chem", "method": "POST", "path": "discussion_topics",
             "body": {"title": "Hi", "is_announcement": True}},
        ]
        for step in flagged:
            p = make_plan([step], {"lab3.html": "x"})
            calls, send = self.send()
            said = []
            lp.apply(p, ROSTER, send, describe=said.append, settings=self.ON)
            self.assertEqual(len(calls), 1, msg=json.dumps(step))
            self.assertTrue(lp.read_stamp(p)["approved_by"].startswith("auto"))
            result = json.loads(p.with_name(p.name + ".result.json").read_text())
            self.assertTrue(result["alerts"], msg=json.dumps(step))
            self.assertTrue(said[-1].startswith("ALERT step 1:"), msg=said)

    def test_clean_plan_has_no_alerts(self):
        p = make_plan([ASSIGN], {"lab3.html": "x"})
        calls, send = self.send()
        lp.apply(p, ROSTER, send, describe=lambda _: None, settings=self.ON)
        result = json.loads(p.with_name(p.name + ".result.json").read_text())
        self.assertNotIn("alerts", result)

    def test_typed_approval_still_works_when_on(self):
        p = make_plan([{"course": "@chem", "method": "DELETE", "path": "pages/old", "body": {}}])
        approve_directly(p)
        calls, send = self.send()
        lp.apply(p, ROSTER, send, describe=lambda _: None, settings=self.ON)
        self.assertEqual(calls, [("DELETE", "courses/1001/pages/old")])

    def test_preview_reports_approval_and_follows_auto_preview(self):
        from unittest import mock
        p = make_plan([ASSIGN], {"lab3.html": "x"})
        with mock.patch.object(lp.subprocess, "run") as run:
            out = lp.preview(p, ROSTER, "https://x", settings=self.ON)
        run.assert_not_called()
        self.assertTrue(out.exists())
        self.assertIn("approval: AUTO", out.read_text())
        with mock.patch.object(lp.subprocess, "run") as run, mock.patch.object(lp.sys, "platform", "darwin"):
            lp.preview(p, ROSTER, "https://x", settings={"auto_approve": False, "auto_preview": True})
        run.assert_called_once()
        self.assertIsNone(lp.read_stamp(p))


class AutoPublish(unittest.TestCase):
    def body(self, step, auto_publish):
        p = make_plan([step], {"lab3.html": "x"})
        plan, _ = lp.load_plan(p, ROSTER, settings={"auto_publish": auto_publish})
        return plan["steps"][0]["body"]

    def test_fills_published_on_new_items(self):
        unset = json.loads(json.dumps(ASSIGN))
        del unset["body"]["assignment"]["published"]
        for flag in (True, False):
            self.assertIs(self.body(unset, flag)["assignment"]["published"], flag)
            page = {"course": "@chem", "method": "POST", "path": "pages", "body": {"wiki_page": {"title": "T"}}}
            self.assertIs(self.body(page, flag)["wiki_page"]["published"], flag)
            disc = {"course": "@chem", "method": "POST", "path": "discussion_topics", "body": {"title": "D"}}
            self.assertIs(self.body(disc, flag)["published"], flag)

    def test_explicit_value_announcements_and_updates_untouched(self):
        self.assertIs(self.body(ASSIGN, True)["assignment"]["published"], False)  # ASSIGN says false
        ann = {"course": "@chem", "method": "POST", "path": "discussion_topics",
               "body": {"title": "A", "is_announcement": True, "delayed_post_at": "2030-01-01T07:00:00-05:00"}}
        self.assertNotIn("published", self.body(ann, True))
        put = {"course": "@chem", "method": "PUT", "path": "assignments/5", "body": {"assignment": {"name": "x"}}}
        self.assertNotIn("published", self.body(put, True)["assignment"])
        item = {**MODULE_ITEM, "body": {"module_item": {"type": "Assignment", "content_id": 5}}}
        self.assertNotIn("published", self.body(item, True)["module_item"])

    def test_switch_changes_digest(self):
        unset = json.loads(json.dumps(ASSIGN))
        del unset["body"]["assignment"]["published"]
        p = make_plan([unset], {"lab3.html": "x"})
        _, d1 = lp.load_plan(p, ROSTER, settings={"auto_publish": True})
        _, d2 = lp.load_plan(p, ROSTER, settings={"auto_publish": False})
        self.assertNotEqual(d1, d2)


class TimezoneCheck(unittest.TestCase):
    PROFILE = {**st.DEFAULT_PROFILE, "timezone": "America/New_York"}

    def warn(self, due):
        return lp.warnings_for({"method": "POST", "body": {"assignment": {"due_at": due}}}, profile=self.PROFILE)

    def test_offset_must_match_profile_timezone(self):
        self.assertEqual(self.warn("2030-10-02T23:59:00-04:00"), [])          # EDT in October
        self.assertEqual(self.warn("2030-12-02T23:59:00-05:00"), [])          # EST in December
        w = self.warn("2030-12-02T23:59:00-04:00")                            # wrong in December
        self.assertTrue(w and "doesn't match America/New_York" in w[0], w)
        self.assertIn("10:59 PM local", w[0])

    def test_no_timezone_no_check(self):
        s = {"method": "POST", "body": {"assignment": {"due_at": "2030-12-02T23:59:00-04:00"}}}
        self.assertEqual(lp.warnings_for(s, profile=st.DEFAULT_PROFILE), [])
