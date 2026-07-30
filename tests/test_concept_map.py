"""Concept-map schema, the knowledge.json reader/aggregator, and the editable-artifact IO.

Fully offline, synthetic fixtures — no model, no real course files.
"""

import json

import pytest

from coursekit.generate.page import concept_map as cm


def _write_knowledge(folder, stem, **fields):
    (folder / f"{stem}{cm.KNOWLEDGE_SUFFIX}").write_text(json.dumps(fields))


# ------------------------------------------------------------- reader / aggregator

def test_reads_and_unions_kcs_across_sources(tmp_path):
    _write_knowledge(tmp_path, "1 hand coding",
                     concepts=[{"name": "manual repetition", "why_it_matters": "it is tedious"}],
                     prerequisites=["variables"], leads_to=["for loops"],
                     code_examples=[{"language": "java", "code": "ellipse(0,0,5,5);"}])
    _write_knowledge(tmp_path, "2 for loops",
                     concepts=[{"name": "for loop", "why_it_matters": "automates repetition"},
                               {"name": "condition", "explanation": "when to stop"}],
                     prerequisites=["variables", "drawing primitives"],  # 'variables' repeats
                     leads_to=["nested loops"],
                     code_examples=[{"language": "java", "code": "for(...){}"}])

    wk = cm.read_week_knowledge(tmp_path, week="week 3")

    assert wk.week == "week 3"
    assert [k.name for k in wk.kcs] == ["manual repetition", "for loop", "condition"]
    # gist falls back explanation → why_it_matters
    assert {k.name: k.gist for k in wk.kcs}["condition"] == "when to stop"
    # each KC remembers its source stem
    assert {k.name: k.source for k in wk.kcs}["for loop"] == "2 for loops"
    # edges unioned, case-insensitive, first-seen order
    assert wk.prerequisites == ["variables", "drawing primitives"]
    assert wk.teaches_toward == ["for loops", "nested loops"]
    assert sorted(wk.sources) == ["1 hand coding", "2 for loops"]


def test_key_material_kinds_and_fidelity(tmp_path):
    # coding source: code_examples -> kind=language, verbatim
    _write_knowledge(tmp_path, "vid",
                     concepts=[{"name": "c"}],
                     code_examples=[{"language": "js", "code": "x"}])
    # neutral source: examples_and_demonstrations -> open kind, faithful
    _write_knowledge(tmp_path, "reading",
                     concepts=[{"name": "d"}],
                     examples_and_demonstrations=[{"kind": "case study", "description": "..."}])

    wk = cm.read_week_knowledge(tmp_path)
    got = {(m.kind, m.fidelity) for m in wk.key_material}
    assert ("js", "verbatim") in got
    assert ("case study", "faithful") in got


def test_missing_and_malformed_files_are_skipped(tmp_path):
    _write_knowledge(tmp_path, "good", concepts=[{"name": "real"}])
    (tmp_path / f"broken{cm.KNOWLEDGE_SUFFIX}").write_text("{not json")
    (tmp_path / f"array{cm.KNOWLEDGE_SUFFIX}").write_text("[1,2,3]")  # not a dict

    wk = cm.read_week_knowledge(tmp_path)
    assert [k.name for k in wk.kcs] == ["real"]


def test_empty_when_no_knowledge_files(tmp_path):
    wk = cm.read_week_knowledge(tmp_path)
    assert wk.kcs == [] and wk.sources == []


def test_accepts_week_doc_path_not_just_dir(tmp_path):
    _write_knowledge(tmp_path, "vid", concepts=[{"name": "c"}])
    doc = tmp_path / "week-3.md"
    doc.write_text("# Week 3")
    wk = cm.read_week_knowledge(doc)  # sibling knowledge files
    assert [k.name for k in wk.kcs] == ["c"]


# ------------------------------------------------------------- schema + IO

def test_concept_map_round_trips_through_yaml(tmp_path):
    pytest.importorskip("yaml")
    m = cm.ConceptMap(
        week="week 3",
        enduring_understanding="Computers repeat tirelessly; a loop hands them the pattern.",
        concepts=[cm.Concept(
            name="for loop", gist="automates repetition", level="apply",
            components=["initialization", "condition", "incrementer"],
            key_material=[cm.KeyMaterial(kind="code", fidelity="verbatim")],
            prerequisites=["variables"], teaches_toward=["nested loops"],
            sources=["2 for loops"])])

    path = cm.concept_map_path(tmp_path, "3")
    assert path.name == "week-3.yaml" and path.parent.name == "concepts"

    cm.save_concept_map(m, path)
    loaded = cm.load_concept_map(path)
    assert loaded == m


def test_load_absent_returns_none(tmp_path):
    assert cm.load_concept_map(tmp_path / "nope.yaml") is None


def test_load_invalid_raises(tmp_path):
    pytest.importorskip("yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("week: week 3\nbogus_field: 1\n")  # extra=forbid -> a broken edit is surfaced
    with pytest.raises(Exception):
        cm.load_concept_map(bad)
