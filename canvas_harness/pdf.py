"""Render course HTML (worksheets, keys, quizzes) to PDF in the course's landing folder.

The course is never chosen by the caller. It is the roster course whose
`local_project` folder (absolute, ~/..., or relative to the profile's
projects_root) contains the resolved HTML path. `--course` may only confirm it.

Default names: `<prefix> <Topic> <File>.pdf`, where prefix is the course's
`pdf_prefix` (default: alias in capitals). An answer key next to practice.html
becomes `<prefix> <Topic> Practice <answer_key_label>.pdf`.

Rendering uses headless Chrome/Chromium without the date/URL header/footer;
override the binary with $CANVAS_HARNESS_CHROME.
"""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import settings as st

HTML_EXTS = {".html", ".htm"}
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)
CHROME_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome")
# Folder names that describe the file type, not the topic; skipped when naming.
GENERIC_DIRS = {"worksheet", "worksheets", "practice-worksheet", "quizzes", "quiz", "answers", "practice"}


class PdfError(Exception):
    pass


def course_for(html, roster, profile=None):
    """(alias, course, src, project_dir) whose local_project contains html, after resolving symlinks."""
    profile = profile or st.load_profile()
    src = Path(html).resolve()
    if src.suffix.lower() not in HTML_EXTS:
        raise PdfError(f"{html}: only .html/.htm can be rendered")
    if not src.is_file():
        raise PdfError(f"{html}: no such file")
    hits = []
    for alias, c in roster.items():
        proj = st.project_dir(c, profile)
        if proj and src.is_relative_to(proj):
            hits.append((alias, c, proj))
    if len(hits) != 1:
        where = "no roster course folder" if not hits else "more than one course folder"
        raise PdfError(f"{src} is inside {where}; move it into its course's project folder")
    alias, c, proj = hits[0]
    return alias, c, src, proj


def _title(part):
    return " ".join(w if w.isupper() else w.capitalize() for w in re.split(r"[-_\s]+", part) if w)


def default_name(course, src, project_dir, profile=None):
    """`<prefix> <Topic> Practice.pdf`; an answer key becomes `... Practice <label>.pdf` (or `<Topic> <label>`)."""
    profile = profile or st.load_profile()
    rel_dirs = [p for p in src.parent.relative_to(project_dir).parts if p.lower() not in GENERIC_DIRS]
    topic = " ".join(_title(p) for p in rel_dirs)
    stem = src.stem.lower()
    key_stems = {w.lower() for w in profile["answer_key_words"]} | {"answer-key", "answer_key"}
    key_label = profile["answer_key_label"]
    if stem in key_stems:
        sibling = next((s for s in ("practice", "quiz") if (src.parent / f"{s}.html").exists()), None)
        label = f"{_title(sibling)} {key_label}" if sibling else key_label
    else:
        label = _title(src.stem)
    prefix = course.get("pdf_prefix", course["alias"].upper())
    return " ".join(x for x in (prefix, topic, label) if x) + ".pdf"


def chrome_path():
    explicit = os.environ.get("CANVAS_HARNESS_CHROME")
    found = [shutil.which(n) or "" for n in CHROME_NAMES]
    for c in ([explicit] if explicit else []) + list(CHROME_CANDIDATES) + found:
        if c and Path(c).exists():
            return c
    raise PdfError("Chrome/Chromium not found; set CANVAS_HARNESS_CHROME to its binary")


def render(src, out):
    """Print src to out with headless Chrome.

    No separate --user-data-dir: with a fresh profile Chrome writes the PDF but
    never exits (verified 2026-10-01); the default profile exits in ~1s.
    """
    try:
        r = subprocess.run(
            [chrome_path(), "--headless", "--disable-gpu", "--no-pdf-header-footer",
             "--virtual-time-budget=4000", f"--print-to-pdf={out}", src.as_uri()],
            capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise PdfError(f"Chrome did not finish rendering {src.name} within 60s; nothing written")
    if not Path(out).exists() or Path(out).stat().st_size == 0:
        raise PdfError(f"Chrome did not produce a PDF for {src.name}: {r.stderr.strip()[-300:]}")


def page_count(pdf):
    return len(re.findall(rb"/Type\s*/Page[^s]", Path(pdf).read_bytes()))


def make_pdf(html, roster, course=None, name=None, pages=None, overwrite=False,
             uploads_root=None, profile=None, renderer=render):
    """Render one HTML file into uploads/<alias>/. Returns (dest, page_count). Writes nothing on error."""
    profile = profile or st.load_profile()
    alias, c, src, project_dir = course_for(html, roster, profile)
    if course and course.lstrip("@") != alias:
        raise PdfError(f"{src.name} belongs to @{alias} ({c['name']}), not {course}; nothing written")
    fname = name or default_name(c, src, project_dir, profile)
    if not fname.lower().endswith(".pdf"):
        fname += ".pdf"
    if Path(fname).name != fname or fname.startswith("."):
        raise PdfError(f"--name must be a plain file name, got {fname!r}")
    folder = Path(uploads_root or st.uploads_root()) / alias
    dest = folder / fname
    if dest.exists() and not overwrite:
        raise PdfError(f"{dest} already exists (it may be in a previewed plan); pass --overwrite to replace it")
    folder.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".pdf", prefix=".rendering-", dir=folder)
    os.close(fd)
    try:
        renderer(src, tmp)
        n = page_count(tmp)
        if pages is not None and n != pages:
            raise PdfError(f"{src.name} rendered to {n} page{'s' * (n != 1)}, expected {pages}; nothing written")
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return dest, n
