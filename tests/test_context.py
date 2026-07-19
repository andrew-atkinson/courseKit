from context import build_messages


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
        "body", course_title="CC101 Special Topics",
        week_label="Week 3: Repetition", module="Module 2 – Chaos and Control",
    )[0]["content"]
    assert "Lecture context —" in system
    assert "Week 3: Repetition" in system
    assert "Module 2 – Chaos and Control" in system
    assert "course: CC101 Special Topics" in system


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
    assert msgs[1]["content"].strip() == "ONLY TRUE/FALSE."
    # the system prompt still falls through to the shipped default
    assert "THE ONLY WAY TO RECORD A QUESTION IS A TOOL CALL." in msgs[0]["content"]


def test_named_prompt_variants_can_be_selected(tmp_path):
    d = tmp_path / ".vtconfig" / "prompts" / "quiz"
    d.mkdir(parents=True)
    (d / "exam.md").write_text("---\nname: exam\ncategory: quiz\n---\n\nEXAM STYLE.\n",
                               encoding="utf-8")
    msgs = build_messages("body", project_root=tmp_path, task_prompt="exam")
    assert msgs[1]["content"].strip() == "EXAM STYLE."
