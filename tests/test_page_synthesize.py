"""Offline tests for the labelled page-section generator. No model: all deterministic."""

from coursekit.generate.page.evaluate import _format_block
from coursekit.generate.page.synthesize import (
    DOMAINS,
    HARD_DOMAINS,
    HARD_FLAWS,
    PAGE_FLAWS,
    synthesize_all_hard_pages,
    synthesize_all_pages,
    synthesize_hard_page_domain,
    synthesize_page_domain,
)
from coursekit.generate.quiz.synthesize import _garble


def test_each_domain_has_the_expected_case_shape():
    for spec in DOMAINS:
        ds = synthesize_page_domain(spec)
        # 3 cases per fact (sound + contradiction + garbled) + one per out-of-scope claim
        assert len(ds.page.blocks) == 3 * len(spec.facts) + len(spec.out_of_scope)
        assert set(ds.expected) == set(ds.page.blocks)


def test_flaw_tally_across_all_domains():
    tally = {"PASS": 0, **{f: 0 for f in PAGE_FLAWS}}
    for ds in synthesize_all_pages().values():
        for exp in ds.expected.values():
            tally["PASS" if exp["verdict"] == "PASS" else exp["flaw"]] += 1
    # 4 domains × (3 facts → 3 sound/contradiction/garbled) + 2 out-of-scope each
    assert tally == {"PASS": 12, "contradiction": 12, "garbled": 12, "out-of-scope": 8}


def test_cases_are_faithful_to_their_labels():
    for spec in DOMAINS:
        ds = synthesize_page_domain(spec)
        blocks = list(ds.page.blocks.values())
        i = 0
        for fact in spec.facts:
            sound, contra, garb = blocks[i:i + 3]
            i += 3
            assert sound.text == fact.true
            assert contra.text == fact.false
            # garbled: the intact span is gone, the corruption is present
            assert fact.garble not in garb.text
            assert _garble(fact.garble) in garb.text
        for claim in spec.out_of_scope:
            assert blocks[i].text == claim
            i += 1
        assert i == len(blocks)


def test_flaw_label_never_leaks_into_what_the_critic_sees():
    for ds in synthesize_all_pages().values():
        for b in ds.page.blocks.values():
            shown = _format_block(b)
            for flaw in PAGE_FLAWS:
                assert flaw not in shown


def test_generation_is_deterministic():
    a = {n: ds.page.model_dump() for n, ds in synthesize_all_pages().items()}
    b = {n: ds.page.model_dump() for n, ds in synthesize_all_pages().items()}
    assert a == b


# ---- the HARD set (subtle flaws) ----

def test_hard_set_shape_and_labels():
    for spec in HARD_DOMAINS:
        ds = synthesize_hard_page_domain(spec)
        assert len(ds.page.blocks) == len(spec.cases)
        assert set(ds.expected) == set(ds.page.blocks)
        for c, b in zip(spec.cases, ds.page.blocks.values()):
            exp = ds.expected[b.block_id]
            assert b.text == c.text
            assert exp == {"verdict": "PASS" if c.flaw is None else "FLAG", "flaw": c.flaw}


def test_hard_set_uses_only_the_declared_flaws_and_has_sounds():
    flaws, sounds = set(), 0
    for ds in synthesize_all_hard_pages().values():
        for exp in ds.expected.values():
            if exp["flaw"] is None:
                sounds += 1
            else:
                flaws.add(exp["flaw"])
    assert flaws == set(HARD_FLAWS)     # near-miss + beyond-material, nothing stray
    assert sounds >= 4                  # sound sections present, to test false-flag under pressure
