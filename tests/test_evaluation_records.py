"""CORE-4.3: an evaluation is tied to the exact version it judged. Each critic `evaluate` runs adds its
result to the artifact's record with the hash of what it read, so a later edit shows the evaluation is
of an earlier version. Offline: one fake critic answers all six. See agent/core-4-design.md.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from coursekit import records
from coursekit.generate.page import concept_delivery, pedagogy
from coursekit.generate.page import evaluate as page_ev
from coursekit.generate.page import groundedness as page_gnd
from coursekit.generate.quiz import evaluate as quiz_ev
from coursekit.generate.quiz import groundedness as quiz_gnd
from coursekit.generate.quiz.generator import QuizGenerator
from coursekit.pipeline import run_unit
from coursekit.providers import OpenAICompatProvider
from tests.test_quiz_records import _Endpoint
from tests.test_records_everywhere import (
    _analyze,
    _course,
    _page,
    _quiet,
    _status,
    _unit,
)

# Each critic's prompt asks for its own reply format; the fake answers by the marker in the prompt.
REPLIES = {"VERDICT:": "VERDICT: FLAG\nCONCERN: not in the material\nFIX: ground it",
           "GROUNDING:": "GROUNDING: MODEL | not in the material",
           "CLAIMS:": "CLAIMS:\n- objects bundle values: GROUNDED | said\n- arrays are fast: TENSION | the lecture disagrees\n"
                      "- maps are hashed: MODEL | not in the material\n",
           "SCANNABILITY": "".join(f"{c}: 2 | fine\n" for c in pedagogy.CRITERIA),
           "CONCEPTS:": "CONCEPTS:\n- Object Literals: 3 | worked example\n- Arrays: 2 | explained\n"}


class Critic:
    def __init__(self, fail=False):
        self.fail = fail

    def chat(self, *, model, messages, temperature=None, max_tokens=None, seed=None):
        if self.fail:
            raise RuntimeError("model offline")
        system = messages[0]["content"]
        return next(reply for marker, reply in REPLIES.items() if marker in system)


# (critic name, the artifact it judges, the review it writes, how it runs)
CRITICS = {
    "quiz facticity": ("facticity", "quiz", "quizzes/quiz-review.md", quiz_ev.evaluate_course),
    "page facticity": ("facticity", "page", "pages/page-review.md", page_ev.evaluate_course_pages),
    "quiz groundedness": ("groundedness", "quiz", "quizzes/quiz-groundedness.md",
                          quiz_gnd.evaluate_course_groundedness),
    "page groundedness": ("groundedness", "page", "pages/page-groundedness.md",
                          page_gnd.evaluate_course_groundedness),
    "pedagogy": ("pedagogy", "page", "pages/page-pedagogy.md", pedagogy.evaluate_course_pedagogy),
    "concept delivery": ("concept_delivery", "page", "pages/page-concepts.md",
                         concept_delivery.evaluate_course_concepts),
}
RESULTS = {"quiz facticity": {"reviewed": 4, "flagged": 4, "errors": 0},
           "page facticity": {"reviewed": 1, "flagged": 1, "errors": 0},
           "quiz groundedness": {"coverage": 0.0, "model_knowledge": 4, "unchecked": 0},
           "page groundedness": {"coverage": 0.67, "in_tension": 1, "model_supplied": 1, "unchecked": 0},
           "pedagogy": {"total": 10, "out_of": 15},
           "concept delivery": {"average": 2.5, "concepts": 2}}


@pytest.fixture
def course(tmp_path):
    """A course with a quiz and a teaching page for week 7, each with a record that reads current."""
    root = _course(tmp_path)
    _analyze(root)
    quiz = _quiet(run_unit, _unit(root), OpenAICompatProvider(client=_Endpoint(), name="f"), "m", QuizGenerator())
    page = _page(root, generator="monolithic")
    assert _status(quiz.output_dir).state == _status(page.output_dir).state == "current"
    return SimpleNamespace(root=root, quiz=quiz.output_dir, page=page.output_dir)


def _evaluate(name, course, critic=None):
    return _quiet(CRITICS[name][3], course.root, weeks=["7"], provider=critic or Critic(), model="critic-m")


def _ir(course, kind):
    return (course.quiz / "bank.json") if kind == "quiz" else (course.page / "page.json")


@pytest.mark.parametrize("name", CRITICS)
def test_an_evaluation_is_recorded_with_the_version_it_judged(course, name):
    critic, kind, review, _ = CRITICS[name]
    ir = _ir(course, kind)
    before = ir.read_bytes()
    _evaluate(name, course)
    assert ir.read_bytes() == before                               # evaluating changes nothing it judged
    st = _status(ir.parent)
    assert st.state == "current" and not st.edited                 # a verdict on quality, not on staleness
    (e,) = st.evaluations
    assert (e["critic"], e["model"], e["review"], e["current"]) == (critic, "critic-m", review, True)
    assert e["judged"] == {ir.name: records.file_hash(ir)} and e["result"] == RESULTS[name]
    assert (course.root / review).is_file()


@pytest.mark.parametrize("name", CRITICS)
def test_a_later_edit_makes_the_evaluation_of_an_earlier_version(course, name):
    _, kind, _, _ = CRITICS[name]
    ir = _ir(course, kind)
    _evaluate(name, course)
    ir.write_text(ir.read_text(encoding="utf-8").replace("Objects", "Objects, edited"), encoding="utf-8")
    st = _status(ir.parent)
    assert st.edited and [e["current"] for e in st.evaluations] == [False]
    ir.write_bytes(ir.read_bytes())                                # unchanged bytes: still the version judged
    _evaluate(name, course)
    assert [e["current"] for e in _status(ir.parent).evaluations] == [True]


def test_each_critic_keeps_its_latest_evaluation_and_a_regenerate_starts_afresh(course):
    for name in ("page facticity", "pedagogy", "page facticity"):
        _evaluate(name, course)
    critics = [e["critic"] for e in _status(course.page).evaluations]
    assert critics == ["pedagogy", "facticity"]                   # facticity's second run replaced its first
    _page(course.root, generator="monolithic")
    assert _status(course.page).evaluations == []                 # a new page; nothing has judged it yet


def test_a_fix_leaves_the_evaluation_of_the_version_before_it_and_a_reorder_does_not(course):
    from types import SimpleNamespace as NS

    from coursekit.generate.quiz import bank, fix
    _evaluate("quiz facticity", course)
    groups = list(json.loads((course.quiz / "bank.json").read_text())["groups"])
    _quiet(bank.set_order, course.quiz, list(reversed(groups)))
    assert [e["current"] for e in _status(course.quiz).evaluations] == [True]   # the questions judged are unchanged

    def rewrite(session, f, *a, **k):                         # coursekit's fix rewrites the flagged question
        v = session.draft.bank.groups[f.group_id].variants[f.label]
        session.draft.put_variant(v.model_copy(update={"question_text": v.question_text + " (fixed)"}))
        return NS(replaced=True, now_passes=True)
    finding = NS(flagged=True, week="week-7", group_id=groups[0], label="A")
    fix_one, fix.fix_one = fix.fix_one, rewrite
    try:
        _quiet(fix.fix_course, course.root, provider=None, model="m", findings=[finding])
    finally:
        fix.fix_one = fix_one
    st = _status(course.quiz)
    assert not st.edited and [e["current"] for e in st.evaluations] == [False]


def test_an_artifact_made_before_records_gets_no_record_from_an_evaluation(course):
    (course.page / records.RECORD).unlink()
    _evaluate("pedagogy", course)
    assert not (course.page / records.RECORD).exists() and _status(course.page).state == "unknown"


@pytest.mark.parametrize("name", ["pedagogy", "concept delivery"])
def test_a_critic_call_that_failed_judged_nothing(course, name):
    _evaluate(name, course, Critic(fail=True))
    assert _status(course.page).evaluations == []


@pytest.mark.parametrize("name", ["quiz facticity", "page facticity"])
def test_a_facticity_read_that_failed_is_counted_as_an_error(course, name):
    _evaluate(name, course, Critic(fail=True))
    (e,) = _status(_ir(course, CRITICS[name][1]).parent).evaluations
    n = RESULTS[name]["reviewed"]
    assert e["result"] == {"reviewed": n, "flagged": 0, "errors": n}


def test_the_status_command_shows_each_evaluation_and_whether_it_is_of_this_version(course, capsys):
    _evaluate("page facticity", course)
    _evaluate("quiz facticity", course)
    bj = course.quiz / "bank.json"
    bj.write_text(bj.read_text(encoding="utf-8").replace("Objects", "Objects, edited"), encoding="utf-8")
    argv, sys.argv = sys.argv, ["records", str(course.root)]
    try:
        _quiet(records.main)
    finally:
        sys.argv = argv
    out = capsys.readouterr().out
    page = out[out.index("pages/week-7 "):]
    quiz = out[out.index("quizzes/week-7 "):]
    assert "evaluated: facticity" in page and "(reviewed 1, flagged 1, errors 0)\n" in page
    (line,) = [ln for ln in quiz.splitlines() if "evaluated:" in ln]
    assert "facticity" in line and line.endswith("— of an earlier version")


@pytest.mark.parametrize("name", CRITICS)
def test_an_evaluation_is_recorded_only_after_its_review_is_written(course, name, monkeypatch):
    from coursekit import atomic
    order, write = [], atomic.write
    monkeypatch.setattr(atomic, "write", lambda p, d: order.append(Path(p).name) or write(p, d))
    _evaluate(name, course)
    review = Path(CRITICS[name][2]).name
    assert order.index(review) < order.index(records.RECORD)       # never a record naming a missing review


class Passing(Critic):
    def chat(self, **kw):
        return "VERDICT: PASS\nCONCERN:\nFIX:"


@pytest.mark.parametrize("critic,flagged", [(Critic(), True), (Passing(), False)])
def test_a_single_document_quizs_own_review_is_recorded(course, monkeypatch, capsys, critic, flagged):
    from coursekit import cli
    from coursekit.generate.quiz import targeted
    reading = course.root / "week-7" / "readings" / "objects.md"
    reading.parent.mkdir(parents=True)
    reading.write_text("Objects group named values.", encoding="utf-8")
    res = _quiet(targeted.generate_targeted_quiz, reading, OpenAICompatProvider(client=_Endpoint(), name="f"), "m")
    monkeypatch.setenv("MODEL_NAME", "critic-m")
    _quiet(cli._review_targeted_quiz, res, critic)              # `generate --source … --review`
    st = _status(res.output_dir)
    (e,) = st.evaluations
    assert st.state == "current" and e["current"] and e["model"] == "critic-m"
    n = e["result"]["reviewed"]
    assert n and e["result"] == {"reviewed": n, "flagged": n if flagged else 0, "errors": 0}
    assert e.get("review") == (f"quizzes/{res.output_dir.name}/quiz-review.md" if flagged else None)


def _fix_without_a_review(course, kind, critic, monkeypatch):
    """`fix` with no review to work from: it runs the critic itself, then rewrites what it flagged."""
    from types import SimpleNamespace as NS

    from coursekit.generate.page import fix as page_fix
    from coursekit.generate.quiz import fix as quiz_fix

    def rewrite_question(session, f, *a, **k):
        v = session.draft.bank.groups[f.group_id].variants[f.label]
        session.draft.put_variant(v.model_copy(update={"question_text": v.question_text + " (fixed)"}))
        return NS(replaced=True, now_passes=True)

    def rewrite_block(session, f, *a, **k):
        b = session.draft.page.blocks[f.group_id]
        session.draft.put_block(b.model_copy(update={"text": "Objects, fixed."}))
        return NS(replaced=True, now_passes=True)

    if kind == "quiz":
        monkeypatch.setattr(quiz_fix, "fix_one", rewrite_question)
        _quiet(quiz_fix.fix_course, course.root, weeks=["7"], provider=critic, model="critic-m")
    else:
        monkeypatch.setattr(page_fix, "fix_one_block", rewrite_block)
        _quiet(page_fix.fix_course_pages, course.root, weeks=["7"], provider=critic, model="critic-m")


@pytest.mark.parametrize("kind", ["quiz", "page"])
def test_fixs_own_check_is_recorded_as_of_the_version_before_the_fix(course, monkeypatch, kind):
    ir = _ir(course, kind)
    before = ir.read_bytes()
    _fix_without_a_review(course, kind, Critic(), monkeypatch)    # flags everything, so fix rewrites
    assert ir.read_bytes() != before
    (e,) = _status(ir.parent).evaluations
    assert e["critic"] == "facticity" and e["result"]["flagged"] == e["result"]["reviewed"] > 0
    assert e["judged"] == {ir.name: records.hash_bytes(before)} and not e["current"] and "review" not in e


@pytest.mark.parametrize("kind", ["quiz", "page"])
def test_fixs_own_check_that_finds_nothing_is_a_current_evaluation(course, monkeypatch, kind):
    ir = _ir(course, kind)
    before = ir.read_bytes()
    _fix_without_a_review(course, kind, Passing(), monkeypatch)
    assert ir.read_bytes() == before                              # nothing flagged, nothing fixed
    (e,) = _status(ir.parent).evaluations
    assert e["current"] and e["result"]["flagged"] == 0


def test_a_page_fixed_by_coursekit_is_not_edited_by_hand(course, monkeypatch):
    _fix_without_a_review(course, "page", Critic(), monkeypatch)
    st = _status(course.page)
    assert st.state == "current" and not st.edited
    assert [s["step"] for s in records.load(course.page)["steps"]] == ["generate", "fix"]   # no "edited"


def test_a_hand_edit_before_a_page_fix_is_remembered(course, monkeypatch):
    pj = course.page / "page.json"
    pj.write_text(pj.read_text(encoding="utf-8").replace("Objects", "Objects, by hand"), encoding="utf-8")
    _fix_without_a_review(course, "page", Critic(), monkeypatch)
    assert [s["step"] for s in records.load(course.page)["steps"]][-2:] == ["edited", "fix"]
    assert not _status(course.page).edited


def test_fixing_a_page_made_before_records_leaves_it_unknown(course, monkeypatch):
    (course.page / records.RECORD).unlink()
    _fix_without_a_review(course, "page", Critic(), monkeypatch)
    assert not (course.page / records.RECORD).exists() and _status(course.page).state == "unknown"


def test_the_decompose_prototypes_fix_records_a_fix_step(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS

    from coursekit import cli
    from coursekit.generate.page import decompose
    from coursekit.generate.page import fix as page_fix
    from tests.test_records_everywhere import Model

    class Flagging(Model):                                   # builds the page, then flags every section
        def chat(self, *, model, messages, **kw):
            if "VERDICT:" in messages[0]["content"]:
                return REPLIES["VERDICT:"]
            return super().chat(model=model, messages=messages, **kw)

    def rewrite_block(session, f, *a, **k):
        b = session.draft.page.blocks[f.group_id]
        session.draft.put_block(b.model_copy(update={"text": "Fixed."}))
        return NS(replaced=True, now_passes=True)

    root = _course(tmp_path)
    _analyze(root)
    monkeypatch.setattr(cli, "_build_provider", Flagging)
    monkeypatch.setattr(page_fix, "fix_one_block", rewrite_block)
    monkeypatch.setenv("MODEL_NAME", "m")
    monkeypatch.setattr(sys, "argv", ["decompose", str(root), "--week", "7", "--fix"])
    assert _quiet(decompose.main) == 0
    page = root / "pages" / "week-7"
    st = _status(page)
    assert [s["step"] for s in records.load(page)["steps"]][-1] == "fix" and not st.edited
