"""The page dispatcher (generate/page/build.py): FUNCTION selection + teaching generator routing.

Offline — the model-driven generators are monkeypatched to sentinels; we assert only that the
dispatcher chooses the right path.
"""

import types

from coursekit.discover import find_units
from coursekit.generate.page import build as pb


def _unit(tmp_path, body="short body", *, quiz_yaml=""):
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    if quiz_yaml:
        (root / ".vtconfig" / "page.yaml").write_text(quiz_yaml, encoding="utf-8")
    f = root / "output" / "week-3.md"
    f.parent.mkdir(parents=True)
    f.write_text(body, encoding="utf-8")
    return find_units(f)[0]


def _fake_page():
    return types.SimpleNamespace(blocks={"a": 1, "b": 2})


# ------------------------------------------------------------- teaching: generator override

def test_generator_override_decompose(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(pb.decompose, "generate_page_decomposed",
                        lambda *a, **k: (seen.setdefault("via", "decompose"), (_fake_page(), []))[1])
    r = pb.build_page_unit(_unit(tmp_path), None, "m", function="teaching", generator="decompose")
    assert seen["via"] == "decompose"
    assert r.finalized and r.counts["blocks"] == 2 and r.output_dir.name == "week-3"


def test_generator_override_monolithic(monkeypatch, tmp_path):
    import coursekit.pipeline as pl
    seen = {}
    monkeypatch.setattr(pl, "run_unit",
                        lambda *a, **k: (seen.setdefault("via", "monolithic"), "SENTINEL")[1])
    out = pb.build_page_unit(_unit(tmp_path), None, "m", function="teaching", generator="monolithic")
    assert seen["via"] == "monolithic" and out == "SENTINEL"


# ------------------------------------------------------------- teaching: the auto router

def test_auto_routes_short_week_to_monolithic(tmp_path):
    # a tiny transcript, no concept map → all signals under budget → monolithic
    assert pb.route_teaching(_unit(tmp_path, body="tiny"), verbose=False) == "monolithic"


def test_auto_routes_long_week_to_decompose(tmp_path):
    long_body = "paragraph. " * 3000                      # ~33K chars, over the char budget
    assert pb.route_teaching(_unit(tmp_path, long_body), verbose=False) == "decompose"


def test_page_yaml_can_tune_the_router(tmp_path):
    # a small char budget makes even a short week route to decompose
    u = _unit(tmp_path, body="x" * 500, quiz_yaml="mono_char_budget: 100\n")
    assert pb.route_teaching(u, verbose=False) == "decompose"


# ------------------------------------------------------------- overview: deterministic, no model

def test_overview_function_writes_a_page(tmp_path):
    u = _unit(tmp_path)
    r = pb.build_page_unit(u, None, "m", function="overview")
    assert r.finalized and r.output_dir.name == "week-3-overview"
    assert (r.output_dir / "page.json").exists()
