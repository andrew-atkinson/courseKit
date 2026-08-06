"""Week & module overview pages — the deterministic assembly (the framing model call is separate)."""

from coursekit.generate import overview
from coursekit.generate.page.concept_map import Concept, ConceptMap


def _cm(eu="", concepts=()):
    return ConceptMap(week="3", enduring_understanding=eu, concepts=list(concepts))


def test_week_overview_assembles_topics_big_idea_and_objectives():
    cm = _cm("Repetition lets code do the labour.",
             [Concept(name="for loop", gist="repeat a block", level="apply"),
              Concept(name="nesting", gist="grids")])          # no level
    page = overview.build_week_overview("Creative Coding", "3", "Repetition", "Chaos & Control", cm)
    assert page.page_type == "week_overview" and page.slug == "week-3-overview"
    assert page.title == "Week 3: Repetition" and page.finalized

    kinds = [b.kind for b in page.blocks.values()]
    assert "pullquote" in kinds                                # the enduring understanding is foregrounded
    assert page.blocks["big-idea"].text == "Repetition lets code do the labour."

    topics = page.blocks["cover"]
    assert topics.kind == "bullets"
    assert any("for loop — repeat a block" in i for i in topics.items)

    assert page.blocks["obj"].items == ["apply for loop"]      # objectives ONLY from concepts with a level


def test_week_overview_prefers_supplied_framing_over_the_default_intro():
    page = overview.build_week_overview("C", "3", "T", "M", _cm(concepts=[Concept(name="x")]),
                                        framing="Welcome — this week you build your first systems.")
    assert page.blocks["intro"].text == "Welcome — this week you build your first systems."


def test_week_overview_without_a_big_idea_or_levels_stays_minimal():
    page = overview.build_week_overview("C", "5", "T", "", _cm(concepts=[Concept(name="x")]))
    kinds = {b.kind for b in page.blocks.values()}
    assert "pullquote" not in kinds and "obj" not in page.blocks   # nothing to show → nothing shown
    assert page.blocks["cover"].items == ["x"]


def test_module_overview_lists_its_weeks_with_themes():
    page = overview.build_module_overview("C", "Chaos and Control",
                                          [("3", "Repetition", "Loops manage repetition."),
                                           ("4", "Randomness", "Controlled chaos.")])
    assert page.page_type == "module_overview" and page.slug == "module-chaos-and-control-overview"
    assert page.title == "Chaos and Control"
    items = page.blocks["weeks"].items
    assert any("Week 3: Repetition — Loops manage repetition." in i for i in items)
    assert any("Week 4: Randomness — Controlled chaos." in i for i in items)
