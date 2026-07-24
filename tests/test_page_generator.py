import json

from coursekit.discover import find_units
from coursekit.generate.page import page as P
from coursekit.generate.page.generator import PageGenerator
from coursekit.pipeline import run_unit
from coursekit.providers import OpenAICompatProvider


# ---- a scripted OpenAI-shaped endpoint returning page tool calls ----

class _Fn:
    def __init__(self, name, arguments):
        self.name, self.arguments = name, json.dumps(arguments)


class _ToolCall:
    def __init__(self, name, arguments, id="call"):
        self.function, self.id = _Fn(name, arguments), id


class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content, self.tool_calls = content, tool_calls


class _Choice:
    def __init__(self, message, finish_reason):
        self.message, self.finish_reason = message, finish_reason


class _Resp:
    def __init__(self, choice):
        self.choices = [choice]


PAGE_SCRIPT = [
    [("add_heading", {"block_id": "review", "text": "REVIEW", "level": 4}),
     ("add_bullets", {"block_id": "recap", "items": ["expressions", "conditionals"]}),
     ("add_code", {"block_id": "loop", "code": "for (let x=0; x<10; x++){}", "language": "js"})],
    [("finalize_page", {})],
]


class _ScriptedRaw:
    def __init__(self, script):
        self._script, self._i = script, 0
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        if len(kwargs["messages"]) == 2:
            self._i = 0
        turn = self._script[self._i]
        self._i += 1
        tcs = [_ToolCall(n, a) for n, a in turn]
        return _Resp(_Choice(_Msg(content=None, tool_calls=tcs), "tool_calls"))


def _client(script=PAGE_SCRIPT):
    return OpenAICompatProvider(client=_ScriptedRaw(script), name="fake")


def test_page_generator_runs_through_the_unchanged_driver(tmp_path):
    f = tmp_path / "week-3.md"
    f.write_text("This week covers for loops and while loops.", encoding="utf-8")
    unit = find_units(f)[0]

    res = run_unit(unit, _client(), "fake-model", PageGenerator())

    assert res.finalized
    assert res.counts == {"blocks": 3}
    # the generic driver wrote the artifacts…
    assert (unit.output_dir / "reply.txt").exists()
    saved = json.loads((unit.output_dir / "page.json").read_text())
    assert list(saved["blocks"]) == ["review", "recap", "loop"]
    assert saved["finalized"] is True
    assert saved["page_type"] == "week_intro"


def test_run_unit_reads_page_yaml_not_quiz_yaml(tmp_path):
    # Combined-run regression: discover binds unit.config to quiz.yaml, so run_unit must load the
    # PAGE generator's own page.yaml — otherwise a course's page prompt selection is silently ignored
    # (and the quiz's would leak in).
    root = tmp_path / "course"
    pd = root / ".vtconfig" / "prompts" / "page"
    pd.mkdir(parents=True)
    (root / ".vtconfig" / "page.yaml").write_text("task_prompt: brief\n", encoding="utf-8")
    (pd / "brief.md").write_text("PAGE-BRIEF-MARKER", encoding="utf-8")
    # a quiz.yaml that would mislead if it were (wrongly) used for the page pass
    (root / ".vtconfig" / "quiz.yaml").write_text("task_prompt: exam\n", encoding="utf-8")
    f = root / "output" / "week-3.md"
    f.parent.mkdir(parents=True)
    f.write_text("body", encoding="utf-8")
    unit = find_units(f)[0]

    raw = _ScriptedRaw(PAGE_SCRIPT)
    captured = {}
    _create = raw.create
    raw.create = lambda **kw: (captured.setdefault("messages", kw["messages"]), _create(**kw))[1]
    provider = OpenAICompatProvider(client=raw, name="fake")

    run_unit(unit, provider, "fake-model", PageGenerator())

    assert "PAGE-BRIEF-MARKER" in captured["messages"][1]["content"]   # page.yaml's brief was used


def test_page_generator_uses_the_shipped_page_prompts(tmp_path):
    # No .vtconfig: prompts resolve to the shipped prompts/page/{system,task}.md.
    f = tmp_path / "week-3.md"
    f.write_text("body", encoding="utf-8")
    unit = find_units(f)[0]
    gen = PageGenerator()

    from coursekit import courseconfig
    cfg = courseconfig.load(f, config_name="page.yaml")
    msgs = gen.build_messages(unit, "TRANSCRIPT-MARKER", cfg)

    assert "THE ONLY WAY TO ADD CONTENT IS A TOOL CALL" in msgs[0]["content"]
    assert "TRANSCRIPT-MARKER" in msgs[0]["content"]
    assert "Start now with the first heading." in msgs[1]["content"]


def test_page_run_writes_html_and_merges_supplements(tmp_path):
    root = tmp_path / "course"
    (root / ".vtconfig" / "pages").mkdir(parents=True)
    (root / ".vtconfig" / "pages" / "week-3.yaml").write_text(
        "references:\n  - label: Casey Reas\n    url: https://example.com/reas\n", encoding="utf-8")
    f = root / "output" / "week-3.md"
    f.parent.mkdir(parents=True)
    f.write_text("for loops and while loops", encoding="utf-8")
    unit = find_units(f)[0]
    assert unit.course_root == root.resolve()   # .vtconfig marker found

    res = run_unit(unit, _client(), "m", PageGenerator())
    assert res.finalized

    # page.json holds ONLY the model's blocks — the supplement URL is absent, so a regenerate
    # (which rewrites page.json) can never clobber the instructor's references.
    page_json = (unit.output_dir / "page.json").read_text()
    assert "example.com" not in page_json

    # the rendered HTML merges the supplement at render time
    doc = (unit.output_dir / "week-3.html").read_text()
    import re as _re
    assert _re.search(r"<h4[^>]*>.*REVIEW.*</h4>", doc, _re.S)
    assert 'href="https://example.com/reas"' in doc and ">Casey Reas</a>" in doc


def test_pages_write_to_a_pages_tree_not_quizzes(tmp_path):
    from coursekit.pipeline import run_course
    (tmp_path / "week 3").mkdir()
    (tmp_path / "week 3" / "week-3.md").write_text("for loops", encoding="utf-8")

    results = run_course(tmp_path, provider=_client(), model="m", generator=PageGenerator())

    assert results[0].output_dir.parent.name == "pages"   # not "quizzes"
    assert (results[0].output_dir / "page.json").exists()


def test_page_slug_comes_from_the_week_title(tmp_path):
    # A titled week yields a Canvas-style slug (week-3-repetition), not the bare filename slug.
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    (root / ".vtconfig" / "context.yaml").write_text(
        "weeks:\n  week 3: {title: Repetition}\n", encoding="utf-8")
    f = root / "output" / "week-3.md"
    f.parent.mkdir(parents=True)
    f.write_text("body", encoding="utf-8")
    unit = find_units(f)[0]

    run_unit(unit, _client(), "m", PageGenerator())

    assert (unit.output_dir / "week-3-repetition.html").exists()
    assert not (unit.output_dir / "week-3.html").exists()
