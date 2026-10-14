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


def test_render_leaves_an_unfilled_placeholder_visible(tmp_path):
    # A placeholder nobody fills can't be told apart from example code like `{i}`, so it stays as
    # written (visible, never silently emptied) instead of raising.
    _write(tmp_path / ".vtconfig/prompts/quiz/t.md", "t", "quiz", "Hello {who}")
    assert prompts.load("quiz", "t", project_root=tmp_path).render(other="x") == "Hello {who}"


def test_render_keeps_literal_braces_from_example_code(tmp_path):
    body = 'Code: for (let i = 0; i < 3; i++) { draw(i); }  py: f"{i}"  jinja: {{ x }}  name: {who}'
    _write(tmp_path / ".vtconfig/prompts/quiz/t.md", "t", "quiz", body)
    out = prompts.load("quiz", "t", project_root=tmp_path).render(who="world")
    assert out == body.replace("{who}", "world")          # only the named placeholder changed


def test_render_is_single_pass(tmp_path):
    # text inserted for one placeholder is never re-scanned for another (no injection)
    _write(tmp_path / ".vtconfig/prompts/quiz/t.md", "t", "quiz", "A {transcript} B {context_line}")
    out = prompts.load("quiz", "t", project_root=tmp_path).render(
        transcript="mentions {context_line} literally", context_line="CTX")
    assert out == "A mentions {context_line} literally B CTX"


@pytest.mark.parametrize("category, values", [
    ("quiz", {"context_line": "This lecture is week 3.", "transcript": "T"}),
    ("page", {"context_line": "This lecture is week 3.", "transcript": "T", "palette": "P"}),
])
def test_shipped_system_prompts_render_byte_identical_to_format(category, values):
    # the fix must not change what the model sees for the shipped prompts (no {{ }} escapes in them)
    p = prompts.load(category, "system")
    assert p.render(**values) == p.body.format(**values)



def test_quiz_builder_accepts_an_override_with_literal_braces(tmp_path):
    from coursekit.generate.quiz.context import build_messages
    _write(tmp_path / ".vtconfig/prompts/quiz/system.md", "system", "quiz",
           "Example: for (let i = 0; i < 3; i++) { draw(i); }  f\"{i}\"\n{context_line}\nMaterial:\n{transcript}")
    msgs = build_messages("TRANSCRIPT-TEXT", project_root=tmp_path, week_label="Week 3")
    sys_msg = msgs[0]["content"]
    assert "for (let i = 0; i < 3; i++) { draw(i); }" in sys_msg and 'f"{i}"' in sys_msg
    assert "TRANSCRIPT-TEXT" in sys_msg and "{context_line}" not in sys_msg


def test_page_builder_accepts_an_override_with_literal_braces(tmp_path):
    from coursekit.generate.page.context import build_messages
    _write(tmp_path / ".vtconfig/prompts/page/system.md", "system", "page",
           "Use { braces } freely.\n{context_line}\n{palette}\n{transcript}")
    sys_msg = build_messages("TRANSCRIPT-TEXT", project_root=tmp_path, week_label="Week 3")[0]["content"]
    assert "Use { braces } freely." in sys_msg and "TRANSCRIPT-TEXT" in sys_msg
    assert "{palette}" not in sys_msg and "{context_line}" not in sys_msg


# ------------------------------------------------------------- require (no silent material drop)

@pytest.mark.parametrize("category, module", [("quiz", "coursekit.generate.quiz.context"),
                                              ("page", "coursekit.generate.page.context")])
def test_override_without_transcript_is_refused_with_an_actionable_message(tmp_path, category, module):
    import importlib
    build = importlib.import_module(module).build_messages
    _write(tmp_path / f".vtconfig/prompts/{category}/system.md", "system", category,
           "A custom brief that forgot the material. {context_line}")
    with pytest.raises(SystemExit) as e:
        build("TRANSCRIPT-TEXT", project_root=tmp_path, week_label="Week 3")
    msg = str(e.value)
    assert "{transcript}" in msg and "system.md" in msg and f"prompts/{category}/" in msg


@pytest.mark.parametrize("category, module", [("quiz", "coursekit.generate.quiz.context"),
                                              ("page", "coursekit.generate.page.context")])
def test_context_line_and_palette_stay_optional(tmp_path, category, module):
    import importlib
    build = importlib.import_module(module).build_messages
    _write(tmp_path / f".vtconfig/prompts/{category}/system.md", "system", category,
           "Minimal brief.\n{transcript}")                     # no {context_line}, no {palette}
    sys_msg = build("TRANSCRIPT-TEXT", project_root=tmp_path, week_label="Week 3")[0]["content"]
    assert "TRANSCRIPT-TEXT" in sys_msg


def test_require_passes_when_present_and_names_every_missing_placeholder(tmp_path):
    _write(tmp_path / ".vtconfig/prompts/quiz/t.md", "t", "quiz", "has {transcript} only")
    p = prompts.load("quiz", "t", project_root=tmp_path)
    prompts.require(p, "transcript")                              # present → no error
    with pytest.raises(SystemExit, match=r"\{palette\}, \{context_line\}"):
        prompts.require(p, "transcript", "palette", "context_line")
