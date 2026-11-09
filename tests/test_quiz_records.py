"""CORE-4.1: a quiz's record says what it was made from, and a check says whether it still matches.

The verdict comes from the brief (exactly what the model was shown), so it is precise both ways: changing
the unit's text makes the quiz stale, while changing another unit's entry in `context.yaml` does not. See
agent/core-4-design.md.
"""

import json
from pathlib import Path
from types import SimpleNamespace as NS

from coursekit import outcomes, records
from coursekit.discover import find_units
from coursekit.generate.page.concept_map import Concept, ConceptMap, concept_map_path, save_concept_map
from coursekit.generate.quiz import bank, fix, record
from coursekit.generate.quiz.generator import QuizGenerator
from coursekit.pipeline import run_unit
from coursekit.providers import OpenAICompatProvider

EU = "enduring_understanding"
INTRO = "So let's see how objects and arrays are landing for you."
MAIN = [[("create_question_group", {"group_id": "c1", "concept_title": "Object Literals",
                                    "question_type": "multiple_choice"})]
        + [("add_multiple_choice_variant",
            {"group_id": "c1", "variant_label": lbl, "question_text": f"Which literal is valid ({lbl})?",
             "variant_summary": f"angle {lbl}", "options": ["a", "b", "c", "d"], "correct_index": i})
           for i, lbl in enumerate("ABCD")],
        [("finalize_bank", {})]]
EU_CALL = [("add_open_response_variant", {"group_id": EU, "variant_label": "A", "variant_summary": "transfer",
                                          "question_text": "Apply objects to a new sketch of your own.",
                                          "rubric_criteria": ["Names the structure"]})]


class _Endpoint:
    """Answers the main run from MAIN, the EU pass (offered one tool) with EU_CALL, and the intro (no tools)
    with INTRO; keeps every request's messages, as sent, so a test can fingerprint what the model saw."""

    def __init__(self):
        self.turn, self.sent = 0, []
        self.chat = self.completions = self

    def create(self, **kw):
        self.sent.append(json.loads(json.dumps(kw["messages"], default=lambda o: o.__dict__)))
        if "tools" not in kw:
            return NS(choices=[NS(message=NS(content=INTRO, tool_calls=None), finish_reason="stop")])
        if [t["function"]["name"] for t in kw["tools"]] == ["add_open_response_variant"]:
            script = EU_CALL
        else:
            script, self.turn = MAIN[min(self.turn, len(MAIN) - 1)], self.turn + 1
        calls = [NS(id=f"t{len(self.sent)}-{i}", type="function", function=NS(name=n, arguments=json.dumps(a)))
                 for i, (n, a) in enumerate(script)]
        return NS(choices=[NS(message=NS(content=None, tool_calls=calls), finish_reason="tool_calls")])


def _course(tmp_path):
    root = tmp_path / "course"
    vt = root / ".vtconfig"
    vt.mkdir(parents=True)
    (vt / "context.yaml").write_text("course_title: Creative Coding\nweeks:\n  week 7: {title: Objects}\n",
                                     encoding="utf-8")
    (vt / "quiz.yaml").write_text("eu_question: true\n", encoding="utf-8")
    (vt / "voice.md").write_text("Say we and let's.", encoding="utf-8")
    (vt / "domain.md").write_text("p5.js creative coding.", encoding="utf-8")
    doc = root / "output" / "week-7.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("Objects bundle data; arrays hold many of them.\n", encoding="utf-8")
    save_concept_map(ConceptMap(week="7", enduring_understanding="Structure lets a sketch scale.",
                                concepts=[Concept(name="Object Literals")]), concept_map_path(root, "7"))
    return root


def _generate(root, endpoint=None):
    endpoint = endpoint or _Endpoint()
    (unit,) = find_units(root / "output" / "week-7.md")
    with outcomes.capture(sink=lambda n: None):
        result = run_unit(unit, OpenAICompatProvider(client=endpoint, name="fake"), "m", QuizGenerator())
    return Path(unit.output_dir), result, endpoint


def _status(quiz_dir):
    with outcomes.capture(sink=lambda n: None):
        return record.status(quiz_dir)


def test_a_finished_quiz_records_what_it_was_made_from_and_reads_current(tmp_path):
    quiz_dir, result, endpoint = _generate(_course(tmp_path))
    assert result.finalized
    rec = records.load(quiz_dir)
    assert [s["step"] for s in rec["steps"]] == ["generate", "eu", "intro"]
    assert rec["kind"] == "quiz" and rec["unit"] == "7" and set(rec["output"]) == {"bank.json", "quiz.json"}
    gen = rec["steps"][0]
    assert {"output/week-7.md", ".vtconfig/concepts/week-7.yaml", ".vtconfig/voice.md", ".vtconfig/domain.md",
            ".vtconfig/quiz.yaml", ".vtconfig/context.yaml", "coursekit:quiz/system.md"} <= set(gen["read"])
    assert gen["options"] == {"text": "output/week-7.md"} and gen["model"] == "m"
    # each step's brief is the fingerprint of what the model was actually sent in that step
    main_sent, eu_sent, intro_sent = endpoint.sent[0], endpoint.sent[2], endpoint.sent[-1]
    briefs = {s["step"]: s["brief"] for s in rec["steps"]}
    assert briefs == {"generate": records.digest(main_sent), "eu": records.digest(eu_sent),
                      "intro": records.digest(intro_sent)}
    assert _status(quiz_dir) == records.Status("current")


def test_changing_the_units_text_makes_it_stale_and_names_the_file(tmp_path):
    root = _course(tmp_path)
    quiz_dir, _, _ = _generate(root)
    (root / "output" / "week-7.md").write_text("Re-transcribed: objects, arrays, and classes.", encoding="utf-8")
    st = _status(quiz_dir)
    assert st.state == "stale" and not st.edited
    assert any(r.startswith("generate: output/week-7.md") for r in st.reasons)
    assert any(r.startswith("eu: output/week-7.md") for r in st.reasons)
    assert not any(r.startswith("intro") for r in st.reasons)     # the intro isn't shown the text


def test_another_units_entry_in_context_yaml_changes_nothing(tmp_path):
    root = _course(tmp_path)
    quiz_dir, _, _ = _generate(root)
    ctx = root / ".vtconfig" / "context.yaml"
    ctx.write_text(ctx.read_text() + "  week 11: {title: Sound}\n", encoding="utf-8")
    assert _status(quiz_dir).state == "current"
    ctx.write_text(ctx.read_text().replace("Objects", "Objects and Arrays"), encoding="utf-8")   # its own label
    st = _status(quiz_dir)
    assert st.state == "stale" and any(".vtconfig/context.yaml" in r for r in st.reasons)


def test_moving_the_open_question_makes_only_the_intro_stale(tmp_path):
    quiz_dir, _, _ = _generate(_course(tmp_path))
    bank.set_order(quiz_dir, [EU, "c1"])
    assert records.load(quiz_dir)["steps"][-1]["step"] == "reorder"
    st = _status(quiz_dir)
    assert st.state == "stale" and not st.edited                  # coursekit wrote the change: not a hand edit
    assert st.reasons == ["intro: quizzes/week-7/quiz.json changed since it was made"]   # not the unit's text
    root = quiz_dir.parent.parent
    (root / "output" / "week-7.md").write_text("Re-transcribed.\n", encoding="utf-8")
    intro_reason = [r for r in _status(quiz_dir).reasons if r.startswith("intro")]
    assert intro_reason == ["intro: quizzes/week-7/quiz.json changed since it was made"]  # the text isn't its input


def test_a_hand_edit_reads_as_edited_and_the_next_step_remembers_it(tmp_path):
    quiz_dir, _, _ = _generate(_course(tmp_path))
    saved = json.loads((quiz_dir / "bank.json").read_text())
    saved["groups"]["c1"]["variants"]["A"]["question_text"] = "Which object literal is valid here?"
    (quiz_dir / "bank.json").write_text(json.dumps(saved, indent=2))
    st = _status(quiz_dir)
    assert st.edited and st.state == "current"                    # a variant isn't part of any brief
    bank.set_order(quiz_dir, ["c1", EU])                          # coursekit writes it again…
    steps = [s["step"] for s in records.load(quiz_dir)["steps"]]
    assert steps[-2:] == ["edited", "reorder"] and not _status(quiz_dir).edited   # …and notes the edit first


def test_a_changed_builtin_prompt_reads_as_outdated_not_stale(tmp_path, monkeypatch):
    import shutil
    from coursekit import prompts
    quiz_dir, _, _ = _generate(_course(tmp_path))
    shipped = tmp_path / "pkg" / "prompts"
    shutil.copytree(prompts._SHIPPED, shipped)
    monkeypatch.setattr(prompts, "_SHIPPED", shipped)
    monkeypatch.setattr(records, "_PACKAGE", tmp_path / "pkg")
    assert _status(quiz_dir).state == "current"                   # same prompts, moved
    (shipped / "quiz" / "intro.md").write_text((shipped / "quiz" / "intro.md").read_text() + "\nBe brief.\n")
    st = _status(quiz_dir)
    assert st.state == "outdated" and st.reasons == ["intro: made with an older coursekit "
                                                     "(coursekit:quiz/intro.md changed)"]


def test_a_quiz_made_before_records_is_unknown_and_stays_unknown(tmp_path):
    quiz_dir, _, _ = _generate(_course(tmp_path))
    (quiz_dir / records.RECORD).unlink()
    assert _status(quiz_dir).state == "unknown"
    bank.set_order(quiz_dir, [EU, "c1"])                          # a later step doesn't invent a history
    assert not (quiz_dir / records.RECORD).exists() and _status(quiz_dir).state == "unknown"


def test_an_unfinished_rerun_leaves_the_last_good_record(tmp_path):
    root = _course(tmp_path)
    quiz_dir, _, _ = _generate(root)
    before = (quiz_dir / records.RECORD).read_text()
    stalled = _Endpoint()
    stalled.create = lambda **kw: NS(choices=[NS(message=NS(content="thinking…", tool_calls=None),
                                                 finish_reason="stop")])
    stalled.chat = stalled.completions = stalled
    _, result, _ = _generate(root, stalled)
    assert not result.finalized and (quiz_dir / records.RECORD).read_text() == before


def test_a_fix_is_recorded_as_a_step(tmp_path):
    quiz_dir, _, _ = _generate(_course(tmp_path))
    finding = NS(flagged=True, week="week-7", group_id="c1", label="A")
    calls = []
    fix_one = fix.fix_one
    try:
        fix.fix_one = lambda *a, **k: calls.append(a) or NS(replaced=False, now_passes=False)
        fix.fix_course(quiz_dir.parent.parent, provider=None, model="m2", findings=[finding])
    finally:
        fix.fix_one = fix_one
    assert calls and [s["step"] for s in records.load(quiz_dir)["steps"]][-1] == "fix"
    assert _status(quiz_dir).state == "current"


def test_a_single_document_quiz_rebuilds_from_its_document(tmp_path):
    from coursekit.generate.quiz import targeted
    root = _course(tmp_path)
    reading = root / "week-7" / "readings" / "objects.md"
    reading.parent.mkdir(parents=True)
    reading.write_text("Objects group named values.", encoding="utf-8")
    with outcomes.capture(sink=lambda n: None):
        result = targeted.generate_targeted_quiz(reading, OpenAICompatProvider(client=_Endpoint(), name="f"), "m")
    quiz_dir = root / "quizzes" / targeted.targeted_slug(reading, None)
    assert records.load(quiz_dir)["steps"][0]["options"]["source"] == "week-7/readings/objects.md"
    assert _status(quiz_dir).state == "current"
    reading.write_text("Objects group named values; classes make many.", encoding="utf-8")
    st = _status(quiz_dir)
    assert st.state == "stale" and any("week-7/readings/objects.md" in r for r in st.reasons)
