"""Phase B item emitters, checked against the Classic sample's structure
(docs/Classic-Quiz-Sample). true_false is inferred (no sample); numerical is gated."""
import xml.etree.ElementTree as ET

import pytest

import qti
from bank import MAVariant, MatchVariant, NumVariant, Pair, SAVariant, TFVariant


def liter(root, name):
    return [e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == name]


def qtype(root):
    for f in liter(root, "qtimetadatafield"):
        if list(f)[0].text == "question_type":
            return list(f)[1].text
    return None


# ----------------------------------------------------------- true/false

def test_true_false_is_well_formed_and_typed():
    v = TFVariant(group_id="c1", label="A", variant_summary="A claim",
                  question_text="Loops repeat code.", correct_answer=True)
    root = ET.fromstring(qti.emit_item(v, "r"))
    assert qtype(root) == "true_false_question"
    labels = [rl.get("ident") for rl in liter(root, "response_label")]
    assert len(labels) == 2
    scored = liter(root, "varequal")[0].text
    assert scored == labels[0]  # True is first, and correct_answer=True


def test_true_false_false_scores_the_second_option():
    v = TFVariant(group_id="c1", label="B", variant_summary="A claim",
                  question_text="Loops never repeat.", correct_answer=False)
    root = ET.fromstring(qti.emit_item(v, "r"))
    labels = [rl.get("ident") for rl in liter(root, "response_label")]
    assert liter(root, "varequal")[0].text == labels[1]


# ----------------------------------------------------------- short answer

def test_short_answer_structure_and_all_answers_scored():
    v = SAVariant(group_id="c1", label="A", variant_summary="Name it",
                  question_text="Two plus two equals?", accepted_answers=["four", "4"])
    root = ET.fromstring(qti.emit_item(v, "r"))
    assert qtype(root) == "short_answer_question"
    assert liter(root, "render_fib")  # fill-in-blank
    # every accepted answer is an OR'd varequal in one respcondition
    cond = liter(root, "respcondition")[0]
    answers = {vq.text for vq in liter(cond, "varequal")}
    assert answers == {"four", "4"}


def test_short_answer_escapes_answer_text():
    v = SAVariant(group_id="c1", label="A", variant_summary="Operator",
                  question_text="The operator is?", accepted_answers=["a < b & c"])
    root = ET.fromstring(qti.emit_item(v, "r"))
    assert liter(root, "varequal")[0].text == "a < b & c"  # parses back to the original


# --------------------------------------------------------- multiple answer

def test_multiple_answer_structure_and_scoring():
    v = MAVariant(group_id="c1", label="A", variant_summary="Select all",
                  question_text="Which are NOT fish? Select all.",
                  options=["Gordon", "cod", "Mixed Martial Arts", "cartons"],
                  correct_indices=[0, 2, 3])
    root = ET.fromstring(qti.emit_item(v, "r"))
    assert qtype(root) == "multiple_answers_question"
    assert liter(root, "response_lid")[0].get("rcardinality") == "Multiple"

    labels = [rl.get("ident") for rl in liter(root, "response_label")]
    and_block = liter(root, "and")[0]
    # correct options are bare varequal; wrong options are wrapped in <not>
    negated = {liter(n, "varequal")[0].text for n in liter(and_block, "not")}
    all_vq = {vq.text for vq in liter(and_block, "varequal")}
    positive = all_vq - negated
    assert positive == {labels[0], labels[2], labels[3]}
    assert negated == {labels[1]}


# ----------------------------------------------------------- matching

def _match():
    return MatchVariant(group_id="c1", label="A", variant_summary="Translate",
                        question_text="Match Spanish to English.",
                        pairs=[Pair(left="pregunta", right="question"),
                               Pair(left="tiempo", right="time"),
                               Pair(left="maleta", right="suitcase")])


def test_matching_structure():
    root = ET.fromstring(qti.emit_item(_match(), "r"))
    assert qtype(root) == "matching_question"
    # one response_lid per left (a dropdown), each offering every right option
    lids = liter(root, "response_lid")
    assert len(lids) == 3
    for lid in lids:
        rights = [rl.get("ident") for rl in liter(lid, "response_label")]
        assert len(rights) == 3  # the shared right-option set


def test_matching_right_ids_are_shared_across_lefts():
    root = ET.fromstring(qti.emit_item(_match(), "r"))
    sets = [{rl.get("ident") for rl in liter(lid, "response_label")}
            for lid in liter(root, "response_lid")]
    assert sets[0] == sets[1] == sets[2]  # identical option set in every dropdown


def test_matching_each_left_scores_its_right():
    root = ET.fromstring(qti.emit_item(_match(), "r"))
    conds = liter(root, "respcondition")
    assert len(conds) == 3
    for c in conds:
        vq = liter(c, "varequal")[0]
        respident = vq.get("respident")  # response_<leftid>
        chosen = vq.text
        # the scored right must belong to that left's own dropdown
        lid = [l for l in liter(root, "response_lid") if l.get("ident") == respident][0]
        assert chosen in {rl.get("ident") for rl in liter(lid, "response_label")}
        assert liter(c, "setvar")[0].get("action") == "Add"


def test_matching_scores_sum_to_about_100():
    root = ET.fromstring(qti.emit_item(_match(), "r"))
    total = sum(float(sv.text) for sv in liter(root, "setvar"))
    assert 99.9 <= total <= 100.1  # 3 x 33.33


# ----------------------------------------------------------- numerical (gated)

def test_numerical_still_gated_with_a_clear_message():
    v = NumVariant(group_id="c1", label="A", variant_summary="Count",
                   question_text="How many sides has a triangle?", answer=3)
    with pytest.raises(NotImplementedError, match="numerical"):
        qti.emit_item(v, "r")


# ----------------------------------------------- all supported types in a bank

def test_objectbank_with_mixed_supported_types_is_well_formed():
    from bank import Group, MCVariant
    g = Group(group_id="c1", concept_title="Mixed", question_type="true_false")
    for lbl, ans in zip("ABCD", [True, False, True, False]):
        g.variants[lbl] = TFVariant(group_id="c1", label=lbl, variant_summary=f"Claim {lbl}",
                                    question_text=f"Statement {lbl} is correct here.",
                                    correct_answer=ans)
    root = ET.fromstring(qti.emit_objectbank(g, "r"))
    assert len(liter(root, "item")) == 4
