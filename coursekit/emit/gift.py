"""GIFT serialisation.

Mirrors Moodle's importer (question/format/gift/format.php, MOODLE_405_STABLE) so that
what we emit is what Moodle reads back. See agent/GIFT_format_compact.md.

Text is stored raw in the bank and escaped only here, at emit time, and only on leaves.
Never run repchar over an assembled answer block: it escapes ':' and '#', which are
structural in {#4:0.5}.
"""

import re

# Mirror of Moodle repchar(). Every key is a single character, so str.translate is a
# genuine single pass and the "escape backslash first" ordering hazard cannot arise.
# "\n" maps to a literal backslash + n, NOT a newline: blank lines delimit questions,
# so a raw newline in a stem would split one question into two at import.
_REPTABLE = {
    "\\": "\\\\",
    "#": "\\#",
    "=": "\\=",
    "~": "\\~",
    "{": "\\{",
    "}": "\\}",
    ":": "\\:",
    "\n": "\\n",
    "\r": "",
}
_TRANS = str.maketrans(_REPTABLE)

# Mirror of escapedchar_pre(). Moodle runs this BEFORE detecting the question type,
# so an escaped \~ correctly does not make a short answer into a multiple choice.
_UNESCAPABLE = {":": ":", "#": "#", "=": "=", "{": "{", "}": "}", "~": "~",
                "n": "\n", "\\": "\\"}


def repchar(text: str) -> str:
    """Escape GIFT control characters in a leaf string."""
    return text.translate(_TRANS)


def unrepchar(text: str) -> str:
    """Inverse of repchar. An unrecognised escape keeps its backslash, as Moodle does."""
    return re.sub(r"\\(.)", lambda m: _UNESCAPABLE.get(m.group(1), "\\" + m.group(1)), text)


def _placeholder(text: str) -> str:
    """What Moodle's escapedchar_pre leaves behind: escapes neutralised, so that type
    detection cannot see them. We only need them gone, not their exact placeholders."""
    return re.sub(r"\\(.)", lambda m: "" if m.group(1) in _UNESCAPABLE else m.group(0), text)


def detect_gift_type(question_source: str) -> str:
    """Moodle's type-detection precedence, first match wins.

    Takes a whole question (title, stem, braces), not just the answer block, because
    'no braces at all' is what distinguishes a description.
    """
    text = _placeholder(question_source)

    start, finish = text.find("{"), text.find("}")
    if start == -1 and finish == -1:
        return "description"
    if start == -1 or finish == -1:
        raise ValueError("unbalanced braces")

    answer = text[start + 1:finish].strip()

    # A trailing #### general-feedback section is not part of type detection.
    gf = answer.rfind("####")
    if gf != -1:
        answer = answer[:gf].strip()

    if answer == "":
        return "essay"
    if answer[0] == "#":
        return "numerical"
    if "~" in answer:
        # Moodle calls both of these qtype 'multichoice' and distinguishes them with
        # single = (strpos($answertext, "=") === false) ? 0 : 1. One '=' anywhere in the
        # block, feedback included, makes it single-answer.
        return "multiple_choice" if "=" in answer else "multiple_answer"
    if "=" in answer and "->" in answer:
        return "matching"

    tf = answer
    hash_at = answer.find("#")
    if hash_at > 0:
        tf = answer[:hash_at].strip()
    if tf in ("T", "TRUE", "F", "FALSE"):  # case-sensitive: {t} is a SHORT ANSWER
        return "true_false"

    return "short_answer"


# ---------------------------------------------------------------- emitters


# Wrong answers in a multiple_answer question share -100% between them, so selecting
# every option scores exactly zero. Moodle's own GIFT test uses a flat -100% per wrong
# answer instead, where a single wrong tick wipes out every correct one. Change this if
# you want that harsher rule.
_PENALISE_WRONG = True


def _weight_str(pct: float) -> str:
    """Format a percentage the way GIFT's weight regex accepts it.

    The regex is /^%\\-*([0-9]{1,2})\\.?([0-9]*)%/, so '100' parses but '100.0' does not:
    after '10' it wants a digit or '%', and finds '.'. Round to 5dp to land on Moodle's
    own fraction values (33.33333, 16.66667).
    """
    r = round(pct, 5)
    return str(int(r)) if r == int(r) else str(r)


def _leaf(text: str, text_format: str) -> str:
    """One escaped text span, with its format prefix.

    The prefix is applied per-leaf, not per-question: a code-completion question has code
    in its options as well as its stem. '[markdown]' must stay unescaped and lead the span.
    """
    body = repchar(text)
    return f"[{text_format}]{body}" if text_format != "plain" else body


def _title(v) -> str:
    # Always emit a title. Without one Moodle derives it from the first 80 chars of the
    # stem, and four variants of one concept collide into near-identical names.
    # The title IS unescaped on import (escapedchar_post), so it must be escaped here.
    return repchar(f"{v.group_id}-{v.label} {v.variant_summary}")


def _category(run_id: str, group_id: str, concept_title: str) -> str:
    """Sanitised, NOT escaped.

    Moodle runs escapedchar_pre before the $CATEGORY check but never unescapes the value,
    so an escape sequence here would leave placeholder junk in the category name. '/' is
    the category path separator, so it has to go.
    """
    safe = " ".join(concept_title.replace("/", "-").replace("\\", "-").split())
    return f"top/Quizbot/{run_id}/{group_id} {safe}"


def _meta_comment(v, tags: list[str]) -> str:
    """[id:] makes re-import idempotent (Moodle matches on idnumber and updates rather
    than duplicating); [tag:] carries the concept back from the LMS to bank.json."""
    parts = [f"[id:{_esc_bracket(v.group_id)}-{v.label}]"]
    parts += [f"[tag:{_esc_bracket(t)}]" for t in tags]
    return "// " + " ".join(parts)


def _esc_bracket(text: str) -> str:
    return text.replace("]", "\\]")


def _answer_block(v) -> str:
    fmt = v.text_format
    if v.kind == "multiple_choice":
        lines = []
        for i, opt in enumerate(v.options):
            # '=' is 100% and '~' is 0%. No %weight% is emitted: single-answer only in v1,
            # and in multiple choice a weight must follow '~', never '='.
            marker = "=" if i == v.correct_index else "~"
            line = f"    {marker}{_leaf(opt, fmt)}"
            if v.feedback and i == v.correct_index:
                # Feedback on the correct answer; per-option feedback is deferred.
                line += f"#{_leaf(v.feedback, fmt)}"
            lines.append(line)
        return "{\n" + "\n".join(lines) + "\n}"

    if v.kind == "multiple_answer":
        correct = set(v.correct_indices)
        n_right, n_wrong = len(correct), len(v.options) - len(correct)
        right_w = _weight_str(100 / n_right)
        wrong_w = _weight_str(-100 / n_wrong) if _PENALISE_WRONG else "0"
        lines = []
        for i, opt in enumerate(v.options):
            # Every option carries '~' and an explicit weight. A single '=' anywhere in
            # this block — including inside feedback — would flip Moodle back to
            # single-answer, so there must be none. Escaping is what guarantees that.
            # Weight precedes the format prefix: ~%-100%[plain]blue.
            w = right_w if i in correct else wrong_w
            line = f"    ~%{w}%{_leaf(opt, fmt)}"
            if v.feedback and i == min(correct):
                line += f"#{_leaf(v.feedback, fmt)}"
            lines.append(line)
        return "{\n" + "\n".join(lines) + "\n}"

    if v.kind == "true_false":
        token = "TRUE" if v.correct_answer else "FALSE"
        out = token
        # GIFT order: wrong-response feedback first, then right-response.
        if v.feedback_wrong or v.feedback_right:
            out += f"#{_leaf(v.feedback_wrong or '', fmt)}"
            out += f"#{_leaf(v.feedback_right or '', fmt)}"
        return "{" + out + "}"

    if v.kind == "short_answer":
        parts = []
        for i, a in enumerate(v.accepted_answers):
            # Feedback binds to the answer it follows, so put it on the first (canonical)
            # one rather than trailing the block, where it would bind to the last.
            part = f"={_leaf(a, fmt)}"
            if v.feedback and i == 0:
                part += f"#{_leaf(v.feedback, fmt)}"
            parts.append(part)
        return "{" + " ".join(parts) + "}"

    if v.kind == "numerical":
        # The '#' opener, and the ':' between answer and tolerance, are structure.
        # Never repchar them: repchar escapes both and would destroy the question.
        num = _fmt_number(v.answer)
        body = f"#{num}" if v.tolerance == 0 else f"#{num}:{_fmt_number(v.tolerance)}"
        if v.feedback:
            body += f"#{_leaf(v.feedback, fmt)}"
        return "{" + body + "}"

    if v.kind == "matching":
        lines = [f"    ={_leaf(p.left, fmt)} -> {_leaf(p.right, fmt)}" for p in v.pairs]
        return "{\n" + "\n".join(lines) + "\n}"

    raise ValueError(f"cannot emit unknown kind {v.kind!r}")


def _fmt_number(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else repr(float(x))


def emit_variant(v, tags: list[str] | None = None) -> str:
    """One GIFT question: metadata comment, title, stem, answer block."""
    return "\n".join([
        _meta_comment(v, tags or []),
        f"::{_title(v)}::{_leaf(v.question_text, v.text_format)} {_answer_block(v)}",
    ])


def emit_bank(bank) -> str:
    """Every variant, one $CATEGORY per concept.

    $CATEGORY is sticky, so each category line applies to the questions that follow it.
    Import once, then build a quiz with one 'random question from category' slot per
    concept: that is Moodle's equivalent of Canvas's pick_count=1 per group, and it is
    the only way GIFT can express the variation. GIFT has no assessment construct.
    """
    chunks = [f"// Question bank: {bank.title}\n// run: {bank.run_id}"]
    for gid in sorted(bank.groups):
        g = bank.groups[gid]
        if not g.variants:
            continue
        # Moodle strips '//' lines before reading the chunk, so the concept comment can
        # ride along with the category line rather than forming an empty question.
        chunks.append(f"$CATEGORY: {_category(bank.run_id, gid, g.concept_title)}"
                      f"\n// {g.concept_title}")
        for lbl in sorted(g.variants):
            chunks.append(emit_variant(g.variants[lbl], tags=[gid, g.question_type]))
    return "\n\n".join(chunks) + "\n"


def emit_quiz(quiz: dict, bank) -> str:
    """One deterministic instance: the seeded pick, flat, no categories.

    A printable fixed-form paper. The randomised quiz is bank.gift plus per-category
    random slots; this is a single realisation of it.
    """
    chunks = [f"// {quiz['title']}\n// seed: {quiz['seed']}"]
    for gid in sorted(quiz["picks"]):
        g = bank.groups[gid]
        for lbl in quiz["picks"][gid]:
            chunks.append(emit_variant(g.variants[lbl], tags=[gid, g.question_type]))
    return "\n\n".join(chunks) + "\n"
