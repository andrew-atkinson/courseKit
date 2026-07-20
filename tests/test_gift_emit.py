import pytest
from coursekit.generate.quiz import bank as bankmod
from coursekit.emit import gift
from coursekit.generate.quiz.bank import (Bank, Group, MAVariant, MatchVariant, MCVariant, NumVariant, Pair,
                  SAVariant, TFVariant)

# Every text field below is hostile: '=' is a GIFT control char and every code question
# in this project contains one.
HOSTILE = "for (let x = 0; x < 10; x++) {a: ~b} #c"


def _bank_with(*variants) -> Bank:
    b = Bank(run_id="t1", title="Test bank")
    for v in variants:
        g = b.groups.setdefault(
            v.group_id,
            Group(group_id=v.group_id, concept_title="Concept " + v.group_id,
                  question_type=v.kind),
        )
        g.variants[v.label] = v
    return b


def _blocks(text: str) -> list[str]:
    """Split emitted GIFT the way Moodle does: on blank lines."""
    return [b for b in text.split("\n\n") if b.strip()]


# ---------------------------------------------------------- type round-trip

def test_multiple_choice_round_trips():
    v = MCVariant(group_id="c1", label="A", variant_summary="Angle A c1", question_text=HOSTILE,
                  options=[HOSTILE + " one", "two = 2", "three ~ 3", "four {4}"],
                  correct_index=2)
    assert gift.detect_gift_type(gift.emit_variant(v)) == "multiple_choice"


def test_true_false_round_trips():
    v = TFVariant(group_id="c2", label="A", variant_summary="Angle A c2", question_text=HOSTILE, correct_answer=True)
    assert gift.detect_gift_type(gift.emit_variant(v)) == "true_false"


def test_true_false_false_round_trips():
    v = TFVariant(group_id="c2", label="B", variant_summary="Angle B c2", question_text=HOSTILE, correct_answer=False)
    src = gift.emit_variant(v)
    assert gift.detect_gift_type(src) == "true_false"
    assert "{FALSE}" in src


def test_short_answer_round_trips_with_hostile_text():
    # The trap: an unescaped '~' or '=' here would silently make this a multiple choice.
    v = SAVariant(group_id="c3", label="A", variant_summary="Angle A c3", question_text=HOSTILE,
                  accepted_answers=[HOSTILE, "~tilde", "{braces}"])
    assert gift.detect_gift_type(gift.emit_variant(v)) == "short_answer"


def test_short_answer_rejects_arrow_because_gift_cannot_express_it():
    # A short answer always carries '=', and '=' plus '->' means matching. '->' is not
    # escapable, so there is no encoding that survives: reject at the boundary instead
    # of emitting a question that silently imports as the wrong type.
    with pytest.raises(bankmod.ValidationError, match="matching question"):
        SAVariant(group_id="c3", label="B", variant_summary="Angle B c3", question_text="What is the arrow operator?",
                  accepted_answers=["a -> b"])


def test_short_answer_arrow_in_the_stem_is_fine():
    # Type detection reads only the brace contents, so an arrow outside them is harmless.
    v = SAVariant(group_id="c3", label="C", variant_summary="Angle C c3", question_text="What does a -> b evaluate to?",
                  accepted_answers=["a function"])
    assert gift.detect_gift_type(gift.emit_variant(v)) == "short_answer"


def test_numerical_round_trips():
    v = NumVariant(group_id="c4", label="A", variant_summary="Angle A c4", question_text=HOSTILE, answer=1822, tolerance=5)
    src = gift.emit_variant(v)
    assert gift.detect_gift_type(src) == "numerical"
    assert "{#1822:5}" in src


def test_numerical_zero_tolerance_omits_colon():
    v = NumVariant(group_id="c4", label="B", variant_summary="Angle B c4", question_text="How many?", answer=4)
    src = gift.emit_variant(v)
    assert "{#4}" in src
    assert gift.detect_gift_type(src) == "numerical"


def test_numerical_float_tolerance():
    v = NumVariant(group_id="c4", label="C", variant_summary="Angle C c4", question_text="What is pi?",
                   answer=3.1415, tolerance=0.0005)
    src = gift.emit_variant(v)
    assert "{#3.1415:0.0005}" in src
    assert gift.detect_gift_type(src) == "numerical"


def test_matching_round_trips_with_hostile_text():
    # Moodle splits pairs on '='. Only escaping stops hostile pair text from shredding them.
    v = MatchVariant(group_id="c5", label="A", variant_summary="Angle A c5", question_text=HOSTILE,
                     pairs=[Pair(left="x = 1", right="one = 1"),
                            Pair(left="y ~ 2", right="two -> 2"),
                            Pair(left="z", right="three")])
    src = gift.emit_variant(v)
    assert gift.detect_gift_type(src) == "matching"
    # Three pair lines. The right-hand "two -> 2" legitimately contains a fourth arrow:
    # Moodle splits each pair on its FIRST arrow, so the right side is safe.
    assert len([ln for ln in src.split("\n") if ln.strip().startswith("=")]) == 3
    assert "two -> 2" in src


# ------------------------------------------------- structural invariants

ALL_KINDS = [
    MCVariant(group_id="c1", label="A", variant_summary="Angle A c1", question_text=HOSTILE,
              options=["a = 1", "b ~ 2", "c {3}"], correct_index=0),
    TFVariant(group_id="c2", label="A", variant_summary="Angle A c2", question_text=HOSTILE, correct_answer=True),
    SAVariant(group_id="c3", label="A", variant_summary="Angle A c3", question_text=HOSTILE, accepted_answers=[HOSTILE]),
    NumVariant(group_id="c4", label="A", variant_summary="Angle A c4", question_text=HOSTILE, answer=42, tolerance=1),
    MatchVariant(group_id="c5", label="A", variant_summary="Angle A c5", question_text=HOSTILE,
                 pairs=[Pair(left="a = 1", right="b"), Pair(left="c", right="d")]),
]


@pytest.mark.parametrize("v", ALL_KINDS, ids=lambda v: v.kind)
def test_no_blank_line_inside_a_question(v):
    # Blank lines delimit questions. One inside a block splits it in two and the
    # orphan half fails to import. This is what the '\n' escape bug would have caused.
    assert "\n\n" not in gift.emit_variant(v)


@pytest.mark.parametrize("v", ALL_KINDS, ids=lambda v: v.kind)
def test_exactly_one_unescaped_brace_pair(v):
    src = gift.emit_variant(v)
    stripped = gift._placeholder(src)
    assert stripped.count("{") == 1
    assert stripped.count("}") == 1


@pytest.mark.parametrize("v", ALL_KINDS, ids=lambda v: v.kind)
def test_every_question_has_a_title_and_an_id(v):
    src = gift.emit_variant(v)
    assert src.startswith(f"// [id:{v.group_id}-{v.label}]")
    assert src.split("\n")[1].startswith("::")


def test_bank_categories_are_blank_line_delimited():
    b = _bank_with(*ALL_KINDS)
    out = gift.emit_bank(b)
    for line in out.split("\n"):
        if line.startswith("$CATEGORY:"):
            assert line.strip() == line
    cats = [c for c in _blocks(out) if c.startswith("$CATEGORY:")]
    assert len(cats) == 5


def test_every_block_in_an_emitted_bank_detects_correctly():
    b = _bank_with(*ALL_KINDS)
    out = gift.emit_bank(b)
    seen = {}
    for block in _blocks(out):
        if block.startswith("$CATEGORY:") or all(
            ln.startswith("//") for ln in block.split("\n")
        ):
            continue
        t = gift.detect_gift_type(block)
        seen[t] = seen.get(t, 0) + 1
    assert seen == {"multiple_choice": 1, "true_false": 1, "short_answer": 1,
                    "numerical": 1, "matching": 1}


# ---------------------------------------------------------- text_format

def test_markdown_prefix_stamped_on_stem_and_every_option():
    # Concept 5's options are code too, not just its stem.
    v = MCVariant(group_id="c5", label="A", variant_summary="Angle A c5", question_text="Complete: `for (let x = 0; ...)`",
                  options=["`x < 400`", "`x <= 400`", "`x = 400`"],
                  correct_index=1, text_format="markdown")
    src = gift.emit_variant(v)
    assert src.count("[markdown]") == 4  # stem + 3 options
    assert gift.detect_gift_type(src) == "multiple_choice"


def test_plain_format_emits_no_prefix():
    v = TFVariant(group_id="c2", label="A", variant_summary="Angle A c2", question_text="Plain statement here.",
                  correct_answer=True)
    assert "[plain]" not in gift.emit_variant(v)


def test_code_question_escapes_equals():
    v = MCVariant(group_id="c5", label="A", variant_summary="Angle A c5", question_text="Complete the loop.",
                  options=["x = 1", "x == 1", "x < 1"], correct_index=0)
    src = gift.emit_variant(v)
    # Every '=' from the option text is escaped; only the three answer markers are bare.
    assert "\\=" in src
    assert gift.detect_gift_type(src) == "multiple_choice"


# ---------------------------------------------------------------- quiz

def test_quiz_emits_one_variant_per_group_with_seed_header():
    bankmod.reset()
    bankmod.create_group("c1", "Loops", "multiple_choice")
    for i, lbl in enumerate("ABCD"):
        bankmod.put_variant(MCVariant(group_id="c1", label=lbl,
                                      question_text=f"Question {lbl} about loops?", variant_summary=f"Angle {lbl}",
                                      options=["w", "x", "y", "z"], correct_index=i))
    quiz = bankmod.pick_quiz(seed=99)
    out = gift.emit_quiz(quiz, bankmod.get())
    assert out.startswith("// Question bank\n// seed: 99")
    assert len([b for b in _blocks(out) if b.startswith("// [id:")]) == 1


def test_quiz_pick_is_deterministic_for_a_seed():
    bankmod.reset()
    bankmod.create_group("c1", "Loops", "multiple_choice")
    for i, lbl in enumerate("ABCD"):
        bankmod.put_variant(MCVariant(group_id="c1", label=lbl,
                                      question_text=f"Question {lbl} about loops?", variant_summary=f"Angle {lbl}",
                                      options=["w", "x", "y", "z"], correct_index=i))
    assert bankmod.pick_quiz(seed=7) == bankmod.pick_quiz(seed=7)


# ------------------------------------------------- titles and categories

def test_title_is_the_variant_summary_not_the_stem():
    v = MCVariant(group_id="c2", label="A", variant_summary="Purpose of the condition",
                  question_text="In a for loop, what is the purpose of the condition?",
                  options=["a", "b"], correct_index=0)
    assert "::c2-A Purpose of the condition::" in gift.emit_variant(v)


def test_title_is_escaped_because_moodle_unescapes_it():
    # readquestion() runs escapedchar_post over the name, so control chars must be escaped.
    v = MCVariant(group_id="c2", label="A", variant_summary="Purpose of x = 1",
                  question_text="What is the purpose of the condition?",
                  options=["a", "b"], correct_index=0)
    assert "::c2-A Purpose of x \\= 1::" in gift.emit_variant(v)


def test_category_names_the_concept():
    b = _bank_with(MCVariant(group_id="c1", label="A", variant_summary="Angle A",
                             question_text="A question about loops here?",
                             options=["a", "b"], correct_index=0))
    b.groups["c1"].concept_title = "Anatomy of a for loop"
    assert "$CATEGORY: top/Quizbot/t1/c1 Anatomy of a for loop" in gift.emit_bank(b)


def test_category_is_sanitised_not_escaped():
    # Moodle never unescapes the category value, so an escape would leave junk in the
    # name. '/' is the category path separator and must not survive.
    b = _bank_with(MCVariant(group_id="c1", label="A", variant_summary="Angle A",
                             question_text="A question about loops here?",
                             options=["a", "b"], correct_index=0))
    b.groups["c1"].concept_title = "map() / lerp() = remapping"
    line = [ln for ln in gift.emit_bank(b).split("\n") if ln.startswith("$CATEGORY")][0]
    assert line == "$CATEGORY: top/Quizbot/t1/c1 map() - lerp() = remapping"
    assert "\\" not in line


# ------------------------------------------------------- multiple answer

def _ma(**kw):
    kw.setdefault("group_id", "c7")
    kw.setdefault("label", "A")
    kw.setdefault("variant_summary", "Select all")
    kw.setdefault("question_text", "Which of these are true? Select all that apply.")
    kw.setdefault("options", ["right one", "wrong one", "right two", "wrong two"])
    kw.setdefault("correct_indices", [0, 2])
    return MAVariant(**kw)


def test_multiple_answer_round_trips():
    assert gift.detect_gift_type(gift.emit_variant(_ma())) == "multiple_answer"


def test_multiple_answer_emits_no_equals_at_all():
    # A single '=' anywhere in the block flips Moodle back to single-answer.
    block = gift._answer_block(_ma())
    assert "=" not in gift._placeholder(block)


def test_multiple_answer_weights_split_100():
    src = gift.emit_variant(_ma(correct_indices=[0, 2]))
    assert src.count("~%50%") == 2
    assert src.count("~%-50%") == 2  # two wrong share -100, so ticking all scores 0


def test_three_correct_uses_moodles_own_fraction():
    src = gift.emit_variant(_ma(options=["a", "b", "c", "d"], correct_indices=[0, 1, 2]))
    assert "~%33.33333%" in src   # matches Moodle's fraction list, not 33.333
    assert "~%-100%" in src       # the single wrong answer carries the whole penalty


def test_weight_never_emits_a_trailing_point_zero():
    # The weight regex is /^%\-*([0-9]{1,2})\.?([0-9]*)%/: '100' parses, '100.0' does not.
    assert gift._weight_str(100.0) == "100"
    assert gift._weight_str(50.0) == "50"
    assert gift._weight_str(-100.0) == "-100"
    assert gift._weight_str(100 / 3) == "33.33333"
    assert gift._weight_str(100 / 6) == "16.66667"


def test_equals_in_feedback_does_not_flip_to_single_answer():
    # The sharp one: Moodle checks for '=' across the whole answer block, feedback
    # included. Only escaping keeps this a multiple_answer question.
    v = _ma(feedback="Because x = 1 and y = 2")
    assert gift.detect_gift_type(gift.emit_variant(v)) == "multiple_answer"


def test_equals_in_option_text_does_not_flip_to_single_answer():
    v = _ma(options=["x = 1", "y = 2", "z = 3", "w = 4"], correct_indices=[0, 1])
    assert gift.detect_gift_type(gift.emit_variant(v)) == "multiple_answer"


def test_weight_precedes_the_format_prefix():
    # Moodle's own fixture: ~%-100%[plain]blue. The weight regex is anchored at ^, so a
    # prefix in front of it would make the weight literal answer text.
    v = _ma(options=["`a`", "`b`", "`c`", "`d`"], correct_indices=[0, 1],
            text_format="markdown")
    assert "~%50%[markdown]`a`" in gift.emit_variant(v)


def test_single_choice_still_detects_as_multiple_choice():
    v = MCVariant(group_id="c1", label="A", variant_summary="One right",
                  question_text="Which one is right here?",
                  options=["a", "b"], correct_index=0)
    assert gift.detect_gift_type(gift.emit_variant(v)) == "multiple_choice"
