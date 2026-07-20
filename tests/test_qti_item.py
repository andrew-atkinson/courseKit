import xml.etree.ElementTree as ET
import pytest
from coursekit.emit import qti
from coursekit.generate.quiz.bank import Group, MCVariant

HOSTILE = "for (let x = 0; x < 10; x++) & then <tag>"


def liter(root, name):
    """Iterate elements by local name, ignoring the default namespace ET applies."""
    return [e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == name]


def fields(root):
    return {list(f)[0].text: list(f)[1].text for f in liter(root, "qtimetadatafield")}


def _mc(label="A", correct=0, group="c1", fmt="plain", **kw):
    kw.setdefault("options", ["alpha", "beta", "gamma", "delta"])
    kw.setdefault("variant_summary", f"Angle {label}")
    return MCVariant(group_id=group, label=label, text_format=fmt,
                     question_text=f"Which is right in {label}? {HOSTILE}",
                     correct_index=correct, **kw)


# ------------------------------------------------------------- escaping

def test_mattext_round_trips_hostile_text():
    # The mattext body is XML-escaped HTML. Decoding both levels must recover the text.
    body = qti.mattext(HOSTILE, "plain")
    # Wrap in an element and parse: the .text is the HTML level (one unescape).
    html_level = ET.fromstring(f"<m>{body}</m>").text
    assert html_level == f"<div>{_html_escape(HOSTILE)}</div>"


def _html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def test_markdown_code_becomes_code_tag():
    body = qti.mattext("Complete `x <= 400` now", "markdown")
    html_level = ET.fromstring(f"<m>{body}</m>").text
    assert "<code>x &lt;= 400</code>" in html_level
    assert html_level.startswith("<div>") and html_level.endswith("</div>")


def test_ampersand_double_escapes_like_the_export():
    # HTML '&nbsp;' -> XML '&amp;nbsp;'  (the export's tell).
    body = qti.mattext("a b", "plain")  # non-breaking space escapes to &nbsp; ? no—raw nbsp
    # Use a literal entity path instead: '&' in text -> HTML '&amp;' -> XML '&amp;amp;'
    body = qti.mattext("Tom & Jerry", "plain")
    assert "&amp;amp;" in body


# ------------------------------------------------- identifiers

def test_ids_are_deterministic():
    assert qti.item_id("r", "c1", "A") == qti.item_id("r", "c1", "A")
    assert qti.bank_ident("r", "c1") == qti.bank_ident("r", "c1")


def test_ids_differ_by_input():
    assert qti.item_id("r", "c1", "A") != qti.item_id("r", "c1", "B")
    assert qti.bank_ident("r", "c1") != qti.bank_ident("r", "c2")


def test_id_shapes():
    assert qti.qid("x").startswith("g") and len(qti.qid("x")) == 33
    assert qti.iid("x").startswith("i") and len(qti.iid("x")) == 33
    assert len(qti.item_id("x")) == 32
    lab = qti.label_id("x")
    assert len(lab) == 36 and lab.count("-") == 4


# ------------------------------------------------- MC item

def test_mc_item_is_well_formed():
    xml = qti.emit_item(_mc(), "run")
    ET.fromstring(xml)  # raises on malformed


def test_mc_item_carries_the_question_type():
    xml = qti.emit_item(_mc(), "run")
    root = ET.fromstring(xml)
    entries = {f.find("fieldlabel").text: f.find("fieldentry").text
               for f in root.iter("qtimetadatafield")}
    assert entries["question_type"] == "multiple_choice_question"


def test_correct_varequal_matches_a_response_label():
    # The load-bearing invariant: the scored answer must be a real option id.
    for correct in range(4):
        xml = qti.emit_item(_mc(correct=correct), "run")
        root = ET.fromstring(xml)
        label_ids = {rl.get("ident") for rl in root.iter("response_label")}
        scored = root.find(".//respcondition/conditionvar/varequal").text
        assert scored in label_ids
        # and it is the one at correct_index
        ordered = [rl.get("ident") for rl in root.iter("response_label")]
        assert scored == ordered[correct]


def test_original_answer_ids_lists_every_option():
    xml = qti.emit_item(_mc(), "run")
    root = ET.fromstring(xml)
    entries = {f.find("fieldlabel").text: f.find("fieldentry").text
               for f in root.iter("qtimetadatafield")}
    listed = entries["original_answer_ids"].split(",")
    label_ids = [rl.get("ident") for rl in root.iter("response_label")]
    assert listed == label_ids


def test_response_lid_is_single_cardinality():
    root = ET.fromstring(qti.emit_item(_mc(), "run"))
    assert root.find(".//response_lid").get("rcardinality") == "Single"


def test_every_modelled_question_type_can_emit():
    # bank.py's QuestionType and qti.py's emitters must not drift apart.
    from typing import get_args
    from coursekit.generate.quiz.bank import QuestionType
    assert set(get_args(QuestionType)) == set(qti._ITEM_EMITTERS)


def test_unknown_kind_raises_a_clear_error():
    class _Fake:
        kind = "sonnet_question"
    with pytest.raises(NotImplementedError, match="sonnet_question"):
        qti.emit_item(_Fake(), "run")


# ------------------------------------------------- objectbank

def _group():
    g = Group(group_id="c1", concept_title="Loops & <fun>", question_type="multiple_choice")
    for i, lbl in enumerate("ABCD"):
        g.variants[lbl] = _mc(lbl, correct=i)
    return g


def test_objectbank_is_well_formed_and_flagged():
    root = ET.fromstring(qti.emit_objectbank(_group(), "run"))
    ob = liter(root, "objectbank")[0]
    assert ob.get("canvas_item_bank") == "true"
    assert ob.get("ident") == qti.bank_ident("run", "c1")


def test_objectbank_holds_every_variant():
    root = ET.fromstring(qti.emit_objectbank(_group(), "run"))
    assert len(liter(root, "item")) == 4


def test_bank_title_is_escaped():
    root = ET.fromstring(qti.emit_objectbank(_group(), "run"))
    assert fields(root)["bank_title"] == "Loops & <fun>"  # parser un-escapes to the original
