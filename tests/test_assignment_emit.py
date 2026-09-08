"""Canvas Assignment emitter (ASMT-4) — grounded against reference/arph201's assignment_settings.xml.
Offline: build an Assignment, emit, and check the CC shape parses and carries the grounded fields."""

import xml.etree.ElementTree as ET
import zipfile

from coursekit.emit import assignment as ae
from coursekit.generate.assignment.assignment import (Assignment, Rubric, RubricCriterion,
                                                      RubricRating, render_instructions)


def _rubric():
    return Rubric(title="Project Rubric", criteria=[
        RubricCriterion(description="Analysis", long_description="depth of the written analysis",
                        ratings=[RubricRating(description="Excellent", points=35),
                                 RubricRating(description="Good", points=25),
                                 RubricRating(description="No marks", points=0)]),
        RubricCriterion(description="Craft",
                        ratings=[RubricRating(description="Strong", points=40),
                                 RubricRating(description="Weak", points=10)])])


def _asg(**kw):
    base = dict(assignment_id="wk3", title="Apply the week's idea", slug="week-3-assignment",
                task="Take the idea and apply it to a situation from your own life; explain your choices.",
                overview="This assignment connects the week to your practice.",
                deliverable="A two-paragraph written response.",
                rubric_criteria=["applies the idea correctly", "justifies the choices"])
    base.update(kw)
    return Assignment(**base)


def liter(root, name):
    return [e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == name]


def test_instructions_are_canvas_safe_html_with_the_parts():
    html = render_instructions(_asg())
    assert "<h3>Your task</h3>" in html and "What to submit" in html
    assert "How you'll be assessed" in html and "<li>applies the idea correctly</li>" in html


def test_settings_xml_carries_the_grounded_fields():
    root = ET.fromstring(ae.assignment_settings_xml(_asg(points=15)))
    assert root.tag.endswith("assignment")
    assert liter(root, "submission_types")[0].text == "online_text_entry"
    assert liter(root, "points_possible")[0].text == "15.0"
    assert liter(root, "grading_type")[0].text == "points"
    assert liter(root, "assignment_group_identifierref")[0].text == ae.group_ident("Assignments")


def test_html_body_escapes_and_wraps():
    root = ET.fromstring(ae.assignment_html(_asg(title="Loops & <fun>")))
    assert liter(root, "title")[0].text == "Assignment: Loops & <fun>"   # parsed back to the original


def test_every_package_file_is_well_formed_xml_or_html():
    for arc, data in ae.package_files([_asg()], "Creative Coding").items():
        if arc.endswith((".xml", ".html")):
            ET.fromstring(data)   # raises on malformed


def test_manifest_references_resolve_and_type_is_the_grounded_one():
    a = _asg()
    files = ae.package_files([a], "Creative Coding")
    manifest = ET.fromstring(files["imsmanifest.xml"])
    res = liter(manifest, "resource")
    assert any(r.get("type") == "associatedcontent/imscc_xmlv1p1/learning-application-resource"
               for r in res)
    # every resource href exists in the package
    for r in res:
        if r.get("href"):
            assert r.get("href") in files


def test_write_imscc_is_a_valid_zip(tmp_path):
    out = ae.write_imscc([_asg()], "Creative Coding", tmp_path / "assignments")
    assert out.suffix == ".imscc"
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        assert "imsmanifest.xml" in z.namelist()


def test_reemit_is_byte_stable():
    a = _asg()
    assert ae.package_files([a], "C") == ae.package_files([a], "C")   # deterministic ids


# ---------------------------------------------------- structured rubric (ASMT-7)

def test_rubric_totals_from_criteria_and_levels():
    r = _rubric()
    assert r.points_possible == 75.0            # 35 + 40 (each criterion's top level)
    assert r.criteria[0].points == 35.0


def test_rubric_xml_carries_criteria_and_levels():
    root = ET.fromstring(ae.rubrics_xml([_asg(rubric=_rubric())]))
    assert len(liter(root, "criterion")) == 2
    assert len(liter(root, "rating")) == 5      # 3 + 2 performance levels
    assert liter(root, "points_possible")[0].text == "75.0"


def test_assignment_attaches_rubric_and_derives_points():
    a = _asg(rubric=_rubric(), points=10)       # the plain points=10 is ignored when a rubric is set
    root = ET.fromstring(ae.assignment_settings_xml(a))
    assert liter(root, "rubric_identifierref")[0].text == ae.rubric_ident(a)
    assert liter(root, "rubric_use_for_grading")[0].text == "true"
    assert liter(root, "points_possible")[0].text == "75.0"   # the rubric total, not 10


def test_package_includes_rubrics_and_bundled_course_settings():
    files = ae.package_files([_asg(rubric=_rubric())], "Creative Coding")
    assert "course_settings/rubrics.xml" in files
    assert "course_settings/canvas_export.txt" in files       # bundled, like the page cartridge
    for arc, data in files.items():
        if arc.endswith((".xml", ".html")):
            ET.fromstring(data)
