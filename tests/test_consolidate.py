"""The consolidation pass — bundle rendering, JSON extraction, and driving a fake provider.

Offline: a fake provider returns canned JSON; no model runs.
"""

import json

import pytest

from coursekit.generate.page import concept_map as cm
from coursekit.generate.page import consolidate as con


class FakeProvider:
    """Records the messages it was called with; returns a canned reply."""
    def __init__(self, reply):
        self.reply = reply
        self.messages = None

    def chat(self, *, model, messages, temperature=None, **kw):
        self.messages = messages
        return self.reply


_MAP_JSON = json.dumps({
    "enduring_understanding": "Computers repeat tirelessly; a loop hands them the pattern.",
    "concepts": [{
        "name": "for loop", "gist": "automates repetition", "level": "apply",
        "components": ["initialization", "condition", "incrementer"],
        "key_material": [{"kind": "code", "fidelity": "verbatim"}],
        "prerequisites": ["variables"], "teaches_toward": ["nested loops"],
        "sources": ["2 for loops"]}]})


def _bundle():
    return cm.WeekKnowledge(
        week="week 3",
        kcs=[cm.KnowledgeComponent(name="initialization", gist="where to start", source="2 for loops"),
             cm.KnowledgeComponent(name="condition", gist="when to stop", source="2 for loops")],
        prerequisites=["variables"], teaches_toward=["nested loops"],
        key_material=[cm.KeyMaterial(kind="code", fidelity="verbatim")],
        sources=["2 for loops"])


# ------------------------------------------------------------- bundle rendering

def test_bundle_includes_kcs_edges_and_material():
    text = con._bundle_for_prompt(_bundle())
    assert "initialization" in text and "[source: 2 for loops]" in text
    assert "when to stop" in text
    assert "variables" in text and "nested loops" in text
    assert "code (verbatim)" in text


# ------------------------------------------------------------- JSON extraction

def test_extract_plain_json():
    assert con._extract_json('{"a": 1}') == {"a": 1}


def test_extract_from_fence():
    assert con._extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_from_surrounding_prose():
    assert con._extract_json('Here it is:\n{"a": 1}\nDone.') == {"a": 1}


def test_extract_invalid_raises_with_raw():
    with pytest.raises(ValueError, match="valid JSON"):
        con._extract_json("no json here")


# ------------------------------------------------------------- consolidate()

def test_consolidate_parses_into_concept_map():
    fp = FakeProvider(_MAP_JSON)
    m = con.consolidate(_bundle(), fp, "fake-model")
    assert isinstance(m, cm.ConceptMap)
    assert m.week == "week 3"                               # set by us, not the model
    assert m.enduring_understanding.startswith("Computers repeat")
    assert [c.name for c in m.concepts] == ["for loop"]
    assert m.concepts[0].components == ["initialization", "condition", "incrementer"]
    assert m.concepts[0].key_material[0].fidelity == "verbatim"


def test_consolidate_sends_bundle_and_domain():
    fp = FakeProvider(_MAP_JSON)
    con.consolidate(_bundle(), fp, "fake-model", domain="p5.js, not Processing.")
    system, user = fp.messages
    assert "p5.js" in system["content"]                    # domain preface prepended
    assert "consolidate" in system["content"].lower()      # the prompt body
    assert "initialization" in user["content"]             # the bundle


def test_consolidate_empty_bundle_skips_model():
    called = FakeProvider("SHOULD NOT BE USED")
    empty = cm.WeekKnowledge(week="week 9")
    m = con.consolidate(empty, called, "fake-model")
    assert m.week == "week 9" and m.concepts == []
    assert called.messages is None                          # no model call for an empty week


def test_week_label_overrides():
    fp = FakeProvider(_MAP_JSON)
    m = con.consolidate(_bundle(), fp, "fake-model", week="week 5")
    assert m.week == "week 5"


# ------------------------------------------------------------- fallback: text -> ConceptMap

def test_build_from_text_uses_extract_prompt_and_material():
    fp = FakeProvider(_MAP_JSON)
    m = con.build_concept_map_from_text("A week about arrays and loops.", fp, "fake-model",
                                        week="week 3")
    assert isinstance(m, cm.ConceptMap) and m.week == "week 3"
    assert [c.name for c in m.concepts] == ["for loop"]
    system, user = fp.messages
    assert "directly from" in system["content"]            # the extract prompt, not consolidate
    assert "A week about arrays and loops." in user["content"]
