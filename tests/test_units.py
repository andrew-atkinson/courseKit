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


# ------------------------------------------------------------------ CORE-5.5: the course's word for a unit

def _rebuilt_briefs(root) -> dict:
    """Every recorded step's brief, rebuilt from today's files with the run's own builder: {step: messages}."""
    import importlib
    out = {}
    for rp in sorted(root.rglob("*record.json")):
        rec = records.load(rp.parent, rp.name)
        rebuild = importlib.import_module(records._REBUILDERS[rec["kind"]]).rebuild
        out |= {f"{rp.parent.relative_to(root).as_posix()} {s['step']}": rebuild(rec, s, rp.parent) for s in rec["steps"] if "brief" in s}
    return out


def _critiques(root, unit) -> list:
    """What every critic and fixer shows the model for `unit`'s quiz and page."""
    from coursekit.generate.page import concept_delivery, consolidate, evaluate as pev, fix as pfix, groundedness as pg
    from coursekit.generate.page import pedagogy
    from coursekit.generate.page import page as pageir, tools as ptools
    from coursekit.generate.quiz import bank as qbank, evaluate as qev, fix as qfix, groundedness as qg, tools as qtools
    text, m = unit.transcript_path.read_text(), Model()
    b = qbank.Bank.model_validate_json((root / "quizzes" / unit.slug / "bank.json").read_text())
    page = pageir.Page.model_validate_json((root / "pages" / unit.slug / "page.json").read_text())
    qev.evaluate_bank(b, text, m, "m", project_root=root, reads=1)
    qg.evaluate_bank_groundedness(b, text, m, "m", project_root=root)
    pev.evaluate_page(page, text, m, "m", project_root=root, reads=1)
    pg.evaluate_page_groundedness(page, text, m, "m", project_root=root)
    pedagogy.evaluate_page_pedagogy(page, text, m, "m", project_root=root)
    concept_delivery.evaluate_page_concepts(page, text, m, "m", project_root=root, concepts=["Arrays"])
    qs = qtools.QuizTools(qbank.BankDraft.new("t"))
    qs.draft.bank = b
    gid, label = next((g.group_id, l) for g in b.groups.values() for l in g.variants)
    qfix.fix_one(qs, qev.Finding(unit.slug, gid, label, "s", "FLAG", "c"), text, m, "m", critic="C",
                 project_root=root, max_turns=1)
    ps = ptools.PageTools(pageir.PageDraft.new("t"))
    ps.draft.page = page
    pfix.fix_one_block(ps, qev.Finding(unit.slug, "d", "details", "s", "FLAG", "c"), text, m, "m", critic="C",
                       project_root=root, max_turns=1)
    consolidate.build_concept_map_from_text(text, m, "m", week="intro", project_root=root)   # analyze with no knowledge.json
    return m.seen


def test_a_course_that_names_its_unit_shows_the_model_its_word_and_never_week(sessions, monkeypatch):
    from coursekit.generate.assignment import build as assignment
    overlay = sessions / ".vtconfig" / "structure.coursekit.yaml"
    overlay.write_text("unit_noun: session\n" + overlay.read_text(), encoding="utf-8")
    _analyze(sessions, monkeypatch)
    intro = _unit(sessions, "intro")
    _quiet(run_unit, intro, OpenAICompatProvider(client=_Endpoint(), name="f"), "m", QuizGenerator())
    for kw in ({"generator": "monolithic"}, {"function": "glossary"}, {"function": "overview"}, {"function": "recap"}):
        _quiet(pagebuild.build_page_unit, _unit(sessions, "intro", "pages"), Model(), "m", **kw)
    _quiet(pagebuild.build_page_unit, _unit(sessions, "loops", "pages"), Model(), "m", generator="decompose")
    a = _unit(sessions, "intro", "assignments")
    _quiet(assignment.build_assignment, a, Model(), "m", a.output_dir)

    briefs = _quiet(_rebuilt_briefs, sessions)
    assert {k.split(" ", 1)[1].split(":")[0] for k in briefs} == {
        "analyze", "segment", "generate", "eu", "intro", "glossary", "build", "frame", "section", "close"}
    for k in ("pages/intro-overview build", "pages/intro-recap build"):         # a model-free page's brief is the page;
        assert briefs[k].pop("page_type").startswith("week_")         # its type is an IR name, not a word
    shown = json.dumps([briefs, _quiet(_critiques, sessions, intro)], ensure_ascii=False)
    assert "week" not in shown.lower()
    for said in ("The session's teaching material", "this session", "Session context —", "The session teaches",
                 "a session's key terms", "Concepts this session", "This session — Session 1 — Intro",
                 "The session's source material", "concept map** for one session"):
        assert said in shown


def test_the_noun_is_week_unless_the_course_says_otherwise(sessions):
    from coursekit import prompts, settings
    assert prompts.unit_noun(None) == prompts.unit_noun(sessions) == "week"
    assert "this week's own subject" in prompts.load("page", "frame", project_root=sessions).body
    _quiet(settings.set, sessions, "unit_noun", "class")
    assert prompts.unit_noun(sessions) == "class"
    body = prompts.load("assignment", "default", project_root=sessions).body
    assert "a single class is a focused task" in body and "several classes" in body
    with pytest.raises(outcomes.CoursekitError):
        settings.set(sessions, "unit_noun", "")
    assert [prompts.plural(n) for n in ("week", "class", "box", "study", "day", "y")] == \
        ["weeks", "classes", "boxes", "studies", "days", "ys"]


def test_a_courses_overview_pages_use_its_word_for_a_unit(tmp_path):
    from coursekit.generate import overview
    from coursekit.generate.page.concept_map import Concept, ConceptMap
    from tests.test_records_everywhere import _analyze as weekly_analyze, _course as weekly_course
    root = weekly_course(tmp_path)                       # the transcriber's weeks 7 and 8, in module Data
    (root / ".vtconfig" / "structure.coursekit.yaml").write_text("unit_noun: block\n", encoding="utf-8")
    weekly_analyze(root)
    _, entries = _quiet(overview.plan, root)
    pages = [e["build"](framing="").model_dump_json() for e in entries if "build" in e]
    assert "This block — Objects — is part of Data" in pages[0] and "Data spans 1 block(s)" in pages[-1]
    assert "what this block or module is about" in json.dumps(entries[0]["frame"])
    recap = overview.build_week_recap("C", "7", "Objects", "", ConceptMap(week="7", concepts=[Concept(name="Arrays")]),
                                      noun="block")
    assert recap.blocks["recall-0"].text == "Look back at Arrays in the block's material."


# ------------------------------------------------------------- CORE-5.7 — the last week-only paths
def _readings_course(tmp_path):
    """Two sessions declared by their sources alone (no `doc:`), the overlay listing `loops` first."""
    root = tmp_path / "readings"
    (root / ".vtconfig").mkdir(parents=True)
    (root / ".vtconfig" / "structure.coursekit.yaml").write_text(
        "units:\n"
        "  loops: {title: Session 2 — Loops, sources: [{path: texts/loops.txt}]}\n"
        "  intro: {title: Session 1 — Intro, sources: [{path: texts/intro.txt}, {path: texts/barrett.txt}]}\n",
        encoding="utf-8")
    (root / "texts").mkdir()
    for name in ("loops", "intro", "barrett"):
        (root / "texts" / f"{name}.txt").write_text(f"{name} repeats things.\n", encoding="utf-8")
    return root


def test_a_session_declared_by_its_sources_alone_is_ingested_where_every_verb_reads_it(tmp_path, capsys):
    from coursekit.ingest.ingest import ingest
    root = _readings_course(tmp_path)
    assert cli.main(["ingest", str(root), "--raw"]) == 0
    out = capsys.readouterr().out
    assert out.index("loops.txt") < out.index("intro.txt")              # the overlay's order
    assert "2 unit doc(s)" in out and "week" not in out.lower()
    assert "## barrett" in (root / "output" / "intro.md").read_text(encoding="utf-8")
    assert [(u.id, u.transcript_path) for u in find_units(root)] == \
        [("loops", root / "output" / "loops.md"), ("intro", root / "output" / "intro.md")]
    assert {d.name for _, d in ingest(root, raw=True, out_dir=tmp_path / "elsewhere")} == {"loops.md", "intro.md"}


def test_a_document_a_session_declares_gets_a_quiz_folder_named_by_that_session(tmp_path):
    from coursekit.generate.quiz import targeted
    root = _readings_course(tmp_path)
    unit, _ = targeted.prepare(root / "texts" / "barrett.txt")
    assert (unit.id, unit.output_dir) == ("intro", root / "quizzes" / "intro-barrett")


def test_a_session_course_gets_an_overview_per_session_and_one_for_its_module(sessions, monkeypatch):
    from coursekit import records, settings
    from coursekit.generate import overview
    _quiet(settings.set, sessions, "unit_noun", "session")     # before analyze: the noun is in its brief too
    _analyze(sessions, monkeypatch)
    _, entries = overview.plan(sessions, framing=False)
    pages = [e["build"]() for e in entries]
    assert [(e["unit"], p.slug, p.title) for e, p in zip(entries, pages)] == [
        ("intro", "intro-overview", "Session 1 — Intro"), ("loops", "loops-overview", "Session 2 — Loops"),
        (None, "module-day-1-overview", "Day 1")]
    shown = [p.model_dump(mode="json", exclude={"page_type"}) for p in pages]   # the whole page, block ids too; `week_overview` is an IR enum
    assert "week" not in json.dumps(shown).lower() and "This session — Session 1 — Intro" in json.dumps(shown, ensure_ascii=False)
    written = _quiet(overview.generate_overviews, sessions)
    assert [p.name for p in written] == ["intro-overview.html", "loops-overview.html", "module-day-1-overview.html"]
    with outcomes.capture(sink=lambda n: None):
        assert {records.status(r.parent, r.name).state for r in (sessions / "overview").glob("*.record.json")} == {"current"}
    intro = (sessions / "overview" / "intro-overview.record.json").read_text(encoding="utf-8")
    assert "concepts/intro.yaml" in intro and "concepts/loops.yaml" not in intro   # a page lists only its own map
    module = (sessions / "overview" / "module-day-1-overview.record.json").read_text(encoding="utf-8")
    assert "concepts/intro.yaml" in module and "concepts/loops.yaml" in module      # a module's, each of its units'
    _, framed = overview.plan(sessions, framing=True)
    assert framed[0]["frame"][-1]["content"].startswith("Title: Session 1 — Intro\n")   # the framing pass's title
    (sessions / ".vtconfig" / "concepts" / "loops.yaml").unlink()
    _, entries = overview.plan(sessions, framing=False)
    assert entries[1]["skip"].startswith("Session 2 — Loops: no overview — no concept map; run `coursekit analyze`")
    (sessions / "notes" / "loops.md").unlink()                       # declared, but nothing to analyze yet
    _, entries = overview.plan(sessions, framing=False)
    assert "no overview — no text yet to analyze" in entries[1]["skip"]


def test_analyze_names_a_chosen_unit_that_has_no_text_yet(sessions, capsys):
    (sessions / "notes" / "loops.md").unlink()
    assert cli.main(["analyze", str(sessions), "--unit", "loops", "--unit", "intro", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "[skip] loops: no text yet" in out and "[plan] Session 1 — Intro" in out


def test_propose_expectations_prints_each_units_own_rule(tmp_path, monkeypatch, capsys):
    from coursekit.ingest import propose_expectations as pe
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    monkeypatch.setattr(pe, "propose_expectations",
                        lambda path: ({"overrides": {"unit": {"intro": {"page:glossary": 1}}}}, []))
    _quiet(cli.main, ["propose", str(root), "--expectations", "--dry-run"])
    assert "unit intro: 1 page:glossary" in capsys.readouterr().out


def test_no_tool_the_model_is_offered_names_a_cadence():
    from coursekit.generate.assignment import build as assignment
    from coursekit.generate.page import tools as page_tools
    from coursekit.generate.quiz import tools as quiz_tools
    specs = page_tools.TOOL_SPECS + quiz_tools.TOOL_SPECS + assignment.TOOL_SPECS
    assert specs and "week" not in json.dumps(specs).lower()


def test_what_analyze_and_generate_print_for_a_session_course_never_says_week(sessions, capsys):
    for verb in ("analyze", "generate"):
        assert cli.main([verb, str(sessions), "--dry-run"]) == 0
    assert "week" not in capsys.readouterr().out.lower()
