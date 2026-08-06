"""Offline tests for the whole-course cartridge assembler (emit/cartridge.py).

Same strategy as the cc/qti suites — no Canvas, no model: every XML file parses, every manifest
reference resolves to a packaged file, pages AND quizzes both land as typed module items, quiz
questions land in non_cc_assessments, and the seam is open to new content types. The one thing these
cannot check is whether Canvas accepts the package — that is the manual import acceptance gate.
"""

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from coursekit.emit import cartridge
from coursekit.emit.cartridge import CartridgeItem
from coursekit.generate.page import page as P
from coursekit.generate.quiz import bank as B


def _write_page(root, week, title, slug):
    P.reset()
    P.init(f"c-{week}", title=title, slug=slug, week_ref=week)
    P.put_block(P.build_block(kind="heading", block_id="h", text="Loops", level=2, role="concept"))
    P.put_block(P.build_block(kind="bullets", block_id="b", items=["for loops repeat"]))
    d = root / "pages" / week
    d.mkdir(parents=True)
    (d / "page.json").write_text(P.get().model_dump_json(), encoding="utf-8")


def _write_quiz(root, week, title):
    B.reset()
    B.init(f"test-{week}", None, title=title, source=f"{week}.md")
    B.create_group("c1", "Loops", "multiple_choice")
    for i, lbl in enumerate("ABCD"):
        B.put_variant(B.MCVariant(
            group_id="c1", label=lbl, variant_summary=f"angle {lbl}",
            question_text=f"Q{lbl}: what is `x < {i}`?", text_format="markdown",
            options=["one", "two", "three", "four"], correct_index=i))
    d = root / "quizzes" / week
    d.mkdir(parents=True)
    (d / "bank.json").write_text(B.get().model_dump_json(), encoding="utf-8")


@pytest.fixture
def course(tmp_path):
    """A course with one week holding both a page and a quiz, plus a context title."""
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    (root / ".vtconfig" / "context.yaml").write_text(
        "course_title: Test Course\nweeks:\n  week 3: {title: Repetition}\n", encoding="utf-8")
    _write_page(root, "week-3", "Week 3: Repetition", "week-3-repetition")
    _write_quiz(root, "week-3", "Week 3 Quiz")
    return root


def _zip(root):
    out = cartridge.write_course_imscc(root)
    return out, zipfile.ZipFile(out)


# ---------------------------------------------------- structure

def test_pages_and_quizzes_land_as_typed_module_items(course):
    _out, z = _zip(course)
    mm = z.read("course_settings/module_meta.xml").decode()
    assert "<content_type>WikiPage</content_type>" in mm
    assert "<content_type>Quizzes::Quiz</content_type>" in mm
    assert "Repetition" in mm                              # module titled from context.yaml


def test_every_packaged_xml_is_well_formed(course):
    _out, z = _zip(course)
    for n in z.namelist():
        if n.endswith((".xml", ".qti")):
            ET.fromstring(z.read(n))                       # raises on malformed


def test_quiz_questions_land_in_non_cc_assessments(course):
    _out, z = _zip(course)
    nc = [n for n in z.namelist() if n.startswith("non_cc_assessments/")]
    assert len(nc) == 1
    body = z.read(nc[0]).decode()
    assert "response_label" in body                        # the actual question options
    # the CC-profile stub is present and deliberately empty (questions live in non_cc)
    stub = [n for n in z.namelist() if n.endswith("assessment_qti.xml")][0]
    assert "cc.exam.v0p1" in z.read(stub).decode()


def test_every_manifest_reference_resolves(course):
    _out, z = _zip(course)
    names = set(z.namelist())
    man = z.read("imsmanifest.xml").decode()
    mm = z.read("course_settings/module_meta.xml").decode()
    # every module item points at a declared resource
    res_ids = set(re.findall(r'<resource identifier="([^"]+)"', man))
    refs = set(re.findall(r"<identifierref>([^<]+)</identifierref>", mm))
    assert refs <= res_ids
    # every <dependency> points at a declared resource
    deps = set(re.findall(r'<dependency identifierref="([^"]+)"', man))
    assert deps <= res_ids
    # every file href in the manifest exists in the zip
    for href in re.findall(r'<file href="([^"]+)"', man):
        assert href in names, href


def test_the_canvas_importer_marker_is_present(course):
    _out, z = _zip(course)
    assert "course_settings/canvas_export.txt" in z.namelist()


def test_ids_are_deterministic(course):
    out1 = cartridge.write_course_imscc(course, out_path=course / "a.imscc")
    man1 = zipfile.ZipFile(out1).read("imsmanifest.xml")
    out2 = cartridge.write_course_imscc(course, out_path=course / "b.imscc")
    man2 = zipfile.ZipFile(out2).read("imsmanifest.xml")
    assert man1 == man2                                    # stable re-emit


def test_empty_course_returns_none(tmp_path):
    assert cartridge.write_course_imscc(tmp_path) is None


def test_duplicate_slug_raises_a_collision_that_names_both_sources(course):
    """Two page.json with the same slug (e.g. a decomposed AND a monolithic page for one week) both
    map to wiki_content/<slug>.html — that must be a clear, sourced error, not a bare traceback."""
    # a second week-3 page, same slug, in a parallel tree — exactly the leftover-copy case
    _write_page(course / "pages-decomposed", "week-3", "Week 3: Repetition", "week-3-repetition")
    with pytest.raises(cartridge.CartridgeCollision) as ei:
        cartridge.write_course_imscc(course, out_path=course / "dup.imscc")
    msg = str(ei.value)
    assert "week-3-repetition.html" in msg                  # the colliding file
    assert str((course / "pages" / "week-3" / "page.json")) in msg          # source A named
    assert "pages-decomposed" in msg                        # source B named
    assert not (course / "dup.imscc").exists()              # nothing written on the error path


# ---------------------------------------------------- the extensibility seam

def test_a_new_content_type_is_one_source(course):
    """Adding a content type is a new CartridgeSource — the assembler needs no change. Prove it with
    a throwaway 'page' of a different content_type routed through the same assembler."""
    class DiscussionsSource:
        def collect(self, path):
            return [CartridgeItem(
                week_key="3", content_type="DiscussionTopic", title="Week 3 Discussion",
                resource_id="gdisc1", item_id="gdiscitem1",
                resource_xml='    <resource identifier="gdisc1" type="imsdt_xmlv1p1">\n'
                             '      <file href="gdisc1/discussion.xml"/>\n    </resource>',
                files={"gdisc1/discussion.xml": "<topic/>"}, rank=2)]

    from coursekit.emit.sources.pages import PagesSource
    out = cartridge.write_course_imscc(
        course, out_path=course / "ext.imscc",
        sources=[PagesSource(), DiscussionsSource()])
    z = zipfile.ZipFile(out)
    mm = z.read("course_settings/module_meta.xml").decode()
    assert "<content_type>DiscussionTopic</content_type>" in mm   # the new type flowed through
    assert "gdisc1/discussion.xml" in z.namelist()
