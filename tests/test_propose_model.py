"""Model-assisted proposer (FLOW-7 Phase 4). Offline: a fake provider stands in for the local model,
so the grouping logic + the no-fabricated-path guard are tested without a model."""

import json

from coursekit.coursestructure import CourseStructure
from coursekit.ingest import propose as P
from coursekit.ingest import propose_model as PM


class _Call:
    def __init__(self, name, **args):
        self.name = name
        self.arguments = json.dumps(args)


class _Reply:
    def __init__(self, calls):
        self.tool_calls = calls
        self.wants_tools = bool(calls)


class _FakeProvider:
    """Returns a canned set of assign_week tool calls; records the messages it was sent."""
    def __init__(self, calls):
        self._calls = calls
        self.sent = None

    def chat_with_tools(self, *, model, messages, tools):
        self.sent = messages
        return _Reply(self._calls)


def _course(tmp_path, *names):
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    for n in names:
        p = root / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"content of {n}", encoding="utf-8")
    return root


def test_model_groups_topic_named_files_into_weeks(tmp_path):
    # files with NO week markers in their names — the case the deterministic proposer can't key
    root = _course(tmp_path, "exposure.md", "aperture.md", "composition.md")
    prov = _FakeProvider([
        _Call("assign_week", number=1, title="Exposure", source_paths=["exposure.md", "aperture.md"]),
        _Call("assign_week", number=2, title="Composition", source_paths=["composition.md"]),
    ])
    prop = PM.propose_with_model(root, prov, "m")

    assert list(prop.weeks) == ["week 1", "week 2"]
    assert prop.weeks["week 1"]["title"] == "Exposure"
    assert [s["path"] for s in prop.weeks["week 1"]["sources"]] == ["aperture.md", "exposure.md"]  # sorted
    assert prop.weeks["week 1"]["sources"][0]["kind"] == "notes"      # kind derived from suffix, not the model
    assert prop.unassigned == []
    # the model was handed the real file list
    assert "exposure.md" in prov.sent[1]["content"]


def test_fabricated_paths_are_dropped_and_unplaced_files_surface(tmp_path):
    root = _course(tmp_path, "real.md", "leftover.md")
    prov = _FakeProvider([
        # GHOST.md doesn't exist; leftover.md the model never places
        _Call("assign_week", number=1, source_paths=["real.md", "GHOST.md"]),
    ])
    prop = PM.propose_with_model(root, prov, "m")
    assert [s["path"] for s in prop.weeks["week 1"]["sources"]] == ["real.md"]   # ghost dropped
    assert [p.name for p in prop.unassigned] == ["leftover.md"]                  # surfaced, not lost


def test_no_tool_calls_leaves_everything_unassigned(tmp_path):
    root = _course(tmp_path, "a.md", "b.md")
    prop = PM.propose_with_model(root, _FakeProvider([]), "m")
    assert prop.weeks == {}
    assert {p.name for p in prop.unassigned} == {"a.md", "b.md"}


def test_model_proposal_round_trips_through_the_overlay(tmp_path):
    root = _course(tmp_path, "materials/barrett.md")
    prov = _FakeProvider([_Call("assign_week", number=3, source_paths=["materials/barrett.md"])])
    P.write_overlay(PM.propose_with_model(root, prov, "m"))

    s = CourseStructure.load(root)
    assert s.has_declared_structure()
    got = s.sources_for("3")
    assert len(got) == 1 and got[0].resolve(root) == root / "materials" / "barrett.md"


def test_deep_manifest_includes_a_content_peek(tmp_path):
    root = _course(tmp_path, "reading.md")
    _, files = P.scan_supported(root)
    shallow = PM.build_manifest(files, root, deep=False)
    deep = PM.build_manifest(files, root, deep=True)
    assert "reading.md" in shallow and "content of" not in shallow
    assert "content of reading.md" in deep        # the peek only appears with --deep
