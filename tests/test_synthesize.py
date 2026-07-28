"""Offline tests for the synthetic-question generator. No model: every assertion is deterministic.

These prove the generator's contract — that each labelled case is genuinely the flaw its label says,
that the label never leaks to the critic, and that generation is reproducible — so the statistics a
later harness builds on it rest on solid data.
"""

import json

import pytest

from coursekit.generate.quiz.bank import Bank
from coursekit.generate.quiz.evaluate import _format_question
from coursekit.generate.quiz.synthesize import (
    DOMAINS,
    FLAWS,
    _garble,
    synthesize_all,
    synthesize_domain,
    write_fixtures,
)


def _ordered(ds):
    """The (group, expected) pairs in insertion order — seeds' four cases each, then out-of-scope."""
    return [(g, ds.expected[gid]) for gid, g in ds.bank.groups.items()]


# ---- structure & counts ---------------------------------------------------

def test_every_domain_has_the_expected_case_shape():
    for spec in DOMAINS:
        ds = synthesize_domain(spec)
        assert len(ds.bank.groups) == 4 * len(spec.seeds) + len(spec.out_of_scope)
        # expected covers exactly the bank's groups
        assert set(ds.expected) == set(ds.bank.groups)


def test_flaw_tally_across_all_domains():
    tally = {"PASS": 0, **{f: 0 for f in FLAWS}}
    for ds in synthesize_all().values():
        for exp in ds.expected.values():
            tally["PASS" if exp["verdict"] == "PASS" else exp["flaw"]] += 1
    # 4 domains × 4 seeds × {1 sound + 1 wrong + 1 missing + 1 garbled}, plus 2 out-of-scope each.
    assert tally == {"PASS": 16, "wrong-answer": 16, "missing-context": 16,
                     "garbled-syntax": 16, "out-of-scope": 8}


# ---- each flaw is genuinely its label -------------------------------------

def test_each_seed_yields_sound_plus_three_faithful_flaws():
    for spec in DOMAINS:
        ds = synthesize_domain(spec)
        pairs = _ordered(ds)
        i = 0
        for seed in spec.seeds:
            (sound, se), (wrong, we), (miss, me), (garb, ge) = pairs[i:i + 4]
            i += 4

            # sound: verbatim seed, marked correct, no flaw
            assert se == {"verdict": "PASS", "flaw": None}
            sv = sound.variants["A"]
            assert sv.question_text == seed.text and sv.correct_index == seed.correct

            # wrong-answer: same stem, the mark moved off the correct option
            assert we == {"verdict": "FLAG", "flaw": "wrong-answer"}
            wv = wrong.variants["A"]
            assert wv.question_text == seed.text
            assert wv.correct_index != seed.correct

            # missing-context: the stripped stem, which differs from the answerable one
            assert me == {"verdict": "FLAG", "flaw": "missing-context"}
            mv = miss.variants["A"]
            assert mv.question_text == seed.stripped != seed.text

            # garbled-syntax: the token corrupted, and the intact token no longer present
            assert ge == {"verdict": "FLAG", "flaw": "garbled-syntax"}
            gv = garb.variants["A"]
            assert gv.question_text != seed.text
            assert _garble(seed.garble) in gv.question_text
            assert seed.garble not in gv.question_text

        for oos in spec.out_of_scope:
            g, exp = pairs[i]
            i += 1
            assert exp == {"verdict": "FLAG", "flaw": "out-of-scope"}
            ov = g.variants["A"]
            assert ov.question_text == oos.text and ov.correct_index == oos.correct
        assert i == len(pairs)


def test_wrong_answer_marks_a_real_distractor():
    """The moved mark must land on an option that is not the sound answer's text (single-answer
    seeds, so any shift is genuinely wrong)."""
    for spec in DOMAINS:
        ds = synthesize_domain(spec)
        pairs = _ordered(ds)
        for seed, base in zip(spec.seeds, range(0, len(spec.seeds) * 4, 4)):
            sound = pairs[base][0].variants["A"]
            wrong = pairs[base + 1][0].variants["A"]
            assert sound.options[wrong.correct_index] != sound.options[sound.correct_index]


# ---- the label must never reach the critic --------------------------------

def test_flaw_label_never_leaks_into_what_the_critic_sees():
    for ds in synthesize_all().values():
        for g in ds.bank.groups.values():
            shown = _format_question(g.variants["A"])
            for flaw in FLAWS:
                assert flaw not in shown


# ---- determinism & serialisation ------------------------------------------

def test_generation_is_deterministic():
    a = {n: ds.bank.model_dump() for n, ds in synthesize_all().items()}
    b = {n: ds.bank.model_dump() for n, ds in synthesize_all().items()}
    assert a == b


def test_every_bank_round_trips_through_pydantic():
    for ds in synthesize_all().values():
        blob = json.dumps(ds.bank.model_dump())
        reloaded = Bank.model_validate_json(blob)
        assert reloaded.model_dump() == ds.bank.model_dump()


# ---- the corruption primitive ---------------------------------------------

def test_garble_unbalances_brackets_and_drops_separators():
    assert _garble("for (let i = 0; i < 5; i++)") == "for (let i = 0 i < 5 i++"
    assert _garble("circle(i * 40, 50, 20)") == "circle(i * 40, 50, 20"
    assert _garble("(a selectively permeable one)") == "(a selectively permeable one"


def test_garble_wraps_a_plain_token_in_broken_math():
    assert _garble("f/2.8") == "$f/2.8\\"


# ---- the on-disk dump ------------------------------------------------------

def test_write_fixtures_emits_parseable_banks(tmp_path):
    paths = write_fixtures(tmp_path)
    assert paths
    banks = [p for p in paths if p.name == "bank.json"]
    assert len(banks) == len(DOMAINS)
    for p in banks:
        Bank.model_validate_json(p.read_text(encoding="utf-8"))  # must parse
    for p in [p for p in paths if p.name == "expected.json"]:
        exp = json.loads(p.read_text(encoding="utf-8"))
        assert all(set(v) == {"verdict", "flaw"} for v in exp.values())
