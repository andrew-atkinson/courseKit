"""CORE-5: a course whose units aren't weeks works through every verb. The session course here has two
units, `intro` and `loops`, declared in coursekit's overlay with no week numbers anywhere; a weekly course
keeps its `week-N` names. Offline. See agent/core-5-design.md.
"""

import json

import pytest

from coursekit import cli, outcomes, records
from coursekit.census import build_census
from coursekit.course import Course, unit_slug
from coursekit.discover import find_units
from coursekit.generate.page import build as pagebuild
from coursekit.generate.page.concept_map import concept_map_path, load_for_unit
from coursekit.generate.page.segment import materials_path
from coursekit.generate.quiz.generator import QuizGenerator
from coursekit.pipeline import run_unit
from coursekit.providers import OpenAICompatProvider
from tests.test_quiz_records import EU, _Endpoint
from tests.test_records_everywhere import Model


def _quiet(fn, *a, **k):
    with outcomes.capture(sink=lambda n: None):
        return fn(*a, **k)


@pytest.fixture
def sessions(tmp_path):
    """Two sessions in one day: declared in coursekit's overlay, each with its own doc, no week anywhere."""
    root = tmp_path / "intensive"
    vt = root / ".vtconfig"
    vt.mkdir(parents=True)
    (vt / "context.yaml").write_text("course_title: Intensive\n", encoding="utf-8")
    (vt / "quiz.yaml").write_text("eu_question: true\n", encoding="utf-8")
    (vt / "structure.coursekit.yaml").write_text(
        "weeks:\n"
        "  intro: {title: Session 1 — Intro, module: Day 1, doc: notes/intro.md}\n"
        "  loops: {title: Session 2 — Loops, module: Day 1, doc: notes/loops.md}\n", encoding="utf-8")
    (root / "notes").mkdir()
    for s in ("intro", "loops"):
        (root / "notes" / f"{s}.md").write_text(
            "Object literals bundle named values.\n\nArrays hold many of them, in order.\n" * 20, encoding="utf-8")
        (root / "notes" / "1 lecture.knowledge.json").write_text(
            json.dumps({"concepts": [{"name": "object literal"}]}), encoding="utf-8")
    return root


def _unit(root, s, subdir="quizzes"):
    (unit,) = find_units(root / "notes" / f"{s}.md", subdir=subdir)
    return unit


def _analyze(root, monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "m")
    monkeypatch.setattr(cli, "_build_provider", Model)
    assert _quiet(cli.main, ["analyze", str(root)]) == 0


def test_a_units_name_on_disk_keeps_a_weekly_courses_names():
    assert [unit_slug(i) for i in ("3", "intro", "Session 2")] == ["week-3", "intro", "session-2"]


def test_a_run_carries_the_course_models_unit(sessions):
    u = _unit(sessions, "loops")
    assert (u.id, u.slug, u.label, u.order, u.module) == ("loops", "loops", "Session 2 — Loops", 1, "Day 1")
    assert u.output_dir == sessions / "quizzes" / "loops"


def test_analyze_writes_each_sessions_concept_map_by_its_name(sessions, monkeypatch):
    _analyze(sessions, monkeypatch)
    concepts = sessions / ".vtconfig" / "concepts"
    assert sorted(p.name for p in concepts.iterdir()) == [
        "intro.materials.json", "intro.record.json", "intro.yaml",
        "loops.materials.json", "loops.record.json", "loops.yaml"]
    assert materials_path(sessions, "intro") == concepts / "intro.materials.json"
    assert _quiet(records.status, concepts, "intro.record.json").state == "current"
    assert [(a.unit, a.slug) for a in Course.load(sessions).artifacts_for(kind="concept_map")] == [
        ("intro", "intro"), ("loops", "loops")]


def test_a_sessions_quiz_and_pages_are_built_from_its_concept_map(sessions, monkeypatch):
    _analyze(sessions, monkeypatch)
    quiz = _unit(sessions, "intro")
    assert load_for_unit(quiz).enduring_understanding                     # found by the unit's id
    res = _quiet(run_unit, quiz, OpenAICompatProvider(client=_Endpoint(), name="f"), "m", QuizGenerator())
    assert EU in json.loads((res.output_dir / "bank.json").read_text())["groups"]   # the EU question had a map
    page = _quiet(pagebuild.build_page_unit, _unit(sessions, "intro", "pages"), Model(), "m", function="overview")
    assert page.output_dir == sessions / "pages" / "intro-overview"
    pj = json.loads((page.output_dir / "page.json").read_text())
    assert (pj["slug"], pj["unit_ref"]) == ("intro-overview", "intro")      # not `week-None-overview`


def test_the_census_sees_a_sessions_concept_map(sessions, monkeypatch):
    _analyze(sessions, monkeypatch)
    census = _quiet(build_census, sessions)
    assert [(w.unit, w.concept_map) for w in census.units] == [("intro", True), ("loops", True)]


def test_a_weekly_unit_keeps_its_week_names(tmp_path):
    root = tmp_path / "weekly"
    (root / ".vtconfig").mkdir(parents=True)
    (root / ".vtconfig" / "context.yaml").write_text("course_title: Weekly\nweeks:\n  week 3: {title: Loops}\n",
                                                     encoding="utf-8")
    (root / "output").mkdir()
    (root / "output" / "week-3.md").write_text("Loops.\n", encoding="utf-8")
    (u,) = find_units(root / "output" / "week-3.md", subdir="pages")
    assert (u.id, u.slug, u.output_dir.name) == ("3", "week-3", "week-3")
    assert concept_map_path(root, u.id).name == "week-3.yaml"
    assert materials_path(root, u.id).name == "week-3.materials.json"
    assert pagebuild.page_dir(u, "glossary").name == "week-3-glossary"


# ------------------------------------------------------------------ CORE-5.2: choosing units by id or title

def _plan(capsys, *args):
    assert cli.main(["generate", *args, "--quizzes", "--dry-run"]) == 0
    return [line.strip() for line in capsys.readouterr().out.splitlines() if "[plan]" in line]


@pytest.mark.parametrize("flag, ref", [("--unit", "intro"), ("--unit", "Session 1 — Intro"),
                                       ("--unit", "session 1 — intro"), ("--week", "Session 1 — Intro")])
def test_a_unit_is_chosen_by_its_id_or_its_title(sessions, capsys, flag, ref):
    assert _plan(capsys, str(sessions), flag, ref) == ["[plan] Session 1 — Intro"]


def test_several_units_are_chosen_in_the_courses_order(sessions, capsys):
    assert _plan(capsys, str(sessions), "--unit", "loops", "--unit", "intro") == [
        "[plan] Session 1 — Intro", "[plan] Session 2 — Loops"]


def test_a_unit_the_course_doesnt_have_says_which_it_has(sessions, capsys):
    assert cli.main(["generate", str(sessions), "--unit", "outro", "--dry-run"]) != 0
    err = capsys.readouterr().err
    assert "no unit 'outro' in this course" in err
    assert "intro (Session 1 — Intro), loops (Session 2 — Loops)" in err


@pytest.mark.parametrize("verb", ["analyze", "evaluate", "fix"])
def test_every_verb_that_chooses_units_checks_them(sessions, capsys, verb):
    assert cli.main([verb, str(sessions), "--unit", "outro"]) != 0
    assert "no unit 'outro'" in capsys.readouterr().err


def test_in_a_weekly_course_unit_and_week_are_the_same(tmp_path, capsys):
    root = tmp_path / "weekly"
    (root / ".vtconfig").mkdir(parents=True)
    (root / ".vtconfig" / "context.yaml").write_text(
        "course_title: Weekly\nweeks:\n  week 3: {title: Loops}\n  week 4: {title: Noise}\n", encoding="utf-8")
    (root / "output").mkdir()
    for n in ("3", "4"):
        (root / "output" / f"week-{n}.md").write_text("Text.\n", encoding="utf-8")
    want = ["[plan] Week 4: Noise"]
    assert _plan(capsys, str(root), "--unit", "4") == _plan(capsys, str(root), "--week", "4") == want
    assert _plan(capsys, str(root), "--weeks", "4-4") == _plan(capsys, str(root), "--unit", "Week 4: Noise") == want
    assert cli.main(["generate", str(root), "--week", "9", "--dry-run"]) != 0
    assert "(units: 3 (Week 3: Loops), 4 (Week 4: Noise))" in capsys.readouterr().err


def test_a_document_quizs_unit_can_be_chosen_though_it_has_no_text_of_its_own(tmp_path):
    from coursekit.course import check_selection
    from coursekit.outcomes import CoursekitError
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    (root / "quizzes" / "week-2-barrett-reading").mkdir(parents=True)
    (root / "quizzes" / "week-2-barrett-reading" / "bank.json").write_text("{}", encoding="utf-8")
    _quiet(check_selection, root, ["2"])                   # unit 2 owns a quiz: it exists
    with pytest.raises(CoursekitError, match="no unit '9'"):
        _quiet(check_selection, root, ["9"])


def test_a_module_script_takes_a_unit_too(sessions, monkeypatch, capsys):
    import sys
    from coursekit.generate.quiz import eu
    monkeypatch.setattr(sys, "argv", ["eu", str(sessions), "--unit", "Session 2 — Loops"])
    assert eu.main() == 1                                  # found the unit; it has no concept map yet
    assert "Session 2 — Loops has no enduring understanding" in capsys.readouterr().out


# ------------------------------------------------------------------ CORE-5.3: what coursekit writes says unit

def test_the_census_labels_each_unit_by_its_own_title_in_the_courses_order(sessions, monkeypatch):
    overlay = sessions / ".vtconfig" / "structure.coursekit.yaml"
    overlay.write_text(overlay.read_text().replace("weeks:", "units:"), encoding="utf-8")
    lines = overlay.read_text().splitlines()
    overlay.write_text("\n".join([lines[0], lines[2], lines[1]]) + "\n", encoding="utf-8")   # loops first
    census = _quiet(build_census, sessions)
    assert [(w.unit, w.label) for w in census.units] == [("loops", "Session 2 — Loops"), ("intro", "Session 1 — Intro")]
    report = __import__("coursekit.census", fromlist=["render_report"]).render_report(census)
    assert "| Unit |" in report and "2 units ·" in report and "Week intro" not in report
    assert "units" in json.loads(census.model_dump_json()) and "weeks" not in json.loads(census.model_dump_json())


@pytest.mark.parametrize("section", ["units", "weeks"])
def test_the_overlay_declares_units_under_units_or_its_old_name_weeks(sessions, section):
    overlay = sessions / ".vtconfig" / "structure.coursekit.yaml"
    overlay.write_text(overlay.read_text().replace("weeks:", f"{section}:"), encoding="utf-8")
    units = _quiet(Course.load, sessions).units
    assert [(u.id, u.label, u.module, u.doc.name) for u in units] == [
        ("intro", "Session 1 — Intro", "Day 1", "intro.md"), ("loops", "Session 2 — Loops", "Day 1", "loops.md")]


def test_an_overlay_cant_declare_units_in_both_places(sessions):
    from coursekit.outcomes import CoursekitError
    overlay = sessions / ".vtconfig" / "structure.coursekit.yaml"
    overlay.write_text(overlay.read_text() + "units:\n  outro: {title: Outro}\n", encoding="utf-8")
    with pytest.raises(CoursekitError, match="both `units:` and `weeks:`"):
        _quiet(Course.load, sessions)


def test_propose_writes_units_and_a_redraft_replaces_the_old_weeks(tmp_path):
    from coursekit import settings
    from coursekit.ingest import propose as P
    from coursekit.outcomes import CoursekitError
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    (root / "week-3").mkdir()
    (root / "week-3" / "a.pdf").write_bytes(b"%PDF")
    (root / ".vtconfig" / "structure.coursekit.yaml").write_text("weeks:\n  week 3: {title: Old}\n", encoding="utf-8")
    with pytest.raises(CoursekitError, match="already declares `weeks:`"):
        P.write_overlay(P.propose(root))                       # the old name holds the faculty's edits too
    P.write_overlay(P.propose(root), force=True)
    data = settings.read(root, "structure")
    assert "week 3" in data["units"] and "weeks" not in data


@pytest.mark.parametrize("old, new", [("week", "unit")])
def test_an_expectation_scoped_to_week_reads_as_unit(old, new):
    from coursekit.coursestructure import _parse_expect
    def scheme(scope):
        return _parse_expect({"defaults": [{"scope": scope, "artifact": "quiz", "count": 1}],
                              "overrides": {scope: {"3": {"quiz": 0}}}})
    assert scheme(old) == scheme(new) and scheme(old).for_unit("3") == {} and scheme(old).for_unit("4") == {"quiz": 1}


def test_propose_expectations_writes_unit_scopes(tmp_path):
    from coursekit.ingest import propose_expectations as pe
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    for n in ("1", "2"):
        (root / "pages" / f"week-{n}").mkdir(parents=True)
        (root / "pages" / f"week-{n}" / "page.json").write_text(json.dumps({"unit_ref": f"week-{n}"}), encoding="utf-8")
    expect, _ = _quiet(pe.propose_expectations, root)
    assert {r["scope"] for r in expect["defaults"]} == {"unit"}


@pytest.mark.parametrize("key", ["unit_ref", "week_ref"])
def test_an_artifact_names_its_unit_by_unit_ref_or_its_old_name_week_ref(tmp_path, key):
    from coursekit.generate.assignment.assignment import Assignment
    from coursekit.generate.page.page import Page
    assert Page.model_validate({"page_id": "p", key: "week-3"}).unit_ref == "week-3"
    assert Assignment.model_validate({"assignment_id": "a", "title": "T", "task": "Do it.", key: "week-3"}).unit_ref == "week-3"
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    (root / "pages" / "stray").mkdir(parents=True)
    (root / "pages" / "stray" / "page.json").write_text(json.dumps({key: "week-3"}), encoding="utf-8")
    assert [a.unit for a in _quiet(Course.load, root).artifacts] == ["3"]      # moved by its own reference
    assert "week_ref" not in Page(page_id="p", unit_ref="week-3").model_dump()    # new files say unit_ref


def test_a_model_free_page_is_titled_by_its_units_label_once(sessions, monkeypatch, tmp_path):
    from tests.test_records_everywhere import _analyze as weekly_analyze, _course as weekly_course, _unit as weekly_unit
    _analyze(sessions, monkeypatch)
    for function in ("overview", "recap"):
        out = _quiet(pagebuild.build_page_unit, _unit(sessions, "intro", "pages"), Model(), "m", function=function).output_dir
        assert json.loads((out / "page.json").read_text())["title"].startswith("Session 1 — Intro")
    root = weekly_course(tmp_path)
    weekly_analyze(root)
    out = _quiet(pagebuild.build_page_unit, weekly_unit(root, subdir="pages"), Model(), "m", function="overview").output_dir
    assert json.loads((out / "page.json").read_text())["title"] == "Week 7: Objects"     # not "Week 7: Week 7: …"


# ------------------------------------------------------------------ CORE-5.4: a cartridge module per unit

def _modules(imscc):
    """[(module title, [item titles])] from a cartridge's module_meta.xml, in order."""
    import re
    import zipfile
    mm = zipfile.ZipFile(imscc).read("course_settings/module_meta.xml").decode()
    return [(re.search(r"<title>(.*?)</title>", m).group(1), re.findall(r"<item [^>]*>\s*<content_type>[^<]*</content_type>"
                                                                      r"\s*<workflow_state>[^<]*</workflow_state>\s*<title>(.*?)</title>", m))
            for m in re.findall(r"<module [^>]*>.*?</module>", mm, re.S)]


@pytest.fixture
def built(sessions, monkeypatch):
    """The session course with a quiz and an overview page per session, and units declared loops-first."""
    _analyze(sessions, monkeypatch)
    for s in ("intro", "loops"):
        _quiet(run_unit, _unit(sessions, s), OpenAICompatProvider(client=_Endpoint(), name="f"), "m", QuizGenerator())
        _quiet(pagebuild.build_page_unit, _unit(sessions, s, "pages"), Model(), "m", function="overview")
    overlay = sessions / ".vtconfig" / "structure.coursekit.yaml"
    head, intro, loops = overlay.read_text().splitlines()
    overlay.write_text("\n".join([head, loops, intro]) + "\n", encoding="utf-8")      # the course's order: loops first
    return sessions


def test_a_course_cartridge_has_a_module_per_unit_titled_and_ordered_by_the_course(built):
    from coursekit.emit import cartridge
    mods = _modules(_quiet(cartridge.write_course_imscc, built))
    assert [title for title, _ in mods] == ["Session 2 — Loops", "Session 1 — Intro"]
    assert all(len(items) == 2 for _, items in mods)                       # its overview page, then its quiz
    assert mods[0][1][0].startswith("Session 2 — Loops")


def test_the_pages_cartridge_follows_the_courses_order_too(built):
    import zipfile
    from coursekit.emit import cc
    names = [n for n in zipfile.ZipFile(_quiet(cc.write_imscc, built)).namelist() if n.startswith("wiki_content/")]
    assert names == ["wiki_content/loops-overview.html", "wiki_content/intro-overview.html"]


def test_an_artifact_with_no_unit_goes_in_the_courses_own_module(built):
    from coursekit.emit import cartridge
    stray = built / "pages" / "welcome"
    stray.mkdir()
    page = json.loads((built / "pages" / "intro-overview" / "page.json").read_text())
    stray.joinpath("page.json").write_text(json.dumps({**page, "unit_ref": None, "slug": "welcome",
                                                       "page_id": "welcome", "title": "Welcome"}), encoding="utf-8")
    mods = _modules(_quiet(cartridge.write_course_imscc, built))
    assert mods[-1] == ("Intensive", ["Welcome"])                           # course scope, after every unit
