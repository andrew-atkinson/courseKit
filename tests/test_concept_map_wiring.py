"""Wiring: the concept map into page generation (context) and concept-delivery scoring.

Offline — builds messages and inspects them; a fake provider for the scorer.
"""

from coursekit.generate.page import concept_map as cm
from coursekit.generate.page import concept_delivery as cd
from coursekit.generate.page.context import build_messages, _concept_directive


def _map():
    return cm.ConceptMap(
        week="week 3",
        enduring_understanding="Computers repeat tirelessly; a loop hands them the pattern.",
        concepts=[
            cm.Concept(name="arrays", gist="ordered collections",
                       components=["array", "arr.push()", "arr.pop()"],
                       key_material=[cm.KeyMaterial(kind="code", fidelity="verbatim")]),
            cm.Concept(name="map()", gist="rescales a range")])


# ------------------------------------------------------------- point 1: generation prompt

def test_directive_lists_every_concept_and_the_pullquote():
    d = _concept_directive(_map())
    assert "1. arrays" in d and "2. map()" in d             # the un-skippable checklist
    assert "include its code" in d                          # key_material surfaced
    assert "arr.push(), arr.pop()" in d                     # components surfaced (the skipped parts)
    assert "INTRODUCE it the first time" in d               # the use-vs-introduce instruction
    assert "Computers repeat tirelessly" in d               # enduring understanding → pullquote


def test_directive_empty_without_map():
    assert _concept_directive(None) == ""
    assert _concept_directive(cm.ConceptMap(week="w")) == ""


def test_build_messages_appends_directive_when_map_present():
    msgs = build_messages("transcript text", concept_map=_map())
    task = msgs[1]["content"]
    assert "arrays" in task and "map()" in task
    # and absent when there is no map (today's behaviour unchanged)
    plain = build_messages("transcript text")[1]["content"]
    assert "arrays" not in plain


# ------------------------------------------------------------- point 2: scoring against a fixed list

class FakeProvider:
    def __init__(self, reply):
        self.reply, self.messages = reply, None

    def chat(self, *, model, messages, temperature=None, **kw):
        self.messages = messages
        return self.reply


def test_scores_against_given_concepts_not_rederived():
    fp = FakeProvider("- for loop: 3 | good\n- map(): 2 | thin")
    page = cm  # any object; _render_page is monkeypatched below
    # Use the real render by passing a minimal fake page with .blocks and .page_id
    class P:
        page_id = "week-3"
        blocks = {}
    pc = cd.evaluate_page_concepts(P(), "material", fp, "m", concepts=["for loop", "map()"])
    user = fp.messages[1]["content"]
    assert "only these" in user and "- for loop" in user and "- map()" in user
    assert [c.concept for c in pc.concepts] == ["for loop", "map()"]


def test_scores_by_rederivation_when_no_list():
    fp = FakeProvider("- x: 3 | ok")
    class P:
        page_id = "w"
        blocks = {}
    cd.evaluate_page_concepts(P(), "material", fp, "m")
    assert "each core concept" in fp.messages[1]["content"]
