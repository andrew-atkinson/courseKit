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
    assert (pj["slug"], pj["week_ref"]) == ("intro-overview", "intro")      # not `week-None-overview`


def test_the_census_sees_a_sessions_concept_map(sessions, monkeypatch):
    _analyze(sessions, monkeypatch)
    census = _quiet(build_census, sessions)
    assert [(w.week, w.concept_map) for w in census.weeks] == [("intro", True), ("loops", True)]


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
