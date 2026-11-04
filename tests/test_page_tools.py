import inspect
import json
from types import SimpleNamespace

import pytest

from coursekit.generate.page import page as P
from coursekit.generate.page import tools as T


def _session(call_log=None):
    return T.PageTools(P.PageDraft.new("test"), call_log=call_log)


@pytest.fixture
def s():
    return _session()


def _call(name, **args):
    return SimpleNamespace(id="c", name=name, arguments=json.dumps(args))


# ---------------------------------------- schema / signature drift (kills a whole risk class)

def test_every_tool_schema_matches_its_function_signature():
    for name, fn in _session().registry.items():
        schema = T._SCHEMAS[name]["parameters"]
        params = inspect.signature(fn).parameters
        want_props = set(params)
        assert set(schema["properties"]) == want_props, f"{name}: property/param mismatch"
        required_params = {p for p, v in params.items() if v.default is inspect._empty}
        assert set(schema["required"]) == required_params, f"{name}: required mismatch"


def test_specs_are_wrapped_for_the_wire():
    assert all(t["type"] == "function" and "function" in t for t in T.tools)
    assert {s["name"] for s in T.TOOL_SPECS} == set(_session().registry)


# -------------------------------------------------------- dispatch is safe

def test_unknown_tool_returns_error_not_raise(s):
    out = s.run_tool_calls([_call("add_video", src="x")])
    assert out[0][1].startswith("ERROR: no tool named 'add_video'")


def test_bad_args_do_not_lose_state(s):
    s.run_tool_calls([_call("add_heading", block_id="h", text="REVIEW")])
    # wrong type for level → ERROR, but the heading already added survives
    out = s.run_tool_calls([_call("add_heading", block_id="h2", text="x", level="two")])
    assert out[0][1].startswith("ERROR")
    assert "h" in s.draft.page.blocks


def test_empty_args_string_is_treated_as_no_args(s):
    s.run_tool_calls([_call("add_heading", block_id="h", text="REVIEW"),
                      _call("add_details", block_id="d", summary="Predict?", text="Yes.")])
    out = s.run_tool_calls([SimpleNamespace(id="c", name="finalize_page", arguments="")])
    assert out[0][1].startswith("OK")


# -------------------------------------------- the URL guardrail via the tool

def test_a_model_supplied_url_is_rejected(s):
    out = s.run_tool_calls([_call("add_paragraph", block_id="p",
                                  text="See https://example.com for more")])
    assert out[0][1].startswith("ERROR")
    assert "links are not allowed" in out[0][1]
    assert s.draft.page.blocks == {}   # nothing stored


# ------------------------------------------------------ a full page builds

def test_build_and_finalize_a_page(s):
    calls = [
        _call("add_heading", block_id="review", text="REVIEW", level=4),
        _call("add_bullets", block_id="recap", items=["expressions", "conditionals"]),
        _call("add_code", block_id="loop", code="for (let x=0; x<10; x++){}", language="js"),
        _call("add_glossary", block_id="terms",
              entries=[{"term": "for loop", "definition": "repeats a block"}]),
        _call("add_details", block_id="predict", summary="Predict: how many iterations?",
              text="Ten."),
    ]
    s.run_tool_calls(calls)
    assert list(s.draft.page.blocks) == ["review", "recap", "loop", "terms", "predict"]

    out = s.run_tool_calls([SimpleNamespace(id="c", name="finalize_page", arguments="{}")])
    assert out[0][1].startswith("OK")
    assert s.draft.is_finalized()


def test_call_log_records_raw_calls(tmp_path):
    s = _session(tmp_path / "calls.jsonl")
    s.run_tool_calls([_call("add_heading", block_id="h", text="REVIEW")])
    logged = (tmp_path / "calls.jsonl").read_text().strip()
    assert json.loads(logged)["name"] == "add_heading"


# ---- stop consuming a batch at the first finalize (the week-7 --detail full runaway) ----

def test_run_tool_calls_ignores_calls_after_a_successful_finalize(s):
    # A gemma --detail full run emitted its whole build AND several rebuilds in one turn, finalizing
    # 8x and leaving orphaned empty headings. Everything after the first finalize must be ignored.
    calls = [
        _call("add_heading", block_id="h1", text="Kept", role="concept"),
        _call("add_details", block_id="d", summary="Predict?", text="Yes."),
        _call("finalize_page"),
        _call("add_heading", block_id="h2", text="Runaway heading"),
        _call("add_paragraph", block_id="p2", text="Runaway content"),
    ]
    results = s.run_tool_calls(calls)
    page = s.draft.page
    assert "h1" in page.blocks and s.draft.is_finalized()
    assert "h2" not in page.blocks and "p2" not in page.blocks   # the rebuild is dropped
    assert results[-1][1].startswith("(ignored")


def test_a_rejected_finalize_does_not_stop_the_batch(s):
    # finalize fails with no heading present; the batch must keep going, not stop on the error.
    calls = [
        _call("finalize_page"),
        _call("add_heading", block_id="h1", text="Added after a failed finalize", role="concept"),
    ]
    results = s.run_tool_calls(calls)
    assert results[0][1].startswith("ERROR") and not s.draft.is_finalized()
    assert "h1" in s.draft.page.blocks                                # processing continued


def test_add_code_accepts_text_as_an_alias_for_code(s):
    # The model sometimes sends code under `text`; accepting it stops a section going all-bullets.
    s.run_tool_calls([_call("add_code", block_id="c1", text="let x = 1;")])
    b = s.draft.page.blocks["c1"]
    assert b.kind == "code" and b.code == "let x = 1;"


# ---- two pages at once: each session writes only to its own draft (CORE-3) ----

def test_two_pages_built_at_once_do_not_touch_each_other(tmp_path):
    a = T.PageTools(P.PageDraft.new("a", tmp_path / "a"), call_log=tmp_path / "a" / "calls.jsonl")
    b = T.PageTools(P.PageDraft.new("b", tmp_path / "b"), call_log=tmp_path / "b" / "calls.jsonl")
    a.run_tool_calls([_call("add_heading", block_id="ah", text="A")])
    b.run_tool_calls([_call("add_heading", block_id="bh", text="B")])
    a.run_tool_calls([_call("add_details", block_id="ad", summary="A?", text="a"), _call("finalize_page")])
    b.run_tool_calls([_call("add_paragraph", block_id="bp", text="still going")])

    assert list(a.draft.page.blocks) == ["ah", "ad"] and a.draft.is_finalized()
    assert list(b.draft.page.blocks) == ["bh", "bp"] and not b.draft.is_finalized()
    assert json.loads((tmp_path / "a" / "page.json").read_text())["page_id"] == "a"
    assert not (tmp_path / "b" / "page.json").exists()
    assert len((tmp_path / "a" / "calls.jsonl").read_text().splitlines()) == 3
    assert len((tmp_path / "b" / "calls.jsonl").read_text().splitlines()) == 2
