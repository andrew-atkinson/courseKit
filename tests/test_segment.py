"""Boundary-correct segmentation — the deterministic half (the model marks boundaries; the partition
that turns those marks into per-concept material is pure and pinned here)."""

from coursekit.generate.page import segment as seg
from coursekit.generate.page.concept_map import Concept, ConceptMap


def _cm(*names):
    return ConceptMap(week="3", concepts=[Concept(name=n) for n in names])


# ------------------------------------------------------------------- chunking
def test_chunk_merges_small_paragraphs_forward():
    text = "# Heading\n\nshort one.\n\n" + ("x" * 250) + "\n\nlast bit."
    chunks = seg.chunk_text(text, min_len=200)
    assert len(chunks) == 1                                   # everything merges under the min length
    assert "Heading" in chunks[0] and "last bit." in chunks[0]


def test_chunk_splits_once_past_the_budget():
    a, b = "a" * 250, "b" * 250
    chunks = seg.chunk_text(f"{a}\n\n{b}", min_len=200)
    assert chunks == [a, b]                                   # each already exceeds the budget


# ------------------------------------------------------------------- boundary parsing (robust)
def test_parse_reads_a_json_array_one_based_to_zero_based():
    assert seg.parse_boundaries("[1, 4, 9]", 3, 12) == [0, 3, 8]   # 1-based → 0-based, first forced 0


def test_parse_forces_monotonic_and_clamps_and_first_zero():
    # out-of-order + out-of-range are repaired into a valid non-decreasing partition
    assert seg.parse_boundaries("[5, 2, 99]", 3, 6) == [0, 4, 5]


def test_parse_pads_when_the_model_gives_too_few():
    assert seg.parse_boundaries("[1, 3]", 4, 10) == [0, 2, 2, 2]   # missing 4th → repeats last


def test_parse_falls_back_to_bare_integers():
    assert seg.parse_boundaries("start 1, then 4, then 9", 3, 12) == [0, 3, 8]


# ------------------------------------------------------------------- partition into material
def test_materials_partition_is_contiguous_and_verbatim():
    chunks = ["AAAA", "BBBB", "CCCC", "DDDD"]
    mats = seg.materials_from_boundaries(chunks, [0, 2, 3], _cm("one", "two", "three"))
    assert mats["one"] == "AAAA\n\nBBBB"     # its span, verbatim
    assert mats["two"] == "CCCC"
    assert mats["three"] == "DDDD"            # last runs to the end


def test_empty_span_is_omitted_so_generation_can_fall_back():
    chunks = ["AAAA", "BBBB"]
    mats = seg.materials_from_boundaries(chunks, [0, 0], _cm("one", "two"))
    # both marked at chunk 0 → the first concept's span is empty and omitted (it falls back to the
    # slicer at generation time), and the material lands on the other concept
    assert "one" not in mats
    assert mats["two"] == "AAAA\n\nBBBB"


def test_roundtrip_partition_covers_every_chunk():
    chunks = [f"chunk{i}" for i in range(6)]
    starts = seg.parse_boundaries("[1, 3, 5]", 3, len(chunks))
    mats = seg.materials_from_boundaries(chunks, starts, _cm("a", "b", "c"))
    joined = "\n\n".join(mats[n] for n in ("a", "b", "c"))
    assert joined == "\n\n".join(chunks)      # nothing dropped, nothing duplicated
