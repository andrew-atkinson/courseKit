"""Targeted page-section regeneration — the page fix loop.

Offline: a fake tool-calling provider scripts the corrected block and the verify verdict.
"""

import json

import pytest

from coursekit.generate.page import fix as pfix
from coursekit.generate.page import page as pageir
from coursekit.generate.page import tools
from coursekit.generate.quiz import evaluate as ev
from coursekit.providers.base import Reply, ToolCall


@pytest.fixture
def fresh():
    pageir.reset()
    tools.reset_state()
    yield
    pageir.reset()
    tools.reset_state()


class FixProvider:
    """Scripts a corrected block tool call, and a verify verdict that PASSes once the marker appears."""
    def __init__(self, tool, tool_args):
        self.tool, self.tool_args = tool, tool_args

    def chat_with_tools(self, *, model, messages, tools, temperature=None, max_tokens=None):
        return Reply(finish_reason="tool_calls",
                     tool_calls=[ToolCall("1", self.tool, json.dumps(self.tool_args))])

    def chat(self, *, model, messages, temperature=None, **kw):
        joined = " ".join(m.get("content", "") for m in messages if isinstance(m.get("content"), str))
        return "VERDICT: PASS" if "FIXED" in joined else "VERDICT: FLAG\nCONCERN: undeclared variable"

    def append_assistant(self, messages, reply):
        messages.append({"role": "assistant", "content": reply.content or ""})

    def append_tool_results(self, messages, results):
        for _id, content in results:
            messages.append({"role": "tool", "content": content})

    def append_user(self, messages, text):
        messages.append({"role": "user", "content": text})


def _finding():
    return ev.Finding(week="week-9", group_id="realtime-code", label="code",
                      stem="sound.play();", verdict="FLAG", concern="'sound' is not declared")


# ------------------------------------------------------------- the tool surface

def test_fix_tool_specs_are_only_add_tools():
    names = {s["name"] for s in pfix.FIX_TOOL_SPECS}
    assert "finalize_page" not in names and "get_page_report" not in names
    assert "add_code" in names and all(n.startswith("add_") for n in names)


# ------------------------------------------------------------- fix_one_block

def test_fix_one_block_replaces_and_verifies(fresh):
    tools.add_code("realtime-code", code="sound.play();", language="js")   # flawed: sound undeclared
    corrected = {"block_id": "realtime-code",
                 "code": "let sound; // FIXED\nfunction preload(){ sound = loadSound('a.mp3'); }",
                 "language": "js"}
    out = pfix.fix_one_block(_finding(), "material", FixProvider("add_code", corrected), "m",
                             critic="CRITIC")
    assert out.replaced is True and out.now_passes is True
    assert "let sound" in pageir.get().blocks["realtime-code"].code


def test_fix_one_block_gives_up_on_persistent_error(fresh):
    tools.add_code("realtime-code", code="sound.play();", language="js")
    # wrong block_id in the payload won't match; but add_code creates a NEW block, not replaces the
    # flagged one — so the flagged block is untouched and never "replaced".
    bad = {"block_id": "somethingelse", "code": "x // FIXED", "language": "js"}
    out = pfix.fix_one_block(_finding(), "material", FixProvider("add_code", bad), "m",
                             critic="CRITIC", max_turns=2)
    assert out.replaced is False and out.now_passes is None
    assert pageir.get().blocks["realtime-code"].code == "sound.play();"     # untouched


# ------------------------------------------------------------- fix_course_pages (integration)

def test_fix_course_pages_updates_page_on_disk(tmp_path, fresh):
    pytest.importorskip("yaml")
    (tmp_path / ".vtconfig").mkdir()
    (tmp_path / "week-9.md").write_text("Load the file into a variable you declare in preload().")
    outd = tmp_path / "pages" / "week-9"
    outd.mkdir(parents=True)
    pageir.init("c-week-9", out_dir=outd, title="Week 9", week_ref="week-9", slug="week-9")
    tools.add_heading("h", "Realtime")
    tools.add_code("realtime-code", code="sound.play();", language="js")
    pageir.reset()                                          # page.json now on disk at outd

    corrected = {"block_id": "realtime-code",
                 "code": "let sound; // FIXED\nfunction preload(){ sound = loadSound('a.mp3'); }",
                 "language": "js"}
    outcomes = pfix.fix_course_pages(tmp_path / "week-9.md", provider=FixProvider("add_code", corrected),
                                     model="m")

    assert len(outcomes) == 1 and outcomes[0].replaced and outcomes[0].now_passes
    from coursekit.generate.page.page import Page
    saved = Page.model_validate_json((outd / "page.json").read_text())
    assert "let sound" in saved.blocks["realtime-code"].code                # fix persisted
