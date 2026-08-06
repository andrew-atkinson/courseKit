"""The deterministic half of the per-concept decomposition prototype: the material slicer.

The model-driven passes are exercised by hand on a real course; here we pin the slicer, which is the
lever (each concept sees a few K chars of relevant transcript, not the whole week)."""

from coursekit.generate.page import decompose
from coursekit.generate.page.concept_map import Concept

TRANSCRIPT = (
    "Loops let you repeat a block of code many times using a for statement.\n\n"
    "Colors in p5 use RGB values from 0 to 255 for red, green, and blue.\n\n"
    "Arrays are ordered collections; you push items to add and pop to remove, storing data.\n\n"
    "You can push more items onto an array whenever the sketch needs another element."
)


def _c(name, **kw):
    return Concept(name=name, **kw)


def test_slice_picks_the_relevant_chunks_only():
    s = decompose.slice_material(TRANSCRIPT, _c("Arrays", gist="ordered collections",
                                               components=["push method", "pop method"]))
    assert "Arrays are ordered collections" in s
    assert "push more items" in s            # the second array-relevant chunk is included too
    assert "Loops let you repeat" not in s   # irrelevant chunks are dropped
    assert "Colors in p5" not in s


def test_slice_preserves_document_order():
    s = decompose.slice_material(TRANSCRIPT, _c("Arrays", components=["push"]))
    assert s.index("Arrays are ordered") < s.index("push more items")


def test_slice_respects_the_budget_but_keeps_the_top_chunk():
    s = decompose.slice_material(TRANSCRIPT, _c("Arrays", components=["push"]), max_chars=20)
    assert "Arrays are ordered collections" in s     # the top chunk is always kept …
    assert "push more items" not in s                # … but the budget stops the next one


def test_no_keyword_match_falls_back_to_the_head():
    s = decompose.slice_material(TRANSCRIPT, _c("Photosynthesis"), max_chars=40)
    assert s == TRANSCRIPT[:40]


def test_module_imports_and_selects_add_tools_only():
    assert decompose._ADD_SPECS and all(s["name"].startswith("add_") for s in decompose._ADD_SPECS)


# ------------------------------------------------ sub-splitting an oversized span (no truncation)

def test_material_chunks_single_when_under_budget():
    assert decompose._material_chunks("short text", 1000) == ["short text"]


def test_material_chunks_splits_oversized_on_paragraph_boundaries_losing_nothing():
    paras = [f"paragraph number {i} " * 8 for i in range(6)]     # ~150 chars each
    material = "\n\n".join(paras)
    chunks = decompose._material_chunks(material, budget=400)
    assert len(chunks) > 1                                        # it split
    assert all(len(c) <= 400 for c in chunks)                    # each within the measured budget
    joined = "\n\n".join(chunks)
    for p in paras:
        assert p.strip() in joined                               # nothing dropped (unlike a cap)


# ------------------------------------------------ pass-error tally (the timeout-tracking signal)

def test_run_pass_tallies_errors_into_stats(capsys):
    from coursekit.generate.page import page as P

    class _Boom:                                     # a provider that times out on every call
        def chat_with_tools(self, **_):
            raise TimeoutError("model call timed out")

    P.reset()
    P.init("p", None)
    stats: dict = {}
    added = decompose._run_pass(_Boom(), "m", "sys", "user", stats=stats)
    assert added == 0                                # nothing committed
    assert stats["errors"] == 1                      # …but the error is counted (not swallowed)
    assert stats["error_types"] == ["TimeoutError"]  # …and typed, so timeouts are visible


# ------------------------------------------------ the sliding coherence window (prev/next by name+gist)

def test_neighbour_window_middle_names_both_sides():
    cs = [_c("Loops", gist="repeat"), _c("Nested loops", gist="grids"), _c("map", gist="scale")]
    ctx = decompose._neighbour_context(cs, 1)
    assert "follows: Loops — repeat" in ctx           # the previous concept, by name + gist
    assert "leads into: map — scale" in ctx           # the next concept
    assert 'teach ONLY "Nested loops"' in ctx          # but only the current one


def test_neighbour_window_edges_point_at_opening_and_close():
    cs = [_c("Loops"), _c("Nested loops"), _c("map")]
    first = decompose._neighbour_context(cs, 0)
    last = decompose._neighbour_context(cs, 2)
    assert "the page's opening" in first              # first concept has no prior concept
    assert "the closing summary" in last              # last concept has no following concept


def test_neighbour_window_carries_only_name_when_no_gist():
    cs = [_c("Loops"), _c("Arrays")]
    assert "leads into: Arrays." in decompose._neighbour_context(cs, 0)   # name only, no " — "
