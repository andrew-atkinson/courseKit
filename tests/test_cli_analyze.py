"""The `analyze` CLI verb — the phase that builds each week's concept map.

Offline: dry-run needs no model; the full-run test injects a fake provider.
"""

import json

import pytest

from coursekit import cli
from coursekit.generate.page import concept_map as cmap


def _course(tmp_path, *, with_knowledge=True):
    """A minimal course tree: a .vtconfig root and one week doc with a sibling knowledge.json."""
    (tmp_path / ".vtconfig").mkdir()
    wk = tmp_path / "output" / "week 3"
    wk.mkdir(parents=True)
    (wk / "week-3.md").write_text("# Week 3\nbody")
    if with_knowledge:
        (wk / f"2 for loops{cmap.KNOWLEDGE_SUFFIX}").write_text(json.dumps({
            "concepts": [{"name": "for loop", "why_it_matters": "automates repetition"},
                         {"name": "condition", "explanation": "when to stop"}],
            "prerequisites": ["variables"], "leads_to": ["nested loops"],
            "code_examples": [{"language": "js", "code": "for(...){}"}]}))
    return tmp_path / "output" / "week 3" / "week-3.md"


class FakeProvider:
    def chat(self, *, model, messages, temperature=None, **kw):
        return json.dumps({
            "enduring_understanding": "Computers repeat tirelessly; a loop hands them the pattern.",
            "concepts": [{"name": "for loop", "gist": "automates repetition", "level": "apply",
                          "components": ["for loop", "condition"],
                          "key_material": [{"kind": "code", "fidelity": "verbatim"}],
                          "prerequisites": ["variables"], "teaches_toward": ["nested loops"],
                          "sources": ["2 for loops"]}]})


# ------------------------------------------------------------- parser routing

def test_analyze_routes_with_args():
    args = cli.build_parser().parse_args(["analyze", "/tmp/course", "--week", "3", "--dry-run"])
    assert args.func is cli._cmd_analyze
    assert args.path == "/tmp/course" and args.week == ["3"] and args.dry_run is True


# ------------------------------------------------------------- dry-run (no model)

def test_dry_run_writes_nothing(tmp_path, capsys):
    doc = _course(tmp_path)
    args = cli.build_parser().parse_args(["analyze", str(doc), "--dry-run"])
    rc = cli._cmd_analyze(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "2 knowledge component(s)" in out
    assert not (tmp_path / ".vtconfig" / "concepts").exists()   # nothing written


# ------------------------------------------------------------- full run (fake provider)

def test_run_writes_concept_map(tmp_path, monkeypatch, capsys):
    pytest.importorskip("yaml")
    doc = _course(tmp_path)
    monkeypatch.setattr(cli, "_build_provider", lambda: FakeProvider())
    monkeypatch.setenv("MODEL_NAME", "fake-model")
    args = cli.build_parser().parse_args(["analyze", str(doc)])
    rc = cli._cmd_analyze(args)
    assert rc == 0

    out_path = cmap.concept_map_path(tmp_path, "3")
    assert out_path.exists()
    m = cmap.load_concept_map(out_path)
    assert m.week == "Week 3" or m.week.startswith("Week 3") or m.week  # a label was set
    assert [c.name for c in m.concepts] == ["for loop"]
    assert m.enduring_understanding.startswith("Computers repeat")
    assert "1 concept map(s) written" in capsys.readouterr().out


def test_run_skips_week_without_knowledge(tmp_path, monkeypatch, capsys):
    doc = _course(tmp_path, with_knowledge=False)
    monkeypatch.setattr(cli, "_build_provider", lambda: FakeProvider())
    monkeypatch.setenv("MODEL_NAME", "fake-model")
    args = cli.build_parser().parse_args(["analyze", str(doc)])
    rc = cli._cmd_analyze(args)
    assert rc == 0
    assert "no knowledge.json" in capsys.readouterr().out
    assert not cmap.concept_map_path(tmp_path, "3").exists()
