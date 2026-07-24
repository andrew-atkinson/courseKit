import inspect
import json
from types import SimpleNamespace

import pytest

from coursekit.generate.page import page as P
from coursekit.generate.page import tools as T


@pytest.fixture
def fresh():
    P.reset()          # reset the IR (tools.reset_state only clears tool-local state)
    T.reset_state()
    yield
    P.reset()
    T.reset_state()


def _call(name, **args):
    return SimpleNamespace(id="c", name=name, arguments=json.dumps(args))


# ---------------------------------------- schema / signature drift (kills a whole risk class)

def test_every_tool_schema_matches_its_function_signature():
    for name, fn in T.TOOL_REGISTRY.items():
        schema = T._SCHEMAS[name]["parameters"]
        params = inspect.signature(fn).parameters
        want_props = set(params)
        assert set(schema["properties"]) == want_props, f"{name}: property/param mismatch"
        required_params = {p for p, v in params.items() if v.default is inspect._empty}
        assert set(schema["required"]) == required_params, f"{name}: required mismatch"


def test_specs_are_wrapped_for_the_wire():
    assert all(t["type"] == "function" and "function" in t for t in T.tools)
    assert {s["name"] for s in T.TOOL_SPECS} == set(T.TOOL_REGISTRY)


# -------------------------------------------------------- dispatch is safe

def test_unknown_tool_returns_error_not_raise(fresh):
    out = T.run_tool_calls([_call("add_video", src="x")])
    assert out[0][1].startswith("ERROR: no tool named 'add_video'")


def test_bad_args_do_not_lose_state(fresh):
    T.run_tool_calls([_call("add_heading", block_id="h", text="REVIEW")])
    # wrong type for level → ERROR, but the heading already added survives
    out = T.run_tool_calls([_call("add_heading", block_id="h2", text="x", level="two")])
    assert out[0][1].startswith("ERROR")
    assert "h" in P.get().blocks


def test_empty_args_string_is_treated_as_no_args(fresh):
    T.run_tool_calls([_call("add_heading", block_id="h", text="REVIEW")])
    out = T.run_tool_calls([SimpleNamespace(id="c", name="finalize_page", arguments="")])
    assert out[0][1].startswith("OK")


# -------------------------------------------- the URL guardrail via the tool

def test_a_model_supplied_url_is_rejected(fresh):
    out = T.run_tool_calls([_call("add_paragraph", block_id="p",
                                  text="See https://example.com for more")])
    assert out[0][1].startswith("ERROR")
    assert "links are not allowed" in out[0][1]
    assert P.get().blocks == {}   # nothing stored


# ------------------------------------------------------ a full page builds

def test_build_and_finalize_a_page(fresh):
    calls = [
        _call("add_heading", block_id="review", text="REVIEW", level=4),
        _call("add_bullets", block_id="recap", items=["expressions", "conditionals"]),
        _call("add_code", block_id="loop", code="for (let x=0; x<10; x++){}", language="js"),
        _call("add_glossary", block_id="terms",
              entries=[{"term": "for loop", "definition": "repeats a block"}]),
    ]
    T.run_tool_calls(calls)
    assert list(P.get().blocks) == ["review", "recap", "loop", "terms"]

    out = T.run_tool_calls([SimpleNamespace(id="c", name="finalize_page", arguments="{}")])
    assert out[0][1].startswith("OK")
    assert P.is_finalized()


def test_call_log_records_raw_calls(fresh, tmp_path):
    T.set_call_log(tmp_path / "calls.jsonl")
    T.run_tool_calls([_call("add_heading", block_id="h", text="REVIEW")])
    logged = (tmp_path / "calls.jsonl").read_text().strip()
    assert json.loads(logged)["name"] == "add_heading"
