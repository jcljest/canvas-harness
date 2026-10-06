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

from canvas_harness import cli  # noqa: E402
from canvas_harness import settings as st  # noqa: E402

PHYS = {"alias": "phys", "id": 2001, "name": "Physics Fall", "nicknames": ["Physics", "Regular Physics"]}
AP = {"alias": "ap", "id": 2002, "name": "AP Physics 2 Fall", "nicknames": ["AP", "AP2", "AP Physics", "AP Physics 2"]}


def roster_file(*courses):
    p = Path(tempfile.mkdtemp()) / "courses.json"
    p.write_text(json.dumps({"courses": list(courses)}))
    return p


class Resolve(unittest.TestCase):
    def setUp(self):
        self.roster = st.load_roster(roster_file(PHYS, AP))

    def test_names_resolve_loosely(self):
        for said, alias in [("AP", "ap"), ("ap2", "ap"), ("AP Physics 2", "ap"), ("ap-physics-2", "ap"),
                            ("@ap", "ap"), ("AP Physics 2 Fall", "ap"), ("physics", "phys"),
                            ("regular physics", "phys"), ("PHYS", "phys")]:
            self.assertEqual(st.resolve_course(said, self.roster)[0], [alias], said)

    def test_no_match_gives_candidates(self):
        matches, cands = st.resolve_course("phys class", self.roster)
        self.assertEqual(matches, [])
        self.assertIn("phys", cands)
        self.assertEqual(st.resolve_course("art", self.roster), ([], []))
        self.assertEqual(st.resolve_course("  ", self.roster), ([], []))


class Validation(unittest.TestCase):
    def bad(self, *courses):
        with self.assertRaises(st.SetupError) as cm:
            st.load_roster(roster_file(*courses))
        return str(cm.exception)

    def test_name_cannot_mean_two_courses(self):
        self.assertIn("both", self.bad(PHYS, {**AP, "nicknames": ["Physics"]}))          # nickname vs nickname
        self.assertIn("both", self.bad(PHYS, {**AP, "nicknames": ["phys"]}))             # nickname vs alias
        self.assertIn("both", self.bad(PHYS, {**AP, "nicknames": ["physics-fall"]}))     # nickname vs title
        self.assertIn("both", self.bad(PHYS, {**AP, "nicknames": ["P.H.Y.S.I.C.S"]}))    # punctuation ignored

    def test_alias_and_nickname_shapes(self):
        self.assertIn("twice", self.bad(PHYS, {**AP, "alias": "phys", "nicknames": []}))
        self.assertIn("letters", self.bad({**PHYS, "alias": "ap-2"}))
        self.assertIn("list of names", self.bad({**PHYS, "nicknames": "Physics"}))
        self.assertIn("list of names", self.bad({**PHYS, "nicknames": ["--"]}))

    def test_nicknames_optional_and_template_valid(self):
        st.load_roster(roster_file({k: v for k, v in PHYS.items() if k != "nicknames"}))
        roster = st.load_roster(REPO / "templates" / "courses.example.json")
        self.assertEqual(st.resolve_course("gen chem", roster)[0], ["chem"])


class WhichCommand(unittest.TestCase):
    def run_which(self, *words):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"CANVAS_HARNESS_LOCAL": str(roster_file(PHYS, AP).parent)}), \
                redirect_stdout(out):
            rc = cli.main(["which", *words])
        return rc, out.getvalue()

    def test_match(self):
        rc, out = self.run_which("AP", "Physics")
        self.assertEqual(rc, 0)
        self.assertIn("@ap = AP Physics 2 Fall (id 2002)", out)

    def test_no_match(self):
        rc, out = self.run_which("phys", "class")
        self.assertEqual(rc, 1)
        self.assertIn("no course is called", out)
        self.assertIn("maybe @phys", out)
        rc, out = self.run_which("art")
        self.assertEqual(rc, 1)
        self.assertIn("courses: @ap", out)


if __name__ == "__main__":
    unittest.main()
