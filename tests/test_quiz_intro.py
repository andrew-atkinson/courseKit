"""SHIP-10: the quiz introduction — written once in the instructor's voice, kept on the bank, never
pointing the student at a file, and optional (a failure leaves the quiz exactly as it was)."""

import json
from types import SimpleNamespace as NS

from coursekit import outcomes
from coursekit.discover import find_units
from coursekit.generate.quiz import bank, intro
from coursekit.generate.quiz.generator import QuizGenerator
from coursekit.pipeline import run_unit
from coursekit.providers import OpenAICompatProvider

INTRO = "So this week we've kind of moved from loose variables to objects, and that's the whole galaxy."

# One MC group with its four variants, then finalize — the main loop's part of a run.
SCRIPT = [
    [("create_question_group", {"group_id": "c1", "concept_title": "Object Literals",
                                "question_type": "multiple_choice"})]
    + [("add_multiple_choice_variant",
        {"group_id": "c1", "variant_label": lbl, "question_text": f"Which literal is valid ({lbl})?",
         "variant_summary": f"angle {lbl}", "options": ["a", "b", "c", "d"], "correct_index": 0})
       for lbl in "ABCD"],
    [("finalize_bank", {})],
]


class _Endpoint:
    """An OpenAI-shaped endpoint: tool turns follow the script; a plain completion (no tools) is the
    intro request, answered with `reply` and recorded so a test can read what the model was shown."""

    def __init__(self, reply=INTRO, script=SCRIPT):
        self.reply, self.script, self.turn, self.intro_requests = reply, script, 0, []
        self.chat = self.completions = self

    def create(self, **kw):
        if "tools" not in kw:
            self.intro_requests.append(kw["messages"])
            if isinstance(self.reply, Exception):
                raise self.reply
            return NS(choices=[NS(message=NS(content=self.reply, tool_calls=None), finish_reason="stop")])
        calls = [NS(id=f"t{self.turn}-{i}", type="function", function=NS(name=n, arguments=json.dumps(a)))
                 for i, (n, a) in enumerate(self.script[min(self.turn, len(self.script) - 1)])]
        self.turn += 1
        return NS(choices=[NS(message=NS(content=None, tool_calls=calls), finish_reason="tool_calls")])


def _unit(tmp_path, voice="Use a collaborative stance: say we and let's."):
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    (root / ".vtconfig" / "voice.md").write_text(voice, encoding="utf-8")
    f = root / "output" / "week-7.md"
    f.parent.mkdir(parents=True)
    f.write_text("a transcript about objects", encoding="utf-8")
    return find_units(f)[0]


def _run(unit, endpoint):
    with outcomes.capture(sink=lambda n: None) as report:
        result = run_unit(unit, OpenAICompatProvider(client=endpoint, name="fake"), "m", QuizGenerator())
    return result, bank.Bank.model_validate_json((unit.output_dir / "bank.json").read_text()), report


def test_a_finished_quiz_gets_an_intro_in_the_instructors_voice(tmp_path):
    unit, endpoint = _unit(tmp_path), _Endpoint()
    result, saved, _ = _run(unit, endpoint)

    assert result.finalized and saved.intro == INTRO
    (messages,) = endpoint.intro_requests
    system, user = messages[0]["content"], messages[1]["content"]
    assert "say we and let's" in system                     # the course's voice.md reaches the call
    assert "Object Literals" in user                        # the topics, from the bank
    assert "week-7" not in system + user                    # never a file name the student can't see


def test_a_failed_or_unusable_reply_leaves_the_quiz_without_an_intro(tmp_path):
    for i, (reply, code) in enumerate([(RuntimeError("down"), "quiz.intro_failed"),
                                       ("Read week-7.md first.", "quiz.intro_rejected"),
                                       ("See https://example.org", "quiz.intro_rejected"),
                                       ("", "quiz.intro_rejected")]):
        result, saved, report = _run(_unit(tmp_path / str(i)), _Endpoint(reply=reply))
        assert result.finalized and saved.intro is None and len(saved.groups) == 1
        assert [w.code for w in report.warnings] == [code]


def test_the_model_is_told_about_an_open_question_but_given_no_counts():
    b = bank.Bank(run_id="r", title="Week 7: Objects", groups={
        "g1": bank.Group(group_id="g1", concept_title="Arrays", question_type="multiple_choice"),
        "enduring_understanding": bank.Group(group_id="enduring_understanding",
                                             concept_title="Enduring Understanding",
                                             question_type="open_response")})
    facts = intro.unit_facts(b, "Structure lets systems scale.")
    assert facts == ("Unit: Week 7: Objects\nTopics: Arrays\nBig idea: Structure lets systems scale.\n"
                     "The quiz: short questions, then one open question answered in writing")


def test_the_intro_script_adds_an_intro_to_an_existing_quiz_in_place(tmp_path, monkeypatch):
    import coursekit.cli as cli
    unit = _unit(tmp_path)
    _run(unit, _Endpoint(reply=""))                          # an existing quiz, made without an intro
    before = json.loads((unit.output_dir / "quiz.json").read_text())
    monkeypatch.setattr(cli, "_build_provider", lambda: OpenAICompatProvider(client=_Endpoint(), name="fake"))
    monkeypatch.setenv("MODEL_NAME", "m")
    monkeypatch.setattr("sys.argv", ["intro", str(unit.course_root), "--week", "7"])

    assert intro.main() == 0
    saved = bank.Bank.model_validate_json((unit.output_dir / "bank.json").read_text())
    assert saved.intro == INTRO and set(saved.groups) == {"c1"}
    assert json.loads((unit.output_dir / "quiz.json").read_text()) == before   # the draw is unchanged
