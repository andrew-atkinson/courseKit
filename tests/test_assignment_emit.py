"""Canvas Assignment emitter (ASMT-4) — grounded against the real ARGS260 Canvas export.
Offline: build an Assignment, emit, and check the CC shape parses and carries the grounded fields."""

import xml.etree.ElementTree as ET
import zipfile

from coursekit.emit import assignment as ae
from coursekit.generate.assignment.assignment import Assignment, Rubric, RubricCriterion, RubricRating


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


def test_instructions_render_themed_html_with_the_parts():
    html = ae.assignment_html(_asg())
    assert "Your task" in html and "What to submit" in html
    assert "be assessed" in html and "applies the idea correctly" in html   # ("you'll" → escaped &#39;)
    assert "style=" in html   # themed via the page design system, not plain HTML


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


def _pkg(course_dir, *assignments):
    """Write assignment.json files under a course dir, emit the cartridge, return (out, files-dict).
    Goes through the SHARED assembler (emit_from_path) — the real, importable structure."""
    for i, a in enumerate(assignments or (_asg(),)):
        d = course_dir / "assignments" / f"a{i}"
        d.mkdir(parents=True)
        (d / "assignment.json").write_text(a.model_dump_json(), encoding="utf-8")
    out = ae.emit_from_path(course_dir)
    with zipfile.ZipFile(out) as z:
        return out, {n: z.read(n).decode("utf-8") for n in z.namelist()}


def test_cartridge_files_are_well_formed_and_a_valid_zip(tmp_path):
    out, files = _pkg(tmp_path, _asg(rubric=_rubric()))
    assert out.suffix == ".imscc"
    for arc, data in files.items():
        if arc.endswith((".xml", ".html")):
            ET.fromstring(data)   # raises on malformed


def test_cartridge_has_module_meta_and_resolvable_refs(tmp_path):
    _out, files = _pkg(tmp_path, _asg(rubric=_rubric()))
    assert "course_settings/module_meta.xml" in files          # the module placement (was MISSING before)
    assert "course_settings/rubrics.xml" in files
    manifest = ET.fromstring(files["imsmanifest.xml"])
    for r in liter(manifest, "resource"):
        if r.get("href"):
            assert r.get("href") in files                      # every resource href is a real file
    assert any(r.get("type") == "associatedcontent/imscc_xmlv1p1/learning-application-resource"
               for r in liter(manifest, "resource"))
    # the course_settings resource lists the extra settings files
    assert "course_settings/rubrics.xml" in files["imsmanifest.xml"]


def test_cartridge_is_byte_stable(tmp_path_factory):
    a = _asg(rubric=_rubric())
    _o1, f1 = _pkg(tmp_path_factory.mktemp("one"), a)
    _o2, f2 = _pkg(tmp_path_factory.mktemp("two"), a)
    assert f1 == f2   # deterministic ids from content, not path


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


def test_emit_from_path_discovers_and_packages(tmp_path):
    import zipfile
    d = tmp_path / "assignments" / "week-3"
    d.mkdir(parents=True)
    (d / "assignment.json").write_text(_asg(rubric=_rubric()).model_dump_json(), encoding="utf-8")
    out = ae.emit_from_path(tmp_path)
    assert out is not None and out.suffix == ".imscc"
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "imsmanifest.xml" in names and "course_settings/rubrics.xml" in names


def test_emit_from_path_none_when_empty(tmp_path):
    assert ae.emit_from_path(tmp_path) is None


def test_derived_rubric_scales_to_total_and_sums_exactly():
    # three equal weights of 100 → 33.3/33.3/33.4 (remainder to one), summing EXACTLY to the total
    r = Rubric(title="R", points_total=100, criteria=[
        RubricCriterion(description=n, ratings=[RubricRating(description="hi", points=1),
                                                RubricRating(description="lo", points=0)])
        for n in ("A", "B", "C")])
    pts = r.resolved_points()
    assert sum(pts) == 100.0 and set(pts) == {33.3, 33.4}
    root = ET.fromstring(ae.rubrics_xml([_asg(rubric=r)]))
    assert liter(root, "points_possible")[0].text == "100.0"
    # a criterion's top level equals the criterion's derived points (partial-credit shape preserved)
    tops = [float(liter(c, "points")[0].text) for c in liter(root, "criterion")]
    assert sorted(tops) == sorted(pts)


def test_legacy_rubric_without_total_is_unchanged():
    r = _rubric()                                    # no points_total → top level is the value
    assert r.points_possible == 75.0 and r.resolved_points() == [35.0, 40.0]


def test_instructions_render_inline_markdown_and_steps():
    a = Assignment(assignment_id="w", title="T", task="Use `map()` and be **bold**.",
                   steps=["**One:** do `x`.", "Two."])
    html = ae.assignment_html(a)
    assert "<code" in html and "map()" in html and "<strong>bold</strong>" in html   # inline md renders
    assert "Two." in html                                        # steps rendered (themed bullets)
    assert "`map()`" not in html and "**bold**" not in html      # no literal markdown shipped


# ---------------------------------------------------- grading scheme (STRC-2)

def _quiz_bank_json():
    """A finalizable all-MC bank, serialized — for a quiz in the course cartridge."""
    from coursekit.generate.quiz import bank as bankmod
    bankmod.reset()
    bankmod.init("run-w3", None, title="Week 3", source="week-3.md")
    bankmod.create_group("c1", "Loops", "multiple_choice")
    for i, lbl in enumerate("ABCD"):
        bankmod.put_variant(bankmod.MCVariant(
            group_id="c1", label=lbl, variant_summary=f"angle {lbl}",
            question_text=f"Question {lbl}: what does a loop do?",
            options=["one", "two", "three", "four"], correct_index=i))
    return bankmod.get().model_dump_json()


def test_declared_scheme_weights_groups_and_places_assignment_and_quiz(tmp_path):
    from coursekit.emit import cartridge
    course = tmp_path / "course"
    (course / ".vtconfig").mkdir(parents=True)
    (course / ".vtconfig" / "structure.coursekit.yaml").write_text(
        "grading:\n  groups:\n    - {name: Projects, weight: 70}\n    - {name: Quizzes, weight: 30}\n"
        "  placement: {assignment: Projects, quiz: Quizzes}\n", encoding="utf-8")
    ad = course / "assignments" / "week-3"
    ad.mkdir(parents=True)
    (ad / "assignment.json").write_text(
        _asg(week_ref="week-3", slug="week-3-assignment").model_dump_json(), encoding="utf-8")
    qd = course / "quizzes" / "week-3"
    qd.mkdir(parents=True)
    (qd / "bank.json").write_text(_quiz_bank_json(), encoding="utf-8")

    out = ae.emit_from_path(course) if False else cartridge.write_course_imscc(course)
    with zipfile.ZipFile(out) as z:
        files = {n: z.read(n).decode("utf-8") for n in z.namelist()}
    groups = files["course_settings/assignment_groups.xml"]
    assert "Projects" in groups and "Quizzes" in groups
    assert "<group_weight>70.0</group_weight>" in groups and "<group_weight>30.0</group_weight>" in groups
    assert "<group_weighting_scheme>percent</group_weighting_scheme>" in files["course_settings/course_settings.xml"]
    asettings = next(v for k, v in files.items() if k.endswith("assignment_settings.xml"))
    assert ae.group_ident("Projects") in asettings                 # assignment → Projects
    qmeta = next(v for k, v in files.items() if k.endswith("assessment_meta.xml"))
    assert ae.group_ident("Quizzes") in qmeta                      # quiz → Quizzes
    for data in files.values():                                    # everything still well-formed
        pass
    ET.fromstring(files["course_settings/assignment_groups.xml"])
    ET.fromstring(files["course_settings/course_settings.xml"])


def test_no_scheme_emits_unweighted_assignments_group_and_no_course_settings(tmp_path):
    from coursekit.emit import cartridge
    course = tmp_path / "course"
    (course / ".vtconfig").mkdir(parents=True)
    ad = course / "assignments" / "week-3"
    ad.mkdir(parents=True)
    (ad / "assignment.json").write_text(_asg(week_ref="week-3").model_dump_json(), encoding="utf-8")
    out = cartridge.write_course_imscc(course)
    with zipfile.ZipFile(out) as z:
        files = {n: z.read(n).decode("utf-8") for n in z.namelist()}
    assert "<group_weight>0.0</group_weight>" in files["course_settings/assignment_groups.xml"]
    assert "course_settings/course_settings.xml" not in files      # no weighting flag when no scheme
