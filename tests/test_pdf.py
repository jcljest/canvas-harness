import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from canvas_harness import pdf  # noqa: E402
from canvas_harness import settings as st  # noqa: E402

# Never touch a real local/ folder in tests.
os.environ["CANVAS_HARNESS_LOCAL"] = tempfile.mkdtemp()
os.environ["CANVAS_HARNESS_ENV"] = os.path.join(os.environ["CANVAS_HARNESS_LOCAL"], "secrets")

ROSTER = {
    "chem": {"alias": "chem", "id": 1001, "name": "Chemistry 101 Fall", "local_project": "chemistry"},
    "biology": {"alias": "biology", "id": 1002, "name": "Biology 101 Fall", "local_project": "biology"},
}


def fake_renderer(pages):
    def r(src, out):
        Path(out).write_bytes(b"%PDF-1.4\n" + b"<< /Type /Page >>\n" * pages + b"<< /Type /Pages >>\n")
    return r


class PdfTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.projects = self.root / "Projects"
        self.uploads = self.root / "uploads"
        self.profile = {**st.DEFAULT_PROFILE, "projects_root": str(self.projects)}
        ws = self.projects / "chemistry" / "proportional-reasoning" / "worksheet"
        ws.mkdir(parents=True)
        (self.projects / "biology").mkdir()
        self.practice = ws / "practice.html"
        self.answers = ws / "answers.html"
        for f in (self.practice, self.answers):
            f.write_text("<html></html>")

    def make(self, html, pages=10, **kw):
        return pdf.make_pdf(html, ROSTER, uploads_root=self.uploads, profile=self.profile,
                            renderer=fake_renderer(pages), **kw)

    def written(self):
        return sorted(p.name for p in self.uploads.rglob("*") if p.is_file())

    def test_course_from_project_folder_and_default_names(self):
        dest, n = self.make(self.practice)
        self.assertEqual((dest.parent.name, dest.name, n), ("chem", "CHEM Proportional Reasoning Practice.pdf", 10))
        dest, _ = self.make(self.answers, pages=5)
        self.assertEqual(dest.name, "CHEM Proportional Reasoning Practice ANS.pdf")

    def test_key_without_practice_sibling_still_gets_ans(self):
        key = self.projects / "chemistry" / "unit9" / "quizzes" / "solutions.html"
        key.parent.mkdir(parents=True)
        key.write_text("x")
        self.assertEqual(self.make(key)[0].name, "CHEM Unit9 ANS.pdf")

    def test_outside_every_course_folder_refused(self):
        stray = self.projects / "misc.html"
        stray.write_text("x")
        with self.assertRaises(pdf.PdfError):
            self.make(stray)
        self.assertEqual(self.written(), [])

    def test_symlink_escape_refused(self):
        outside = self.root / "elsewhere.html"
        outside.write_text("x")
        link = self.projects / "chemistry" / "link.html"
        os.symlink(outside, link)
        with self.assertRaises(pdf.PdfError):
            self.make(link)
        self.assertEqual(self.written(), [])

    def test_non_html_refused(self):
        notes = self.projects / "chemistry" / "notes.md"
        notes.write_text("x")
        with self.assertRaises(pdf.PdfError):
            self.make(notes)

    def test_course_mismatch_refused(self):
        with self.assertRaises(pdf.PdfError):
            self.make(self.practice, course="@physics")
        self.assertEqual(self.written(), [])
        self.assertEqual(self.make(self.practice, course="@chem")[0].parent.name, "chem")

    def test_existing_file_needs_overwrite(self):
        self.make(self.practice)
        with self.assertRaises(pdf.PdfError):
            self.make(self.practice)
        self.make(self.practice, pages=3, overwrite=True)
        self.assertEqual(pdf.page_count(self.uploads / "chem" / "CHEM Proportional Reasoning Practice.pdf"), 3)

    def test_page_mismatch_leaves_nothing(self):
        with self.assertRaises(pdf.PdfError):
            pdf.make_pdf(self.practice, ROSTER, pages=10, uploads_root=self.uploads,
                         profile=self.profile, renderer=fake_renderer(11))
        self.assertEqual(self.written(), [])

    def test_name_must_be_plain(self):
        with self.assertRaises(pdf.PdfError):
            self.make(self.practice, name="../biology/x.pdf")
        self.assertEqual(self.make(self.practice, name="Custom")[0].name, "Custom.pdf")

    def test_page_count_ignores_pages_tree_node(self):
        p = self.root / "p.pdf"
        fake_renderer(4)(None, p)
        self.assertEqual(pdf.page_count(p), 4)


if __name__ == "__main__":
    unittest.main()
