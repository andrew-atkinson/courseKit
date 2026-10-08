"""Expectation proposer (FLOW-9 Phase 1.5, Layer A) — offline. L0 modal induction + L1-deterministic
concept-map rules → a drafted `expect:` block. No model."""

import json

import pytest

from coursekit import courseconfig
from coursekit.generate.page.concept_map import Concept, ConceptMap, concept_map_path, save_concept_map
from coursekit.ingest import propose_expectations as pe


def _artifact(root, kind, slug, body):
    d = root / kind / slug
    d.mkdir(parents=True)
    (d / ("page.json" if kind == "pages" else "bank.json" if kind == "quizzes" else "assignment.json")
     ).write_text(body, encoding="utf-8")


def _cmap(root, week, *, eu="", n_concepts=1):
    cm = ConceptMap(week=week, enduring_understanding=eu,
                    concepts=[Concept(name=f"c{i}") for i in range(n_concepts)])
    save_concept_map(cm, concept_map_path(root, week))


def _course(tmp_path, *, eu_all=True, dense_week=None, assignment=True):
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    for wk in ("week-1", "week-2", "week-3"):
        _artifact(root, "pages", wk, json.dumps({"week_ref": wk}))
        _artifact(root, "quizzes", wk, "{}")
    if assignment:
        _artifact(root, "assignments", "week-1", json.dumps({"week_ref": "week-1"}))
    for i, wk in enumerate(("1", "2", "3")):
        eu = "Big idea." if (eu_all or wk == "1") else ""
        nc = 8 if dense_week == wk else 2
        _cmap(root, wk, eu=eu, n_concepts=nc)
    return root


def test_L0_proposes_week_rules_for_modal_types(tmp_path):
    expect, notes = pe.propose_expectations(_course(tmp_path))
    week_rules = {r["artifact"] for r in expect["defaults"] if r["scope"] == "week"}
    assert {"page", "quiz", "concept-map"} <= week_rules          # all present in 3/3 weeks → week rules
    assert all(r["count"] == 1 for r in expect["defaults"])


def test_L0_flags_a_sparse_type_instead_of_fabricating_a_rule(tmp_path):
    expect, notes = pe.propose_expectations(_course(tmp_path, assignment=True))
    assert not any(r["artifact"] == "assignment" for r in expect["defaults"])   # 1/3 → NOT a rule
    assert any("assignment" in note and "DECISION NEEDED" in note for note in notes)


def test_L1_eu_universal_becomes_a_week_default(tmp_path):
    expect, notes = pe.propose_expectations(_course(tmp_path, eu_all=True))
    assert any(r["artifact"] == "quiz:eu" and r["scope"] == "week" for r in expect["defaults"])
    assert any("quiz:eu" in note and "UbD" in note for note in notes)


def test_L1_eu_partial_becomes_per_week_overrides(tmp_path):
    expect, notes = pe.propose_expectations(_course(tmp_path, eu_all=False))   # only week 1 has an EU
    assert not any(r["artifact"] == "quiz:eu" for r in expect["defaults"])      # not universal → no default
    assert expect["overrides"]["week"]["1"]["quiz:eu"] == 1


def test_L1_dense_week_gets_a_glossary_override(tmp_path):
    expect, notes = pe.propose_expectations(_course(tmp_path, dense_week="2"))
    assert expect["overrides"]["week"]["2"]["page:glossary"] == 1
    assert any("glossary" in note and "CLT" in note for note in notes)


def test_rationale_grounds_every_default_in_a_fact(tmp_path):
    _expect, notes = pe.propose_expectations(_course(tmp_path))
    assert any("modal" in n for n in notes)         # L0 cites the pattern
    assert any("UbD" in n for n in notes)           # L1 cites the framework + the map fact


def test_write_is_merge_aware_and_refuses_to_clobber(tmp_path):
    root = _course(tmp_path)
    overlay = root / ".vtconfig" / "structure.coursekit.yaml"
    overlay.write_text('weeks:\n  "week 1": {doc: output/week-1.md}\n'
                       'grading:\n  groups: [{name: Quizzes, weight: 100}]\n', encoding="utf-8")
    expect, notes = pe.propose_expectations(root)

    dest = pe.write_expectations(root, expect, notes)
    data = courseconfig._read_yaml(dest)
    assert "week 1" in data["weeks"] and data["grading"]["groups"]    # pre-existing blocks preserved
    assert data["expect"]["defaults"]                                 # the new block landed

    with pytest.raises(SystemExit):                                   # second write refuses without --force
        pe.write_expectations(root, expect, notes)
    pe.write_expectations(root, expect, notes, force=True)            # --force redrafts


def test_no_artifacts_yields_nothing(tmp_path):
    root = tmp_path / "bare"
    (root / ".vtconfig").mkdir(parents=True)
    expect, _notes = pe.propose_expectations(root)
    assert expect["defaults"] == [] and "overrides" not in expect
