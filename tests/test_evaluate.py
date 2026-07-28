"""The cold-read quiz evaluator — offline, with a fake critic (no model)."""

from coursekit.generate.quiz import bank as bankmod
from coursekit.generate.quiz import evaluate as ev


class _FakeCritic:
    """A stand-in provider: FLAGs any question containing `flag_marker`, else PASS."""
    def __init__(self, flag_marker=None):
        self.flag_marker = flag_marker
        self.calls = 0

    def chat(self, *, model, messages, temperature=None, max_tokens=None):
        self.calls += 1
        question = messages[1]["content"]
        if self.flag_marker and self.flag_marker in question:
            return "VERDICT: FLAG\nCONCERN: not in the material\nFIX: ground it in the lecture"
        return "VERDICT: PASS\nCONCERN:\nFIX:"


def _bank():
    bankmod.reset()
    bankmod.init("run", None, title="Week 3", source="week-3.md")
    bankmod.create_group("c1", "Loops", "multiple_choice")
    for i, lbl in enumerate("ABCD"):
        bankmod.put_variant(bankmod.MCVariant(
            group_id="c1", label=lbl, variant_summary=f"angle {lbl}",
            question_text=f"Question {lbl}: what does a loop do {'OUTOFSCOPE' if lbl == 'B' else 'here'}?",
            options=["one", "two", "three", "four"], correct_index=i))
    return bankmod.get()


def test_parse_verdict_reads_pass_flag_and_fields():
    assert ev._parse_verdict("VERDICT: PASS\nCONCERN:\nFIX:")[0] == "PASS"
    v, c, f = ev._parse_verdict("VERDICT: FLAG\nCONCERN: out of scope\nFIX: rewrite it")
    assert (v, c, f) == ("FLAG", "out of scope", "rewrite it")
    assert ev._parse_verdict("unparseable reply")[0] == "ERROR"   # a flaky reply -> ERROR, not crash


def test_format_question_shows_the_marked_answer():
    b = _bank()
    text = ev._format_question(b.groups["c1"].variants["A"])
    assert "multiple_choice" in text and "* one" in text   # option 0 marked correct for label A


def test_evaluate_bank_cold_reads_each_variant_and_flags_the_match():
    findings = ev.evaluate_bank(_bank(), "a transcript about loops", _FakeCritic("OUTOFSCOPE"), "m")
    assert len(findings) == 4                              # one fresh read per variant
    flagged = [f for f in findings if f.flagged]
    assert len(flagged) == 1 and flagged[0].label == "B"
    assert "not in the material" in flagged[0].concern


def test_evaluate_bank_survives_a_flaky_critic():
    class _Boom:
        def chat(self, **kw):
            raise RuntimeError("model offline")
    findings = ev.evaluate_bank(_bank(), "t", _Boom(), "m")
    assert all(f.verdict == "ERROR" for f in findings)    # reported, whole review not aborted


def test_render_review_lists_only_flagged():
    review = ev.render_review(ev.evaluate_bank(_bank(), "t", _FakeCritic("OUTOFSCOPE"), "m"))
    assert "1 of 4 question(s) flagged" in review
    assert "c1/B" in review and "not in the material" in review
    assert "Question A" not in review                     # passing questions are omitted


def test_render_review_all_clear():
    review = ev.render_review(ev.evaluate_bank(_bank(), "t", _FakeCritic(), "m"))   # nothing flagged
    assert "0 of 4" in review and "Nothing to review" in review


def test_evaluate_course_writes_a_review(tmp_path):
    course = tmp_path / "course"
    (course / "output").mkdir(parents=True)
    (course / "output" / "week-3.md").write_text("loops and iteration", encoding="utf-8")
    qd = course / "quizzes" / "week-3"
    qd.mkdir(parents=True)
    (qd / "bank.json").write_text(_bank().model_dump_json(), encoding="utf-8")

    findings, review = ev.evaluate_course(course, provider=_FakeCritic("OUTOFSCOPE"), model="m")
    assert len(findings) == 4 and review is not None and review.exists()
    assert "flagged" in review.read_text()
