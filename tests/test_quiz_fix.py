"""Targeted quiz regeneration — the fix loop.

Offline: a fake tool-calling provider scripts the corrected tool call and the verify verdict.
"""

import json

import pytest

from coursekit.generate.quiz import bank, tools
from coursekit.generate.quiz import fix as qfix
from coursekit.generate.quiz import evaluate as ev
from coursekit.providers.base import Reply, ToolCall


@pytest.fixture
def fresh():
    bank.reset()
    tools.reset_state()
    yield
    bank.reset()
    tools.reset_state()


def _flawed_group():
    """A group with one MC variant whose marked answer is wrong (index 1; correct is index 0)."""
    bank.create_group("c1", "key vs keyCode", "multiple_choice")
    tools.add_multiple_choice_variant("c1", "A", "What does `key` hold?", "meaning of key",
                                      ["a string character", "a numeric code"], 1)


class FixProvider:
    """Scripts the corrected tool call, and a verify verdict that PASSes once the fix marker appears."""
    def __init__(self, tool_args, *, tool="add_multiple_choice_variant"):
        self.tool_args, self.tool = tool_args, tool

    def chat_with_tools(self, *, model, messages, tools, temperature=None, max_tokens=None):
        return Reply(finish_reason="tool_calls",
                     tool_calls=[ToolCall("1", self.tool, json.dumps(self.tool_args))])

    def chat(self, *, model, messages, temperature=None, **kw):
        joined = " ".join(m.get("content", "") for m in messages if isinstance(m.get("content"), str))
        return "VERDICT: PASS" if "FIXED" in joined else "VERDICT: FLAG\nCONCERN: wrong key"

    def append_assistant(self, messages, reply):
        messages.append({"role": "assistant", "content": reply.content or ""})

    def append_tool_results(self, messages, results):
        for _id, content in results:
            messages.append({"role": "tool", "content": content})

    def append_user(self, messages, text):
        messages.append({"role": "user", "content": text})


def _finding():
    return ev.Finding(week="week-3", group_id="c1", label="A", stem="What does `key` hold?",
                      verdict="FLAG", concern="marked answer is wrong")


# ------------------------------------------------------------- the tool surface

def test_fix_tool_specs_are_only_add_tools():
    names = {s["name"] for s in qfix.FIX_TOOL_SPECS}
    assert names == {"add_multiple_choice_variant", "add_multiple_answer_variant",
                     "add_true_false_variant", "add_short_answer_variant",
                     "add_numerical_variant", "add_matching_variant"}
    assert "finalize_bank" not in names and "create_checklist" not in names


# ------------------------------------------------------------- fix_one

def test_fix_one_replaces_and_verifies(fresh):
    _flawed_group()
    corrected = {"group_id": "c1", "variant_label": "A", "question_text": "What does `key` hold? FIXED",
                 "variant_summary": "key is the character", "options": ["a string character", "a numeric code"],
                 "correct_index": 0}
    fp = FixProvider(corrected)
    out = qfix.fix_one(_finding(), "material", fp, "m", critic="CRITIC")
    assert out.replaced is True and out.now_passes is True
    # the bank now marks the correct option
    assert bank.get().groups["c1"].variants["A"].correct_index == 0


def test_fix_one_gives_up_when_the_tool_keeps_erroring(fresh):
    _flawed_group()
    # wrong group_id -> put_variant returns ERROR every turn -> never replaced
    fp = FixProvider({"group_id": "nope", "variant_label": "A", "question_text": "x FIXED",
                      "variant_summary": "s", "options": ["a", "b"], "correct_index": 0})
    out = qfix.fix_one(_finding(), "material", fp, "m", critic="CRITIC", max_turns=2)
    assert out.replaced is False and out.now_passes is None
    assert bank.get().groups["c1"].variants["A"].correct_index == 1   # untouched


# ------------------------------------------------------------- fix_course (integration)

def test_fix_course_updates_bank_on_disk(tmp_path, fresh):
    pytest.importorskip("yaml")
    (tmp_path / ".vtconfig").mkdir()
    (tmp_path / "week-3.md").write_text("`key` is a string character; `keyCode` is a numeric code.")
    outd = tmp_path / "quizzes" / "week-3"
    outd.mkdir(parents=True)
    b = bank.Bank(run_id="c-week-3", title="t")
    b.groups["c1"] = bank.Group(group_id="c1", concept_title="key vs keyCode",
                                question_type="multiple_choice",
                                variants={"A": bank.MCVariant(
                                    group_id="c1", label="A", question_text="What does `key` hold?",
                                    variant_summary="meaning of key",
                                    options=["a string character", "a numeric code"], correct_index=1)})
    (outd / "bank.json").write_text(b.model_dump_json())

    corrected = {"group_id": "c1", "variant_label": "A", "question_text": "What does `key` hold? FIXED",
                 "variant_summary": "key is the character", "options": ["a string character", "a numeric code"],
                 "correct_index": 0}
    outcomes = qfix.fix_course(tmp_path / "week-3.md", provider=FixProvider(corrected), model="m")

    assert len(outcomes) == 1 and outcomes[0].replaced and outcomes[0].now_passes
    saved = bank.Bank.model_validate_json((outd / "bank.json").read_text())
    assert saved.groups["c1"].variants["A"].correct_index == 0        # fix persisted
    assert (outd / "bank.gift").exists()                              # re-emitted


def test_parse_review_round_trips_render_review():
    from coursekit.generate.quiz.evaluate import render_review, parse_review, Finding
    fs = [Finding("week-7", "c5", "B", "the stem", "FLAG", "circular question"),
          Finding("week-9", "realtime-code", "code", "s", "FLAG", "undeclared variable")]  # page-style ids
    parsed = parse_review(render_review(fs))
    got = {(f.week, f.group_id, f.label, f.verdict, f.concern) for f in parsed}
    assert ("week-7", "c5", "B", "FLAG", "circular question") in got
    assert ("week-9", "realtime-code", "code", "FLAG", "undeclared variable") in got   # rsplit on last /


def test_fix_course_from_review_uses_given_findings(tmp_path, fresh):
    pytest.importorskip("yaml")
    (tmp_path / ".vtconfig").mkdir()
    (tmp_path / "week-3.md").write_text("`key` is a string character; `keyCode` is a numeric code.")
    outd = tmp_path / "quizzes" / "week-3"
    outd.mkdir(parents=True)
    b = bank.Bank(run_id="c-week-3", title="t")
    b.groups["c1"] = bank.Group(group_id="c1", concept_title="key vs keyCode",
                                question_type="multiple_choice",
                                variants={"A": bank.MCVariant(
                                    group_id="c1", label="A", question_text="What does `key` hold?",
                                    variant_summary="meaning of key",
                                    options=["a string character", "a numeric code"], correct_index=1)})
    (outd / "bank.json").write_text(b.model_dump_json())

    corrected = {"group_id": "c1", "variant_label": "A", "question_text": "What does `key` hold? FIXED",
                 "variant_summary": "key is the character", "options": ["a string character", "a numeric code"],
                 "correct_index": 0}
    findings = [ev.Finding("week-3", "c1", "A", "", "FLAG", "wrong key")]
    # findings supplied → no re-audit; fixes exactly this one
    outcomes = qfix.fix_course(tmp_path / "week-3.md", provider=FixProvider(corrected), model="m",
                               findings=findings)
    assert len(outcomes) == 1 and outcomes[0].replaced and outcomes[0].now_passes
    saved = bank.Bank.model_validate_json((outd / "bank.json").read_text())
    assert saved.groups["c1"].variants["A"].correct_index == 0


def test_fix_verb_routes():
    from coursekit import cli
    args = cli.build_parser().parse_args(["fix", "/tmp/c", "--week", "3", "--max-turns", "2"])
    assert args.func is cli._cmd_fix
    assert args.path == "/tmp/c" and args.week == ["3"] and args.max_turns == 2


def test_render_outcomes_summarizes():
    outs = [qfix.FixOutcome("week-3", "c1", "A", "x", True, True),
            qfix.FixOutcome("week-4", "c2", "C", "y", True, False),
            qfix.FixOutcome("week-5", "c3", "B", "z", False, None)]
    text = qfix.render_outcomes(outs)
    assert "Fixed 2 of 3" in text and "1 now pass" in text
    assert "fixed ✓" in text and "still flagged" in text and "could not fix" in text


def test_render_outcomes_uses_the_given_noun():
    outs = [qfix.FixOutcome("week-8", "g1", "A", "c", True, True)]
    assert "flagged question(s)" in qfix.render_outcomes(outs)              # default (quizzes)
    assert "flagged section(s)" in qfix.render_outcomes(outs, noun="section")   # pages


def test_abort_if_model_error_aborts_on_infra_but_not_on_content():
    from coursekit.pipeline import ModelLoadError

    class _P:
        def check_fit(self, model):
            return (False, "model ~14 GB but budget ~9 GB")

    # a model-load / connection failure aborts the whole run — NOT a per-item "could not fix"
    with pytest.raises(ModelLoadError):
        qfix._abort_if_model_error(_P(), "m",
                                   RuntimeError("Failed to load model: insufficient system resources"))
    # a content-level exception does not abort; the caller breaks just that one item
    assert qfix._abort_if_model_error(_P(), "m", ValueError("some content issue")) is None
