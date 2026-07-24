import json
import pytest
from coursekit.generate.quiz import bank as bankmod
from coursekit.generate.quiz.bank import (MAVariant, MatchVariant, MCVariant, NumVariant, Pair, SAVariant,
                  TFVariant, ValidationError)


@pytest.fixture(autouse=True)
def clean():
    bankmod.reset()


def _mc(label, correct=0, group="c1", **kw):
    kw.setdefault("options", ["alpha", "beta", "gamma", "delta"])
    kw.setdefault("variant_summary", f"Angle {label}")
    return MCVariant(group_id=group, label=label,
                     question_text=f"Question {label} about the concept?",
                     correct_index=correct, **kw)


# ------------------------------------------------- the overwrite mechanism

class TestOverwrite:
    """The reason this module exists: a revision must replace, never accumulate."""

    def test_same_key_replaces_rather_than_appends(self):
        bankmod.create_group("c1", "Loops", "multiple_choice")
        bankmod.put_variant(_mc("A", 0, options=["first draft", "b", "c", "d"]))
        bankmod.put_variant(_mc("A", 0, options=["revised", "b", "c", "d"]))
        g = bankmod.get().groups["c1"]
        assert len(g.variants) == 1
        assert g.variants["A"].options[0] == "revised"

    def test_ack_says_replaced_on_a_rewrite(self):
        bankmod.create_group("c1", "Loops", "multiple_choice")
        assert "stored" in bankmod.put_variant(_mc("A", 0))
        assert "replaced" in bankmod.put_variant(_mc("A", 0))

    def test_rewriting_a_variant_may_keep_its_own_position(self):
        # The position check must exclude the variant being replaced, or a no-op
        # rewrite would collide with itself.
        bankmod.create_group("c1", "Loops", "multiple_choice")
        bankmod.put_variant(_mc("A", 0))
        bankmod.put_variant(_mc("B", 1))
        out = bankmod.put_variant(_mc("B", 1, options=["w", "x", "y", "z"]))
        assert not out.startswith("ERROR")

    def test_the_observed_failure_cannot_happen(self):
        # output/quiz_20260716_141609.txt has Variation A four times. Four commits of
        # A can only ever leave one A.
        bankmod.create_group("c1", "Loops", "multiple_choice")
        for draft in ["first", "second", "third", "final"]:
            bankmod.put_variant(_mc("A", 0, options=[draft, "b", "c", "d"]))
        g = bankmod.get().groups["c1"]
        assert list(g.variants) == ["A"]
        assert g.variants["A"].options[0] == "final"


# ------------------------------------------------------------- guardrails

class TestGuardrails:
    def test_variant_before_group_is_refused_with_a_next_step(self):
        out = bankmod.put_variant(_mc("A"))
        assert out.startswith("ERROR")
        assert "create_question_group" in out

    def test_wrong_tool_for_group_type_names_the_right_tool(self):
        bankmod.create_group("c2", "Facts", "true_false")
        out = bankmod.put_variant(_mc("A", group="c2"))
        assert "add_true_false_variant" in out

    def test_duplicate_options_rejected(self):
        with pytest.raises(ValidationError, match="distinct"):
            _mc("A", options=["same", "same", "b", "c"])

    def test_duplicate_options_are_case_insensitive(self):
        with pytest.raises(ValidationError, match="distinct"):
            _mc("A", options=["Same", "same ", "b", "c"])

    def test_correct_index_out_of_range(self):
        with pytest.raises(ValidationError, match="out of range"):
            _mc("A", correct=9)

    def test_self_correction_note_in_an_option_is_rejected(self):
        # The literal artefact from the observed run.
        with pytest.raises(ValidationError, match="self-correction"):
            _mc("A", options=["Initialization, Condition, and Incrementer",
                              "Initialization, Condition, and Incrementer "
                              "(Wait, this is the same as A)", "c", "d"])

    def test_legitimate_parenthetical_is_not_rejected(self):
        # The guardrail must not eat real question text.
        v = _mc("A", options=["A note (see line 3)", "b (optional)", "c", "d"])
        assert v.options[0] == "A note (see line 3)"

    def test_markdown_with_unbackticked_angle_is_rejected(self):
        with pytest.raises(ValidationError, match="backticks"):
            MCVariant(group_id="c1", label="A", text_format="markdown",
                      question_text="What does x < 10 do in the loop?",
                      variant_summary="Condition", options=["a", "b"], correct_index=0)

    def test_markdown_with_backticked_angle_is_fine(self):
        v = MCVariant(group_id="c1", label="A", text_format="markdown",
                      question_text="What does `x < 10` do in the loop?",
                      variant_summary="Condition", options=["`x < 400`", "`x <= 400`"],
                      correct_index=0)
        assert v.text_format == "markdown"

    def test_plain_format_allows_angles(self):
        v = _mc("A", options=["x < 10", "b", "c", "d"])
        assert v.options[0] == "x < 10"

    def test_matching_rejects_arrow_on_the_left_only(self):
        with pytest.raises(ValidationError, match="left side"):
            Pair(left="a -> b", right="c")
        assert Pair(left="a", right="b -> c").right == "b -> c"

    def test_matching_needs_two_pairs(self):
        with pytest.raises(ValidationError):
            MatchVariant(group_id="c1", label="A", question_text="Match these things.",
                         variant_summary="Pairs", pairs=[Pair(left="a", right="b")])

    def test_matching_has_no_feedback_field(self):
        # GIFT matching supports neither feedback nor weights; prevent at the schema.
        with pytest.raises(ValidationError):
            MatchVariant(group_id="c1", label="A", question_text="Match these things.",
                         variant_summary="Pairs",
                         pairs=[Pair(left="a", right="b"), Pair(left="c", right="d")],
                         feedback="nope")

    def test_label_must_be_a_single_capital(self):
        with pytest.raises(ValidationError):
            _mc("a")
        with pytest.raises(ValidationError):
            _mc("AA")

    def test_negative_tolerance_rejected(self):
        with pytest.raises(ValidationError):
            NumVariant(group_id="c1", label="A", question_text="How many?",
                       variant_summary="Count", answer=1, tolerance=-1)


# ------------------------------------------- correct-answer position steering

class TestPositions:
    def test_reused_position_is_rejected_and_lists_free_ones(self):
        bankmod.create_group("c1", "Loops", "multiple_choice")
        bankmod.put_variant(_mc("A", 0))
        out = bankmod.put_variant(_mc("B", 0))
        assert out.startswith("ERROR")
        assert "variant A already" in out
        assert "[1, 2, 3]" in out

    def test_rejected_variant_does_not_half_write(self):
        bankmod.create_group("c1", "Loops", "multiple_choice")
        bankmod.put_variant(_mc("A", 0))
        bankmod.put_variant(_mc("B", 0))
        assert list(bankmod.get().groups["c1"].variants) == ["A"]

    def test_ack_steers_toward_the_free_positions(self):
        bankmod.create_group("c1", "Loops", "multiple_choice")
        bankmod.put_variant(_mc("A", 0))
        out = bankmod.put_variant(_mc("B", 1))
        assert "positions still free: [2, 3]" in out

    def test_four_distinct_positions_all_accepted(self):
        bankmod.create_group("c1", "Loops", "multiple_choice")
        for i, lbl in enumerate("ABCD"):
            assert not bankmod.put_variant(_mc(lbl, i)).startswith("ERROR")
        assert bankmod.validate_final() == []

    def test_position_rule_not_applied_to_true_false(self):
        # Incoherent for a type with no answer positions.
        bankmod.create_group("c2", "Facts", "true_false")
        for lbl, ans in zip("ABCD", [True, False, True, False]):
            out = bankmod.put_variant(TFVariant(group_id="c2", label=lbl,
                                                question_text=f"Statement {lbl} is true?",
                                                variant_summary=f"Claim {lbl}",
                                                correct_answer=ans))
            assert not out.startswith("ERROR")
        assert bankmod.validate_final() == []

    def test_position_rule_relaxes_when_variants_exceed_options(self):
        # Five variants cannot occupy four distinct positions; the rule must not
        # become unsatisfiable.
        bankmod.create_group("c1", "Loops", "multiple_choice")
        for i, lbl in enumerate("ABCD"):
            bankmod.put_variant(_mc(lbl, i))
        assert not bankmod.put_variant(_mc("E", 0)).startswith("ERROR")


# --------------------------------------------------------------- finalize

class TestFinalize:
    def test_all_true_true_false_group_is_flagged(self):
        bankmod.create_group("c2", "Facts", "true_false")
        for lbl in "AB":
            bankmod.put_variant(TFVariant(group_id="c2", label=lbl,
                                          question_text=f"Statement {lbl} is true?",
                                          variant_summary=f"Claim {lbl}",
                                          correct_answer=True))
        assert any("at least one of each" in p for p in bankmod.validate_final())

    def test_empty_group_is_flagged(self):
        bankmod.create_group("c1", "Loops", "multiple_choice")
        assert any("no variants" in p for p in bankmod.validate_final())

    def test_finalize_refuses_and_does_not_set_the_flag(self):
        bankmod.create_group("c1", "Loops", "multiple_choice")
        out = bankmod.finalize()
        assert out.startswith("ERROR")
        assert not bankmod.is_finalized()

    def test_finalize_succeeds_on_a_valid_bank(self):
        bankmod.create_group("c1", "Loops", "multiple_choice")
        for i, lbl in enumerate("ABCD"):
            bankmod.put_variant(_mc(lbl, i))
        assert bankmod.finalize().startswith("OK")
        assert bankmod.is_finalized()

    def test_group_cannot_change_type_once_it_has_variants(self):
        bankmod.create_group("c1", "Loops", "multiple_choice")
        bankmod.put_variant(_mc("A", 0))
        assert bankmod.create_group("c1", "Loops", "true_false").startswith("ERROR")


# --------------------------------------------------------------- autosave

def test_autosave_writes_after_every_put(tmp_path):
    bankmod.init("run1", tmp_path)
    bankmod.create_group("c1", "Loops", "multiple_choice")
    bankmod.put_variant(_mc("A", 0))
    saved = json.loads((tmp_path / "bank.json").read_text())
    assert saved["groups"]["c1"]["variants"]["A"]["correct_index"] == 0

    bankmod.put_variant(_mc("B", 1))
    saved = json.loads((tmp_path / "bank.json").read_text())
    assert sorted(saved["groups"]["c1"]["variants"]) == ["A", "B"]


def test_finalize_writes_all_four_artifacts(tmp_path):
    bankmod.init("run1", tmp_path)
    bankmod.create_group("c1", "Loops", "multiple_choice")
    for i, lbl in enumerate("ABCD"):
        bankmod.put_variant(_mc(lbl, i))
    out = bankmod.finalize(seed=42)
    assert out.startswith("OK")
    for name in ["bank.json", "quiz.json", "bank.gift", "quiz_42.gift"]:
        assert (tmp_path / name).exists(), name
    quiz = json.loads((tmp_path / "quiz.json").read_text())
    assert quiz["seed"] == 42
    assert quiz["groups"] == [{"group_id": "c1", "pick_count": 1, "points": 1}]


def test_bank_json_round_trips_through_the_model(tmp_path):
    bankmod.init("run1", tmp_path)
    bankmod.create_group("c1", "Loops", "multiple_choice")
    bankmod.create_group("c5", "Matching", "matching")
    bankmod.put_variant(_mc("A", 0))
    bankmod.put_variant(MatchVariant(group_id="c5", label="A",
                                     question_text="Match the pairs up.",
                                     variant_summary="Pairs",
                                     pairs=[Pair(left="a", right="b"),
                                            Pair(left="c", right="d")]))
    reloaded = bankmod.Bank.model_validate_json((tmp_path / "bank.json").read_text())
    assert reloaded.groups["c1"].variants["A"].kind == "multiple_choice"
    assert reloaded.groups["c5"].variants["A"].kind == "matching"


# ------------------------------------------------------- variant summaries

class TestVariantSummary:
    def test_duplicate_summary_in_a_group_is_rejected(self):
        # Two variants testing the same angle is the failure the bank exists to prevent.
        bankmod.create_group("c1", "Loops", "multiple_choice")
        bankmod.put_variant(_mc("A", 0, variant_summary="Purpose of the condition"))
        out = bankmod.put_variant(_mc("B", 1, variant_summary="purpose of the CONDITION"))
        assert out.startswith("ERROR")
        assert "variant A already has the summary" in out

    def test_duplicate_summary_does_not_block_a_rewrite(self):
        bankmod.create_group("c1", "Loops", "multiple_choice")
        bankmod.put_variant(_mc("A", 0, variant_summary="Purpose of the condition"))
        out = bankmod.put_variant(_mc("A", 0, variant_summary="Purpose of the condition"))
        assert "replaced" in out

    def test_summary_may_not_be_the_question_text(self):
        with pytest.raises(ValidationError, match="must not repeat the question text"):
            MCVariant(group_id="c1", label="A",
                      question_text="What does the incrementer do?",
                      variant_summary="What does the incrementer do?",
                      options=["a", "b"], correct_index=0)

    def test_pasted_stem_is_rejected_by_length(self):
        with pytest.raises(ValidationError):
            _mc("A", variant_summary="What are the three components required within the "
                                     "parentheses of a for loop, and in what order?")

    def test_summary_whitespace_is_collapsed(self):
        assert _mc("A", variant_summary="  Purpose  of\n the condition ").variant_summary == \
            "Purpose of the condition"


# -------------------------------------------------------- multiple answer

class TestMultipleAnswer:
    def _ma(self, label="A", correct=(0, 2), group="c7", **kw):
        kw.setdefault("options", ["right one", "wrong one", "right two", "wrong two"])
        kw.setdefault("variant_summary", f"Select all {label}")
        return MAVariant(group_id=group, label=label,
                         question_text=f"Which are true in set {label}? Select all that apply.",
                         correct_indices=list(correct), **kw)

    def test_stores_through_the_bank(self):
        bankmod.create_group("c7", "Loop facts", "multiple_answer")
        assert not bankmod.put_variant(self._ma()).startswith("ERROR")
        assert bankmod.get().groups["c7"].variants["A"].correct_indices == [0, 2]

    def test_one_correct_answer_is_refused(self):
        # That is a multiple_choice question; the message has to say so.
        with pytest.raises(ValidationError):
            self._ma(correct=(0,))

    def test_all_options_correct_is_refused(self):
        with pytest.raises(ValidationError, match="at least one option must be wrong"):
            self._ma(correct=(0, 1, 2, 3))

    def test_repeated_index_is_refused(self):
        with pytest.raises(ValidationError, match="must not repeat"):
            self._ma(correct=(0, 0))

    def test_out_of_range_index_is_refused(self):
        with pytest.raises(ValidationError, match="out of range"):
            self._ma(correct=(0, 9))

    def test_wrong_tool_for_a_multiple_answer_group(self):
        bankmod.create_group("c7", "Loop facts", "multiple_answer")
        out = bankmod.put_variant(_mc("A", 0, group="c7"))
        assert "add_multiple_answer_variant" in out

    def test_position_rule_does_not_apply(self):
        # There is no single correct position, so the rule is incoherent here.
        bankmod.create_group("c7", "Loop facts", "multiple_answer")
        for lbl in "ABCD":
            assert not bankmod.put_variant(self._ma(label=lbl, correct=(0, 2))).startswith("ERROR")
        assert bankmod.validate_final() == []

    def test_option_starting_with_a_weight_is_refused(self):
        # GIFT would read a leading %50% as an answer weight and eat it.
        with pytest.raises(ValidationError, match="answer weight"):
            self._ma(options=["%50% of the time", "b", "c", "d"])
