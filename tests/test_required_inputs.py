"""CORE-1.5 — required inputs. A switched-on feature either produces its artifact or fails / records
why not — never a silent no-op. Each test below is one of the CORE-1 audit's silent cases."""

import types

import pytest

from coursekit import outcomes
from coursekit.discover import Unit
from coursekit.generate.page import concept_delivery as cd
from coursekit.generate.page import pedagogy as ped
from coursekit.generate.page.concept_map import (Concept, ConceptMap, concept_map_path, load_for_unit,
                                                 save_concept_map)
from coursekit.outcomes import CoursekitError
from coursekit.pipeline import ModelLoadError


def _unit(tmp_path, num="3") -> Unit:
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True, exist_ok=True)
    doc = root / "output" / f"week-{num}.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("Loops repeat a block of code.", encoding="utf-8")
    return Unit(transcript_path=doc, week_slug=f"week-{num}", output_dir=root / "quizzes" / f"week-{num}",
                course_slug="c", week_label=f"Week {num}", week_num=num, course_root=root)


def _map(u, *, eu="Loops scale effort."):
    save_concept_map(ConceptMap(week=u.week_num, enduring_understanding=eu, concepts=[Concept(name="For loops")]),
                     concept_map_path(u.course_root, u.week_num))


def _captured():
    return outcomes.capture(sink=lambda n: None)


class _Boom:
    """A provider whose every call fails with a content-level (not infrastructure) error."""
    def chat(self, **kw):
        raise RuntimeError("down")


# ------------------------------------------------------------------ A. absent vs broken concept map
def test_a_missing_map_is_none_but_a_broken_one_is_an_error(tmp_path):
    u = _unit(tmp_path)
    assert load_for_unit(u) is None
    path = concept_map_path(u.course_root, "3")
    path.parent.mkdir(parents=True)
    path.write_text("week: '3'\nconcepts: [{name: X, colour: red}]\n")
    with pytest.raises(CoursekitError) as e:
        load_for_unit(u)
    assert e.value.code == "config.invalid" and "week-3.yaml" in e.value.message


# ------------------------------------------------------------------ B. the EU path
class _Cfg:
    def __init__(self, **values):
        self.values = values

    def value(self, key, fallback=None):
        return self.values.get(key, fallback)


def _postprocess(u, monkeypatch, *, made=True):
    from coursekit.generate.quiz import bank, eu
    from coursekit.generate.quiz.generator import QuizGenerator
    calls = []
    monkeypatch.setattr(bank, "is_finalized", lambda: True)
    monkeypatch.setattr(bank, "finalize", lambda: calls.append("finalize"))
    monkeypatch.setattr(eu, "generate_eu_question", lambda *a, **k: calls.append("eu") or made)
    with _captured() as report:
        QuizGenerator().postprocess(u, None, "m", _Cfg(eu_question=True), "material")
    return calls, report


def test_eu_on_without_a_map_records_why(tmp_path, monkeypatch):
    calls, report = _postprocess(_unit(tmp_path), monkeypatch)
    assert calls == []
    (w,) = report.warnings
    assert w.code == "eu.skipped" and w.details["reason"] == "no_concept_map" and "analyze" in w.message


def test_eu_on_with_a_map_but_no_eu_records_why(tmp_path, monkeypatch):
    u = _unit(tmp_path)
    _map(u, eu="")
    _, report = _postprocess(u, monkeypatch)
    assert [w.details["reason"] for w in report.warnings] == ["no_enduring_understanding"]


def test_eu_on_with_an_eu_adds_the_question(tmp_path, monkeypatch):
    u = _unit(tmp_path)
    _map(u)
    calls, report = _postprocess(u, monkeypatch)
    assert calls == ["eu", "finalize"] and report.notices == []


def test_eu_pass_that_produces_nothing_is_recorded(tmp_path, monkeypatch):
    u = _unit(tmp_path)
    _map(u)
    calls, report = _postprocess(u, monkeypatch, made=False)
    assert calls == ["eu"] and [w.code for w in report.warnings] == ["eu.not_added"]


def test_a_targeted_quiz_knows_its_unit_but_keeps_its_own_shape(tmp_path, monkeypatch):
    # ASMT-19 layer 1: the unit number reaches the EU lookup; the unit's concept list stays out of the
    # single reading's brief.
    from coursekit import pipeline
    from coursekit.generate.quiz import targeted
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    src = root / "week-3" / "readings" / "Essay.md"
    src.parent.mkdir(parents=True)
    src.write_text("An essay about loops.", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(pipeline, "run_unit", lambda unit, p, m, gen, **k: seen.update(unit=unit, gen=gen))
    targeted.generate_targeted_quiz(src, None, "m")
    assert seen["unit"].week_num == "3" and seen["gen"].concept_shape is False
    _map(seen["unit"])
    from coursekit import courseconfig
    seen["gen"].build_messages(seen["unit"], "An essay about loops.",
                               courseconfig.load(root, config_name="quiz.yaml"))
    assert seen["gen"]._expected_groups is None                  # not one group per unit concept


# ------------------------------------------------------------------ D. critic failures
def test_a_failed_pedagogy_call_is_not_scored_not_zero():
    from coursekit.generate.page.pedagogy_fixtures import good_page
    with _captured() as report:
        r = ped.evaluate_page_pedagogy(good_page(), "material", _Boom(), "m")
    assert r.failed and "NOT SCORED" in ped.render_rubric(r)
    assert [w.code for w in report.warnings] == ["critic.call_failed"]


def test_a_failed_concept_call_is_not_scored_not_no_concepts():
    from coursekit.generate.page.concept_fixtures import good_page
    r = cd.evaluate_page_concepts(good_page(), "material", _Boom(), "m")
    assert r.failed and "NOT SCORED" in cd.render_concepts(r)


def test_a_model_that_wont_load_aborts_the_critics():
    from coursekit.generate.page.pedagogy_fixtures import good_page

    class _NotLoaded:
        def chat(self, **kw):
            raise RuntimeError("Failed to load model 'x': insufficient system resources")

        def check_fit(self, model):                # what a real provider reports for the message
            return None, ""
    with pytest.raises(ModelLoadError):
        ped.evaluate_page_pedagogy(good_page(), "material", _NotLoaded(), "m")


# ------------------------------------------------------------------ E. stale output, unreadable artifacts
def test_an_unreadable_artifact_is_counted_and_flagged_by_the_census(tmp_path):
    from coursekit import census
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    (root / "quizzes" / "week-3").mkdir(parents=True)
    (root / "quizzes" / "week-3" / "bank.json").write_text("{not json", encoding="utf-8")
    with _captured() as report:
        c = census.build_census(root)
    assert c.unreadable == ["quizzes/week-3/bank.json"]
    assert next(w for w in c.weeks if w.week == "3").quizzes == 1            # presence still counts
    assert "Unreadable artifacts" in census.render_report(c)
    assert [w.code for w in report.warnings] == ["census.unreadable_artifact"]


def test_a_failed_rerender_after_fix_is_recorded(tmp_path, monkeypatch):
    from coursekit.emit import html as html_emit
    from coursekit.generate.page import fix

    def _fail(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(html_emit, "write_html", _fail)
    with _captured() as report:
        fix._rerender(tmp_path, tmp_path, "week-3")
    (w,) = report.warnings
    assert w.code == "fix.html_stale" and "emit html" in w.message


# ------------------------------------------------------------------ F. housekeeping
def test_a_generator_without_an_output_tree_fails_loudly(tmp_path):
    from coursekit import pipeline
    u = _unit(tmp_path)
    with pytest.raises(AttributeError):          # once silently filed under quizzes/
        pipeline.run_course(u.course_root, dry_run=True, generator=types.SimpleNamespace(category="x"))


def test_an_unreadable_file_in_a_deep_proposal_is_recorded(tmp_path, monkeypatch):
    from coursekit.ingest import propose_model

    def _fail(p):
        raise ValueError("corrupt")
    monkeypatch.setattr(propose_model, "extract_text", _fail)
    with _captured() as report:
        assert propose_model._peek(tmp_path / "Broken.pdf") == ""
    assert [w.code for w in report.warnings] == ["propose.peek_failed"]
