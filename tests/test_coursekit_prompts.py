import pytest

from coursekit import prompts


def _write(path, name, category, body, description="d"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'---\nname: {name}\ncategory: {category}\ndescription: "{description}"\n'
                    f"---\n\n{body}\n", encoding="utf-8")


# ------------------------------------------------------------- shipped

def test_shipped_quiz_prompts_load():
    system = prompts.load("quiz", "system")
    task = prompts.load("quiz", "task")
    assert system.category == "quiz" and task.category == "quiz"
    assert "THE ONLY WAY TO RECORD A QUESTION IS A TOOL CALL." in system.body
    assert "Start by calling create_checklist." in task.body


def test_shipped_system_prompt_keeps_its_placeholders():
    # build_messages formats these; losing one would silently drop the transcript.
    body = prompts.load("quiz", "system").body
    assert "{transcript}" in body and "{context_line}" in body


def test_available_lists_the_quiz_category():
    assert {"system", "task"} <= set(prompts.available("quiz"))


def test_missing_prompt_raises_with_the_paths_it_tried():
    with pytest.raises(prompts.PromptNotFound, match="quiz/nope"):
        prompts.load("quiz", "nope")


# --------------------------------------------------- frontmatter parsing

def test_frontmatter_is_stripped_from_the_body(tmp_path):
    _write(tmp_path / ".vtconfig/prompts/quiz/x.md", "x", "quiz", "BODY TEXT")
    p = prompts.load("quiz", "x", project_root=tmp_path)
    assert p.body == "BODY TEXT"
    assert "---" not in p.body
    assert p.description == "d"


def test_a_file_without_frontmatter_is_all_body(tmp_path):
    d = tmp_path / ".vtconfig/prompts/quiz"
    d.mkdir(parents=True)
    (d / "bare.md").write_text("just the prompt", encoding="utf-8")
    assert prompts.load("quiz", "bare", project_root=tmp_path).body == "just the prompt"


def test_body_may_contain_triple_dashes_after_the_frontmatter(tmp_path):
    _write(tmp_path / ".vtconfig/prompts/quiz/y.md", "y", "quiz", "before\n---\nafter")
    assert prompts.load("quiz", "y", project_root=tmp_path).body == "before\n---\nafter"


# ------------------------------------------------------------- override

def test_project_override_beats_the_shipped_default(tmp_path):
    """The point of the whole mechanism: a course can change the brief without touching code."""
    _write(tmp_path / ".vtconfig/prompts/quiz/task.md", "task", "quiz", "MY OWN BRIEF")
    assert prompts.load("quiz", "task", project_root=tmp_path).body == "MY OWN BRIEF"
    # …and the shipped one is untouched for everyone else
    assert "Start by calling create_checklist." in prompts.load("quiz", "task").body


def test_override_falls_through_to_shipped_when_absent(tmp_path):
    # A project that overrides only the task still gets the shipped system prompt.
    _write(tmp_path / ".vtconfig/prompts/quiz/task.md", "task", "quiz", "MY OWN BRIEF")
    system = prompts.load("quiz", "system", project_root=tmp_path)
    assert "THE ONLY WAY TO RECORD A QUESTION IS A TOOL CALL." in system.body


def test_available_merges_overrides_and_defaults(tmp_path):
    _write(tmp_path / ".vtconfig/prompts/quiz/exam.md", "exam", "quiz", "b")
    names = set(prompts.available("quiz", project_root=tmp_path))
    assert {"system", "task", "exam"} <= names


# ------------------------------------------------------------- render

def test_render_substitutes_placeholders(tmp_path):
    _write(tmp_path / ".vtconfig/prompts/quiz/t.md", "t", "quiz", "Hello {who}")
    assert prompts.load("quiz", "t", project_root=tmp_path).render(who="world") == "Hello world"


def test_render_names_a_missing_placeholder(tmp_path):
    # Better a loud KeyError than a silently empty prompt.
    _write(tmp_path / ".vtconfig/prompts/quiz/t.md", "t", "quiz", "Hello {who}")
    with pytest.raises(KeyError, match="who"):
        prompts.load("quiz", "t", project_root=tmp_path).render(other="x")
