"""CORE-4.4: a record is shown where people look. The census gives each artifact's status, `emit` warns about
a stale artifact (and packages it anyway), and `generate` refuses to overwrite one edited by hand unless
`--force`. Offline. See agent/core-4-design.md.
"""

import json

import pytest

from coursekit import cli, outcomes, records
from coursekit.census import build_census, render_report
from coursekit.course import Course
from coursekit.emit import qti
from coursekit.generate.quiz import targeted
from coursekit.generate.quiz.generator import QuizGenerator
from coursekit.outcomes import CoursekitError
from coursekit.pipeline import run_course, run_unit
from coursekit.providers import OpenAICompatProvider
from tests.test_quiz_records import _Endpoint
from tests.test_records_everywhere import Model, _analyze, _course, _page, _quiet, _status, _unit


def _provider():
    endpoint = _Endpoint()
    return OpenAICompatProvider(client=endpoint, name="f"), endpoint


@pytest.fixture
def quiz(tmp_path):
    """A course whose week 7 quiz was made with a record, and reads current."""
    root = _course(tmp_path)
    _analyze(root)
    res = _quiet(run_unit, _unit(root), _provider()[0], "m", QuizGenerator())
    assert _status(res.output_dir).state == "current"
    return res.output_dir


def _edit(path):
    path.write_text(path.read_text(encoding="utf-8").replace("{", "{ ", 1), encoding="utf-8")


def _regenerate(quiz, **kw):
    provider, endpoint = _provider()
    _quiet(run_course, quiz.parents[1] / "output" / "week 7", generator=QuizGenerator(), provider=provider,
           model="m", **kw)
    return endpoint


# ------------------------------------------------------------------ generate refuses to overwrite an edit

def test_generate_refuses_to_overwrite_a_quiz_edited_by_hand(quiz):
    _edit(quiz / "bank.json")
    edited = (quiz / "bank.json").read_text(encoding="utf-8")
    provider, endpoint = _provider()
    with pytest.raises(CoursekitError) as e:
        _quiet(run_course, quiz.parents[1] / "output" / "week 7", generator=QuizGenerator(), provider=provider,
               model="m")
    assert e.value.code == "artifact.edited" and e.value.details == {"paths": [str(quiz)]}
    assert "--force" in e.value.message
    assert endpoint.sent == []                                      # refused before the model was asked
    assert (quiz / "bank.json").read_text(encoding="utf-8") == edited


def test_force_regenerates_an_edited_quiz(quiz):
    _edit(quiz / "bank.json")
    assert _regenerate(quiz, force=True).sent
    assert _status(quiz).state == "current" and not _status(quiz).edited


@pytest.mark.parametrize("change", ["nothing", "deleted", "no record"])
def test_generate_regenerates_what_isnt_a_hand_edit(quiz, change):
    if change == "deleted":
        (quiz / "quiz.json").unlink()                               # nothing there to lose
    if change == "no record":
        _edit(quiz / "bank.json")
        (quiz / records.RECORD).unlink()                            # made before records: can't tell
    assert _regenerate(quiz).sent


def test_the_refusal_names_every_edited_unit_at_once(tmp_path):
    root = _course(tmp_path)
    for n in ("7", "8"):
        _analyze(root, n)
        _quiet(run_unit, _unit(root, n), _provider()[0], "m", QuizGenerator())
        _edit(root / "quizzes" / f"week-{n}" / "bank.json")
    with pytest.raises(CoursekitError) as e:
        _quiet(run_course, root / "output", generator=QuizGenerator(), provider=_provider()[0], model="m")
    assert e.value.details["paths"] == [str(root / "quizzes" / f"week-{n}") for n in ("7", "8")]


class _Fits(Model):
    def check_fit(self, model):
        return None, ""


@pytest.mark.parametrize("function", ["overview", "glossary"])
def test_generate_looks_for_an_edited_page_where_its_function_writes_it(tmp_path, monkeypatch, capsys, function):
    root = _course(tmp_path)
    _analyze(root)
    out = _page(root, function=function).output_dir
    _edit(out / "page.json")
    monkeypatch.setenv("MODEL_NAME", "m")
    monkeypatch.setattr(cli, "_build_provider", _Fits)
    args = ["generate", str(root / "output" / "week 7"), "--pages", "--function", function, "--no-review"]
    assert cli.main(args) != 0
    assert "edited by hand" in capsys.readouterr().err
    assert cli.main(args + ["--force"]) == 0 and not _status(out).edited


def test_generate_refuses_to_overwrite_an_edited_assignment(tmp_path, monkeypatch, capsys):
    from coursekit.generate.assignment import build as assignment
    root = _course(tmp_path)
    _analyze(root)
    unit = _unit(root, subdir="assignments")
    _quiet(assignment.build_assignment, unit, Model(), "m", unit.output_dir)
    _edit(unit.output_dir / "assignment.json")
    monkeypatch.setenv("MODEL_NAME", "m")
    monkeypatch.setattr(cli, "_build_provider", lambda: pytest.fail("the model was reached"))
    assert cli.main(["generate", str(root / "output" / "week 7"), "--assignments"]) != 0
    assert "edited by hand" in capsys.readouterr().err


def test_a_document_quiz_refuses_to_overwrite_an_edit(tmp_path):
    root = _course(tmp_path)
    doc = root / "week 7 reading.md"
    doc.write_text("Objects bundle values.\n" * 20, encoding="utf-8")
    res = _quiet(targeted.generate_targeted_quiz, doc, _provider()[0], "m")
    assert _status(res.output_dir).state == "current"
    _edit(res.output_dir / "bank.json")
    provider, endpoint = _provider()
    with pytest.raises(CoursekitError, match="edited by hand"):
        _quiet(targeted.generate_targeted_quiz, doc, provider, "m")
    assert endpoint.sent == []
    assert _quiet(targeted.generate_targeted_quiz, doc, provider, "m", force=True).finalized


# ------------------------------------------------------------------ the census shows each artifact's status

def _census(root):
    return _quiet(build_census, root)


def test_an_artifact_made_before_records_reads_unknown_never_current(quiz):
    (quiz / records.RECORD).unlink()
    census = _census(quiz.parents[1])
    assert {(a.kind, a.state) for a in census.artifacts} == {("quiz", "unknown"), ("concept_map", "current")}
    report = render_report(census)
    assert "2 artifacts: 1 current · 1 unknown" in report and "1 were made before records" in report


def test_the_census_lists_what_is_stale_or_edited_and_why(quiz):
    root = quiz.parents[1]
    assert {a.state for a in _census(root).artifacts} == {"current"}
    assert "\n- `" not in render_report(_census(root))                  # nothing to look at
    (root / ".vtconfig" / "domain.md").write_text("Processing.", encoding="utf-8")
    _edit(quiz / "bank.json")
    (a,) = [a for a in _census(root).artifacts if a.kind == "quiz"]
    assert (a.path, a.unit, a.state, a.edited) == ("quizzes/week-7/bank.json", "7", "stale", True)
    assert "- `quizzes/week-7/bank.json` — stale + edited: generate: .vtconfig/domain.md changed" in render_report(
        _census(root))


def test_an_overviews_record_is_not_an_overview(tmp_path):
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    (root / "overview").mkdir()
    (root / "overview" / "course.json").write_text("{}", encoding="utf-8")
    (root / "overview" / "course.record.json").write_text("{}", encoding="utf-8")
    course = _quiet(Course.load, root)
    assert [(a.slug, a.record[1]) for a in course.artifacts] == [("course", "course.record.json")]


# ------------------------------------------------------------------ emit warns about a stale artifact

def _emit(root):
    with outcomes.capture(sink=lambda n: None) as report:
        results = qti.reemit(root)
    return [n for n in report.warnings if n.code == "artifact.stale"], results


def test_emit_warns_about_a_stale_quiz_and_packages_it_anyway(quiz):
    root = quiz.parents[1]
    (root / ".vtconfig" / "domain.md").write_text("Processing.", encoding="utf-8")
    (warning,), results = _emit(root)
    assert "week-7: stale — generate: .vtconfig/domain.md changed" in warning.message
    assert warning.details == {"path": str(quiz / "bank.json")}
    assert [imscc is not None for _, imscc, _ in results] == [True]


@pytest.mark.parametrize("change", ["nothing", "edited", "no record"])
def test_emit_says_nothing_about_a_current_edited_or_unknown_quiz(quiz, change):
    if change != "nothing":
        _edit(quiz / "bank.json")
    if change == "no record":
        (quiz / records.RECORD).unlink()
    warnings, results = _emit(quiz.parents[1])
    assert warnings == [] and [imscc is not None for _, imscc, _ in results] == [True]
