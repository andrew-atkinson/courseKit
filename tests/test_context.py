from coursekit.generate.quiz.context import build_messages


def test_returns_system_then_user():
    msgs = build_messages("A transcript body.")
    assert [m["role"] for m in msgs] == ["system", "user"]


def test_transcript_is_embedded():
    msgs = build_messages("UNIQUE-TRANSCRIPT-MARKER inside.")
    assert "UNIQUE-TRANSCRIPT-MARKER inside." in msgs[0]["content"]


def test_no_metadata_line_when_none_given():
    system = build_messages("body")[0]["content"]
    assert "Lecture context" not in system


def test_metadata_woven_in_when_given():
    system = build_messages(
        "body", course_title="ARGS260 Special Topics",
        week_label="Week 3: Repetition", module="Module 2 – Chaos and Control",
    )[0]["content"]
    assert "Lecture context —" in system
    assert "Week 3: Repetition" in system
    assert "Module 2 – Chaos and Control" in system
    assert "course: ARGS260 Special Topics" in system


def test_partial_metadata_is_fine():
    system = build_messages("body", week_label="Week 5")[0]["content"]
    assert "Lecture context — Week 5." in system
    assert "course:" not in system


def test_structured_output_rules_are_retained():
    system = build_messages("body")[0]["content"]
    # The load-bearing instructions must survive the refactor.
    assert "THE ONLY WAY TO RECORD A QUESTION IS A TOOL CALL." in system
    assert "REPLACES the earlier version" in system
    assert "Do not use Rich markup" in system


def test_user_message_still_starts_the_tool_sequence():
    user = build_messages("body")[1]["content"]
    assert "Start by calling create_checklist." in user
    assert "variant_summary" in user


def test_task_brief_is_subject_neutral():
    # the blocker fix: no group is hard-wired to code-completion, so a non-coding course generates
    user = build_messages("body")[1]["content"]
    assert "c5: a code-completion" not in user      # not a fixed, forced group any more
    assert "c1 to c4" not in user
    # code-completion is offered conditionally, and the domain note carries the specifics
    assert "domain note" in user
    assert "where it fits" in user or "contains code" in user


def test_is_pure_no_env_dependency(monkeypatch):
    # Importing context.py used to read TRANSCRIPTION at import time; it must not now.
    monkeypatch.delenv("TRANSCRIPTION", raising=False)
    assert build_messages("body")  # does not raise


# ------------------------------------------- prompts come from files now

def test_prompts_load_from_the_shipped_files():
    from coursekit import prompts
    system = build_messages("body")[0]["content"]
    assert prompts.load("quiz", "system").body.split("\n")[0] in system


def test_a_course_can_override_the_task_brief(tmp_path):
    """The payoff of externalising: change the brief per course, no code edit."""
    d = tmp_path / ".vtconfig" / "prompts" / "quiz"
    d.mkdir(parents=True)
    (d / "task.md").write_text("---\nname: task\ncategory: quiz\n---\n\nONLY TRUE/FALSE.\n",
                               encoding="utf-8")

    msgs = build_messages("body", project_root=tmp_path)
    # the override replaces the shipped brief; the shape directive still rides along at the end
    assert msgs[1]["content"].strip().startswith("ONLY TRUE/FALSE.")
    assert "How many groups" in msgs[1]["content"]
    # the system prompt still falls through to the shipped default
    assert "THE ONLY WAY TO RECORD A QUESTION IS A TOOL CALL." in msgs[0]["content"]


def test_named_prompt_variants_can_be_selected(tmp_path):
    d = tmp_path / ".vtconfig" / "prompts" / "quiz"
    d.mkdir(parents=True)
    (d / "exam.md").write_text("---\nname: exam\ncategory: quiz\n---\n\nEXAM STYLE.\n",
                               encoding="utf-8")
    msgs = build_messages("body", project_root=tmp_path, task_prompt="exam")
    assert msgs[1]["content"].strip().startswith("EXAM STYLE.")


# ------------------------------------------------------------- flexible quiz shape

from coursekit.generate.quiz.context import _shape_directive
from coursekit.generate.page.concept_map import ConceptMap, Concept


def test_shape_directive_fixed_count_overrides():
    d = _shape_directive(None, questions=8)
    assert "EXACTLY 8 question groups" in d


def test_shape_directive_from_concept_map():
    cm = ConceptMap(week="w", enduring_understanding="Structure lets one pattern govern many.",
                    concepts=[Concept(name="for loop", components=["initialization", "condition"]),
                              Concept(name="map()")])
    d = _shape_directive(cm)
    assert "for loop" in d and "map()" in d                # one group per concept
    assert "initialization, condition" in d                # KCs seed the variants
    assert "Structure lets one pattern govern many." in d  # enduring understanding shown (frames questions)
    assert "Do NOT add an MC group for the enduring understanding" in d   # ASMT-1: no MC group for the EU
    # The EU open-response question is NOT built in the main pass — it's the deterministic EU pass
    # (coursekit/generate/quiz/eu.py). The shape directive never asks the model to add it.
    assert "add_open_response_variant" not in d


def test_shape_directive_default_lets_material_decide():
    d = _shape_directive(None)
    assert "let the material decide" in d.lower() and "not a fixed count" in d


def test_build_messages_appends_the_shape():
    assert "EXACTLY 6 question groups" in build_messages("body", questions=6)[1]["content"]
    assert "let the material decide" in build_messages("body")[1]["content"].lower()


def test_shape_directive_fixed_count_with_map_stays_grounded():
    cm = ConceptMap(week="w", enduring_understanding="Structure governs many.",
                    concepts=[Concept(name="for loop"), Concept(name="map()")])
    d = _shape_directive(cm, questions=9)
    assert "EXACTLY 9 question groups" in d
    assert "for loop" in d and "map()" in d          # a fixed count still covers the concepts


def test_concept_map_questions_field():
    import pytest
    assert ConceptMap(week="w", questions=8).questions == 8
    with pytest.raises(Exception):
        ConceptMap(week="w", questions=0)            # ge=1


def test_per_week_questions_beats_course_quiz_yaml(tmp_path):
    import pytest
    pytest.importorskip("yaml")
    from coursekit import courseconfig
    from coursekit.discover import find_units
    from coursekit.generate.quiz.generator import QuizGenerator
    from coursekit.generate.page.concept_map import save_concept_map, concept_map_path
    (tmp_path / ".vtconfig").mkdir()
    (tmp_path / ".vtconfig" / "quiz.yaml").write_text("questions: 5\n", encoding="utf-8")
    save_concept_map(ConceptMap(week="week 3", questions=9, concepts=[Concept(name="for loop")]),
                     concept_map_path(tmp_path, "3"))
    f = tmp_path / "output" / "week-3.md"
    f.parent.mkdir(parents=True)
    f.write_text("for loops", encoding="utf-8")
    unit = find_units(f)[0]
    cfg = courseconfig.load(f, config_name="quiz.yaml")
    msgs = QuizGenerator().build_messages(unit, "for loops", cfg)
    assert "EXACTLY 9 question groups" in msgs[1]["content"]   # per-week (9) wins over course (5)
