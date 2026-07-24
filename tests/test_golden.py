"""Byte-compare a realistic bank against a checked-in GIFT file.

tests/golden/bank.json is a run covering all five question types, hostile code text, and
markdown options. Any change to the emitter that alters real output shows up here as a
diff instead of as a surprise at import time.

To re-bless after an intentional change:
    uv run python -c "import json,bank,gift; \
        b=bank.Bank.model_validate_json(open('tests/golden/bank.json').read()); \
        open('tests/golden/bank.gift','w').write(gift.emit_bank(b))"
"""

from pathlib import Path
from typing import get_args
from coursekit.emit import gift
from coursekit.generate.quiz.bank import Bank, QuestionType

GOLDEN = Path(__file__).parent / "golden"


def _bank() -> Bank:
    return Bank.model_validate_json((GOLDEN / "bank.json").read_text(encoding="utf-8"))


def test_emitted_bank_matches_golden_file():
    assert gift.emit_bank(_bank()) == (GOLDEN / "bank.gift").read_text(encoding="utf-8")


def test_golden_covers_every_question_type():
    kinds = {v.kind for g in _bank().groups.values() for v in g.variants.values()}
    assert kinds == set(get_args(QuestionType))


def test_every_question_in_the_golden_file_detects_as_its_declared_type():
    b = _bank()
    text = (GOLDEN / "bank.gift").read_text(encoding="utf-8")
    blocks = [x for x in text.split("\n\n") if x.strip()]

    checked = 0
    for block in blocks:
        if block.startswith("$CATEGORY:") or all(
            ln.startswith("//") for ln in block.split("\n")
        ):
            continue
        # "// [id:c1-A] ..." -> group c1, variant A
        ident = block.split("[id:", 1)[1].split("]", 1)[0]
        gid, label = ident.rsplit("-", 1)
        expected = b.groups[gid].variants[label].kind
        assert gift.detect_gift_type(block) == expected, ident
        checked += 1

    assert checked == sum(len(g.variants) for g in b.groups.values())


def test_golden_file_has_no_blank_line_inside_any_question():
    text = (GOLDEN / "bank.gift").read_text(encoding="utf-8")
    for block in text.split("\n\n"):
        if block.startswith("// [id:"):
            assert "\n\n" not in block
