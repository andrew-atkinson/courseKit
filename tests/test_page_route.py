"""The deterministic page-generator router (generate/page/route.py) + the function dispatcher's
generator selection. Offline — the router is pure; the dispatch selection is checked by monkeypatch.
"""

from coursekit.generate.page import route


def _sig(chars=1000, concepts=3, span=500):
    return route.PageSignals(transcript_chars=chars, concept_count=concepts, largest_span_chars=span)


# ------------------------------------------------------------- the router (pure)

def test_small_week_stays_monolithic():
    assert route.choose_generator(_sig(chars=5000, concepts=4, span=2000),
                                  char_budget=24000, concept_budget=7, pass_budget=20000) == "monolithic"


def test_long_week_routes_to_decompose():
    r = route.decompose_reasons(_sig(chars=60000), char_budget=24000, concept_budget=7, pass_budget=20000)
    assert r and "chars" in r[0]
    assert route.choose_generator(_sig(chars=60000), char_budget=24000, concept_budget=7) == "decompose"


def test_many_concepts_routes_to_decompose():
    assert route.choose_generator(_sig(chars=5000, concepts=12), char_budget=24000, concept_budget=7,
                                  pass_budget=20000) == "decompose"


def test_a_dominant_span_routes_to_decompose():
    # a short-ish week whose ONE big concept span alone overruns a pass
    r = route.decompose_reasons(_sig(chars=20000, concepts=4, span=40000),
                                char_budget=24000, concept_budget=7, pass_budget=20000)
    assert any("span" in x for x in r)


def test_each_signal_is_independent():
    # all three under budget → monolithic; any one over → decompose
    assert route.decompose_reasons(_sig(chars=1000, concepts=2, span=800),
                                   char_budget=24000, concept_budget=7, pass_budget=20000) == []


def test_signals_for_measures_the_week():
    class _C:
        def __init__(self, name): self.name = name
    class _CM:
        concepts = [_C("Loops"), _C("Arrays")]
    sig = route.signals_for("x" * 4000, _CM(), {"Loops": "y" * 300, "Arrays": "z" * 900})
    assert sig.transcript_chars == 4000 and sig.concept_count == 2 and sig.largest_span_chars == 900


def test_signals_for_handles_no_map():
    sig = route.signals_for("abc", None, None)
    assert sig.concept_count == 0 and sig.largest_span_chars == 0
