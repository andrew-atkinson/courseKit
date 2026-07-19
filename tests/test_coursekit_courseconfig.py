import builtins

import pytest

from coursekit import courseconfig as cc


# --------------------------------------------------------------- fixtures

def _project(tmp_path, *, config=None, context=None, config_name="quiz.yaml"):
    """A course tree with a .vtconfig/ marker and, optionally, the two yaml files written raw."""
    root = tmp_path / "a course"
    vt = root / ".vtconfig"
    vt.mkdir(parents=True)
    if config is not None:
        (vt / config_name).write_text(config, encoding="utf-8")
    if context is not None:
        (vt / "context.yaml").write_text(context, encoding="utf-8")
    inp = root / "output" / "week-3.md"
    inp.parent.mkdir(parents=True)
    inp.write_text("transcript", encoding="utf-8")
    return root, inp


# ----------------------------------------------------- test 1: week_key

@pytest.mark.parametrize("ref,expected", [
    ("week-3.md", "3"),
    ("Week 3: Repetition", "3"),
    ("week 3", "3"),
    ("week_10", "10"),
    ("3", "3"),
    (3, "3"),
    ("intro.md", None),
    ("", None),
    ("chapter-2-notes", None),   # a number, but not a *week* number
])
def test_week_key_normalises(ref, expected):
    assert cc.week_key(ref) == expected


# ------------------------------------------- test 2: load never raises

def test_load_with_no_vtconfig_is_empty_not_an_error(tmp_path):
    f = tmp_path / "loose.md"
    f.write_text("x", encoding="utf-8")
    cfg = cc.load(f, config_name="quiz.yaml")
    assert cfg.root is None
    assert cfg.config == {} and cfg.context == {}
    assert cfg.course_title is None
    assert cfg.week(3) == {}


def test_load_with_marker_but_no_files(tmp_path):
    root, inp = _project(tmp_path)  # .vtconfig exists, both yaml absent
    cfg = cc.load(inp, config_name="quiz.yaml")
    assert cfg.root == root
    assert cfg.config == {} and cfg.context == {}
    # paths still point into .vtconfig so a future write has a target
    assert cfg.config_path == root / ".vtconfig" / "quiz.yaml"
    assert cfg.context_path == root / ".vtconfig" / "context.yaml"


def test_malformed_yaml_degrades_to_empty(tmp_path):
    root, inp = _project(tmp_path, config="model: [unclosed\n:::")
    cfg = cc.load(inp, config_name="quiz.yaml")
    assert cfg.config == {}


def test_a_yaml_scalar_is_not_a_config(tmp_path):
    # A file that parses but isn't a mapping must not become a dict-shaped surprise.
    root, inp = _project(tmp_path, config="just a string")
    assert cc.load(inp, config_name="quiz.yaml").config == {}


def test_missing_pyyaml_degrades(tmp_path, monkeypatch):
    root, inp = _project(tmp_path, config="model: gemma\n")
    real_import = builtins.__import__

    def no_yaml(name, *a, **k):
        if name == "yaml":
            raise ImportError("no pyyaml")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_yaml)
    cfg = cc.load(inp, config_name="quiz.yaml")
    assert cfg.config == {}   # degraded, did not raise


# ------------------------------------ test 3: legacy_search is opt-in

def test_loose_context_is_ignored_by_default(tmp_path):
    # A bare context.yaml two dirs above the input, no .vtconfig anywhere.
    (tmp_path / "context.yaml").write_text("course_title: Loose\n", encoding="utf-8")
    inp = tmp_path / "a" / "b" / "week-3.md"
    inp.parent.mkdir(parents=True)
    inp.write_text("x", encoding="utf-8")

    assert cc.load(inp, config_name="quiz.yaml").course_title is None
    # …but opting in finds it, which is the transcriber's back-compat path
    assert cc.load(inp, legacy_search=True).course_title == "Loose"


def test_legacy_search_does_not_reach_beyond_grandparent(tmp_path):
    (tmp_path / "context.yaml").write_text("course_title: TooFar\n", encoding="utf-8")
    inp = tmp_path / "a" / "b" / "c" / "week-3.md"   # 3 levels down
    inp.parent.mkdir(parents=True)
    inp.write_text("x", encoding="utf-8")
    assert cc.load(inp, legacy_search=True).course_title is None


# -------------------------------- test 4: prompt_name precedence

def test_prompt_name_precedence(tmp_path):
    root, inp = _project(tmp_path, config="task_prompt: exam\n")
    cfg = cc.load(inp, config_name="quiz.yaml")
    assert cfg.prompt_name("task_prompt") == "exam"                 # config
    assert cfg.prompt_name("task_prompt", cli_arg="essay") == "essay"  # CLI wins
    assert cfg.prompt_name("system_prompt") == "default"           # unset -> default


def test_value_reads_this_tools_config(tmp_path):
    root, inp = _project(tmp_path, config="model: my-quiz-model\n")
    cfg = cc.load(inp, config_name="quiz.yaml")
    assert cfg.value("model") == "my-quiz-model"
    assert cfg.value("missing", "fallback") == "fallback"


def test_configs_are_separate_files(tmp_path):
    # quiz.yaml and config.yaml coexist; each tool reads only its own.
    root, inp = _project(tmp_path, config="model: quiz-model\n", config_name="quiz.yaml")
    (root / ".vtconfig" / "config.yaml").write_text("default_lm_model: vt-model\n", encoding="utf-8")

    quiz = cc.load(inp, config_name="quiz.yaml")
    vt = cc.load(inp, config_name="config.yaml")
    assert quiz.value("model") == "quiz-model"
    assert quiz.value("default_lm_model") is None       # not quizbot's key
    assert vt.value("default_lm_model") == "vt-model"


def test_week_reads_shared_context(tmp_path):
    ctx = (
        "course_title: CC101\n"
        "weeks:\n"
        "  week 3:\n"
        "    title: Repetition\n"
        "    module: Chaos and Control\n"
    )
    root, inp = _project(tmp_path, context=ctx)
    cfg = cc.load(inp, config_name="quiz.yaml")
    assert cfg.course_title == "CC101"
    assert cfg.week("week-3.md")["title"] == "Repetition"
    assert cfg.week(3)["module"] == "Chaos and Control"
    assert cfg.week(99) == {}
