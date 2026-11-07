"""ASMT-21: a quiz's question order is the program's default (as written, open questions last) until an
instructor sets one, and then it is theirs — kept through every later finalize, followed by every
emitter, and the only order an introduction describes. Also: one attempts value, not two literals."""

import json

import pytest

from coursekit.emit import qti
from coursekit.generate.quiz import bank as bankmod
from coursekit.generate.quiz.bank import MCVariant, OpenResponseVariant
from coursekit.outcomes import CoursekitError

EU = "enduring_understanding"


def _mc(group, label, correct):
    return MCVariant(group_id=group, label=label, question_text=f"Which is right in {group}{label}?",
                     variant_summary=f"angle {label}", options=["a", "b", "c", "d"], correct_index=correct)


def _draft(out_dir, groups, *, eu=True, staged=False):
    """A bank written in `groups` order (each a four-variant MC group), then the EU question, as a run makes it."""
    d = bankmod.BankDraft.new("run", out_dir, title="Week 7") if staged else \
        bankmod.BankDraft.adopt(bankmod.Bank(run_id="run", title="Week 7"), out_dir)
    for gid in groups:
        d.create_group(gid, f"Concept {gid}", "multiple_choice")
        for i, lbl in enumerate("ABCD"):
            d.put_variant(_mc(gid, lbl, i))
    if eu:
        d.create_group(EU, "Enduring Understanding", "open_response")
        d.put_variant(OpenResponseVariant(group_id=EU, label="A", variant_summary="EU transfer task",
                                          question_text="Apply the big idea to a new sketch.",
                                          rubric_criteria=["Names the structure"]))
    return d


def _quiz(out_dir):
    return json.loads((out_dir / "quiz.json").read_text())


def _order(out_dir):
    return [g["group_id"] for g in _quiz(out_dir)["groups"]]


def test_the_default_is_as_written_with_open_questions_last_and_the_draw_unchanged(tmp_path):
    # the bug: groups were sorted by id, so 'enduring_understanding' opened the quiz and g10 came before g2
    ids = [f"g{i}" for i in range(1, 12)]
    d = _draft(tmp_path, ids, staged=True)
    assert d.finalize(seed=7).startswith("OK")
    assert _order(tmp_path) == ids + [EU] and _quiz(tmp_path)["order_from"] == "default"
    cats = [ln for ln in (tmp_path / "bank.gift").read_text().split("\n") if ln.startswith("// Concept")]
    assert cats == [f"// Concept {g}" for g in ids]          # the Moodle bank too: g2 before g10
    # the variant each group draws is what the old (sorted) draw chose — reordering moves, never redraws
    rng, old = __import__("random").Random(7), {}
    for gid in sorted(d.bank.groups):
        old[gid] = rng.sample(sorted(d.bank.groups[gid].variants), 1)
    assert _quiz(tmp_path)["picks"] == old


def test_an_instructors_order_survives_a_later_finalize_with_new_groups_at_the_end(tmp_path):
    d = _draft(tmp_path, ["g1", "g2", "g3"], eu=False)
    d.finalize(seed=7)
    bankmod.set_order(tmp_path, ["g3", "g1", "g2"])
    quiz = _quiz(tmp_path)
    quiz["groups"][0]["points"] = 2                         # an instructor's points, kept too
    (tmp_path / "quiz.json").write_text(json.dumps(quiz))

    again = bankmod.BankDraft.adopt(bankmod.Bank.model_validate_json((tmp_path / "bank.json").read_text()),
                                    tmp_path)               # e.g. the EU pass, or a fix, editing in place
    again.create_group(EU, "Enduring Understanding", "open_response")
    again.put_variant(OpenResponseVariant(group_id=EU, label="A", variant_summary="EU transfer task",
                                          question_text="Apply the big idea to a new sketch."))
    again.finalize(seed=7)
    assert _order(tmp_path) == ["g3", "g1", "g2", EU] and _quiz(tmp_path)["order_from"] == "instructor"
    assert _quiz(tmp_path)["groups"][0] == {"group_id": "g3", "pick_count": 1, "points": 2}


def test_a_quiz_from_before_this_gets_the_default_unless_someone_edited_it(tmp_path):
    for i, (old_order, expect) in enumerate([([EU, "g1", "g2"], ["g1", "g2", EU]),        # the old sort
                                             (["g2", EU, "g1"], ["g2", EU, "g1"])]):      # a hand edit
        out = tmp_path / str(i)
        d = _draft(out, ["g1", "g2"])
        d.finalize(seed=7)
        legacy = _quiz(out)
        del legacy["order_from"]
        legacy["groups"] = [{"group_id": g, "pick_count": 1, "points": 1} for g in old_order]
        (out / "quiz.json").write_text(json.dumps(legacy))
        d.finalize(seed=7)
        assert _order(out) == expect


def test_a_fresh_run_ignores_the_old_quizs_order(tmp_path):
    # a regenerated quiz's g1 is new content: an order chosen for the old g1 must not land on it
    _draft(tmp_path, ["g1", "g2"]).finalize(seed=7)
    bankmod.set_order(tmp_path, [EU, "g2", "g1"])
    _draft(tmp_path, ["g1", "g2"], staged=True).finalize(seed=7)
    assert _order(tmp_path) == ["g1", "g2", EU] and _quiz(tmp_path)["order_from"] == "default"


def test_set_order_checks_the_list_and_every_emitter_follows_it(tmp_path):
    _draft(tmp_path, ["g1", "g2"]).finalize(seed=7)
    before = (tmp_path / "quiz.json").read_text()
    for bad in (["g1", "g2"], ["g1", "g2", EU, "g1"], ["g1", "g2", "g9"]):
        with pytest.raises(CoursekitError) as ei:
            bankmod.set_order(tmp_path, bad)
        assert ei.value.code == "quiz.order_invalid"
    assert (tmp_path / "quiz.json").read_text() == before    # a bad list changes nothing

    bankmod.set_order(tmp_path, [EU, "g2", "g1"])
    for gift_file in ("quiz_7.gift", "bank.gift"):          # the paper, and the whole bank for Moodle
        text = (tmp_path / gift_file).read_text()
        assert text.index("Apply the big idea") < text.index("in g2") < text.index("in g1"), gift_file
    b = bankmod.Bank.model_validate_json((tmp_path / "bank.json").read_text())
    xml = qti.emit_assessment(b, qti._quiz_for(b, tmp_path / "quiz.json"))   # what the export packages
    assert xml.index("Enduring Understanding") < xml.index("Concept g2") < xml.index("Concept g1")


def test_the_default_intro_says_where_the_open_question_is(tmp_path):
    d = _draft(tmp_path, ["g1", "g2"])
    d.finalize(seed=7)
    desc = lambda: qti.emit_assessment_meta(d.bank, _quiz(tmp_path))
    assert "2 questions, then one open question to answer in writing." in desc()
    bankmod.set_order(tmp_path, [EU, "g1", "g2"])
    assert "one open question to answer in writing first, then 2 questions." in desc()
    bankmod.set_order(tmp_path, ["g1", EU, "g2"])
    assert "2 questions, with one open question to answer in writing partway through." in desc()


def test_a_hand_edit_that_lists_a_group_twice_is_refused_at_emit(tmp_path):
    d = _draft(tmp_path, ["g1"])
    d.finalize(seed=7)
    quiz = _quiz(tmp_path)
    quiz["groups"].append(dict(quiz["groups"][0]))
    assert "more than once" in qti._quiz_bank_mismatch(d.bank, quiz)


def test_the_attempts_sentence_and_the_attempts_settings_are_one_value(tmp_path, monkeypatch):
    d = _draft(tmp_path, ["g1"])
    d.finalize(seed=7)
    monkeypatch.setattr(qti, "ALLOWED_ATTEMPTS", 3)
    meta, items = qti.emit_assessment_meta(d.bank, _quiz(tmp_path)), qti.emit_assessment(d.bank, _quiz(tmp_path))
    assert "<allowed_attempts>3</allowed_attempts>" in meta and "3 attempts." in meta
    assert "<fieldentry>3</fieldentry>" in items.split("cc_maxattempts")[1][:60]


def test_the_intro_is_told_the_instructors_order_not_the_default(tmp_path):
    from coursekit.generate.quiz import intro

    class _Model:
        def chat(self, *, messages, **kw):
            self.asked = messages[1]["content"]
            return "Let's see how the ideas are landing."

    _draft(tmp_path, ["g1", "g2"]).finalize(seed=7)
    bankmod.set_order(tmp_path, [EU, "g1", "g2"])
    draft = bankmod.BankDraft.adopt(bankmod.Bank.model_validate_json((tmp_path / "bank.json").read_text()),
                                    tmp_path)                # what the intro script does
    model = _Model()
    assert intro.write_intro(draft, model, "m", "")
    assert model.asked.endswith("one open question to answer in writing first, then short questions")
