"""The question bank: models, validation, and state.

A variant is keyed on (group_id, label). Re-adding a key REPLACES it. That overwrite is
the point of this module: the model can revise as much as it likes without leaving dead
drafts behind, which is what free text could not express.

Knows nothing about GIFT. See gift.py for serialisation.
"""

import json
import random
import re
from pathlib import Path
from typing import Annotated, Literal
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

QuestionType = Literal["multiple_choice", "multiple_answer", "true_false", "short_answer",
                       "numerical", "matching"]
TextFormat = Literal["plain", "markdown", "html"]

# A leading %n% in option text is read by GIFT as an answer weight and eaten. Our own
# weight consumes the first match in multiple_answer, but a bare '~' distractor in
# multiple_choice would silently become a partially-correct answer.
_LOOKS_LIKE_WEIGHT = re.compile(r"^%-?\d{1,2}\.?\d*%")

# The artefacts the model left in output/quiz_20260716_141609.txt when it corrected
# itself in prose: "D. Initialization, ... (Wait, this is the same as A)".
# Deliberately narrow. "note" and "fix" are excluded: "(Note: x is 5)" is legitimate
# question text and a guardrail that rejects real content is worse than none.
_META_COMMENTARY = re.compile(
    r"\(\s*(wait|correction|corrected|same as|let'?s|restart|ignore this|oops)\b",
    re.IGNORECASE,
)
_BACKTICK_SPAN = re.compile(r"`[^`]*`")


def _check_no_meta_commentary(text: str) -> str:
    if _META_COMMENTARY.search(text):
        raise ValueError(
            "contains a self-correction note. Do not write corrections into the text. "
            "Re-call the same tool with the same group_id and variant_label to replace it"
        )
    return text


def _check_markdown_angles(text: str, text_format: str) -> None:
    """Under [markdown], an unbackticked '<' can be eaten as a tag open by Moodle's
    markdown filter, silently deleting the rest of the line. Backticks are load-bearing."""
    if text_format != "markdown":
        return
    stripped = _BACKTICK_SPAN.sub("", text)
    if "<" in stripped or ">" in stripped:
        raise ValueError(
            "has '<' or '>' outside backticks while text_format is markdown; "
            "wrap code in backticks or use text_format='plain'"
        )


class BaseVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str = Field(min_length=1)
    label: str = Field(pattern=r"^[A-Z]$")
    question_text: str = Field(min_length=8)
    # Names the angle this variant takes on the concept, e.g. "Purpose of the condition".
    # Becomes the GIFT title. max_length is the forcing function: a pasted stem is
    # rejected, so the model has to actually say what this variant tests.
    variant_summary: str = Field(min_length=3, max_length=60)
    text_format: TextFormat = "plain"

    @field_validator("question_text")
    @classmethod
    def _clean_stem(cls, v: str) -> str:
        return _check_no_meta_commentary(v.strip())

    @field_validator("variant_summary")
    @classmethod
    def _clean_summary(cls, v: str) -> str:
        return _check_no_meta_commentary(" ".join(v.split()))

    @model_validator(mode="after")
    def _summary_is_not_the_stem(self):
        if self.variant_summary.casefold() == self.question_text.casefold():
            raise ValueError(
                "variant_summary must not repeat the question text. Say what this variant "
                "tests in a few words, e.g. 'Purpose of the condition'"
            )
        return self

    # mode="after" (not model_post_init): pydantic wraps ValueError raised here into a
    # ValidationError, which tools.py renders into an actionable message for the model.
    @model_validator(mode="after")
    def _check_stem_markdown(self):
        _check_markdown_angles(self.question_text, self.text_format)
        return self


def _clean_option_list(v: list[str]) -> list[str]:
    opts = [o.strip() for o in v]
    for o in opts:
        if not o:
            raise ValueError("option text cannot be empty")
        _check_no_meta_commentary(o)
        if _LOOKS_LIKE_WEIGHT.match(o):
            raise ValueError(
                f"option {o!r} starts with something GIFT reads as an answer weight. "
                f"Reword it so it does not begin with a percentage in %% signs"
            )
    seen = [o.casefold() for o in opts]
    if len(set(seen)) != len(seen):
        raise ValueError("options must be distinct from one another")
    return opts


class _OptionVariant(BaseVariant):
    """Shared by the two option-list types."""
    options: list[str] = Field(min_length=2, max_length=6)

    @field_validator("options")
    @classmethod
    def _clean_options(cls, v: list[str]) -> list[str]:
        return _clean_option_list(v)

    @model_validator(mode="after")
    def _check_option_markdown(self):
        for o in self.options:
            _check_markdown_angles(o, self.text_format)
        return self


class MCVariant(_OptionVariant):
    kind: Literal["multiple_choice"] = "multiple_choice"
    correct_index: int = Field(ge=0)
    feedback: str | None = None

    @model_validator(mode="after")
    def _check_correct_index(self):
        if self.correct_index >= len(self.options):
            raise ValueError(
                f"correct_index {self.correct_index} is out of range for "
                f"{len(self.options)} options (valid: 0..{len(self.options) - 1})"
            )
        return self


class MAVariant(_OptionVariant):
    """Multiple correct answers: 'select all that apply'.

    Emitted with a weight on every option and no '=' anywhere, because GIFT decides
    single-vs-multi by whether the answer block contains an '=' at all.
    """
    kind: Literal["multiple_answer"] = "multiple_answer"
    correct_indices: list[int] = Field(min_length=1)
    feedback: str | None = None

    @model_validator(mode="after")
    def _check_correct_indices(self):
        n = len(self.options)
        if len(self.correct_indices) < 2:
            # Checked here rather than via Field(min_length=2) so the message can name
            # the tool to use instead.
            raise ValueError(
                "a 'select all that apply' question needs at least two correct options. "
                "With exactly one correct answer, use add_multiple_choice_variant instead"
            )
        if len(set(self.correct_indices)) != len(self.correct_indices):
            raise ValueError("correct_indices must not repeat an index")
        for i in self.correct_indices:
            if not 0 <= i < n:
                raise ValueError(
                    f"correct_indices contains {i}, which is out of range for {n} options "
                    f"(valid: 0..{n - 1})"
                )
        if len(self.correct_indices) >= n:
            raise ValueError(
                "at least one option must be wrong, or the question cannot be got wrong"
            )
        return self


class TFVariant(BaseVariant):
    kind: Literal["true_false"] = "true_false"
    correct_answer: bool
    # GIFT order is wrong-response feedback first, then right-response.
    feedback_wrong: str | None = None
    feedback_right: str | None = None


class SAVariant(BaseVariant):
    kind: Literal["short_answer"] = "short_answer"
    accepted_answers: list[str] = Field(min_length=1)
    feedback: str | None = None

    @field_validator("accepted_answers")
    @classmethod
    def _clean_answers(cls, v: list[str]) -> list[str]:
        ans = [a.strip() for a in v]
        if any(not a for a in ans):
            raise ValueError("accepted answer cannot be empty")
        if len({a.casefold() for a in ans}) != len(ans):
            raise ValueError("accepted answers must be distinct")
        for a in ans:
            # A short answer always carries '=' as its answer marker, and GIFT reads
            # '=' plus '->' as a matching question. '->' cannot be escaped, so this
            # combination is inexpressible rather than merely awkward.
            if "->" in a:
                raise ValueError(
                    "'->' cannot appear in a short answer: GIFT would import the question "
                    "as a matching question, and '->' cannot be escaped. Reword the answer "
                    "(for example use 'gives' or 'produces')"
                )
        return ans


class NumVariant(BaseVariant):
    kind: Literal["numerical"] = "numerical"
    answer: float
    tolerance: float = Field(default=0.0, ge=0.0)
    feedback: str | None = None


class Pair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: str = Field(min_length=1)
    right: str = Field(min_length=1)

    @field_validator("left")
    @classmethod
    def _no_arrow_in_left(cls, v: str) -> str:
        # Moodle splits a pair on the FIRST '->' and '->' is not escapable, so an arrow
        # on the left would truncate it. The right-hand side is safe: everything after
        # the first arrow is taken verbatim.
        if "->" in v:
            raise ValueError("'->' cannot appear in the left side of a matching pair")
        return v.strip()


class MatchVariant(BaseVariant):
    kind: Literal["matching"] = "matching"
    # No feedback field by design: GIFT matching supports neither feedback nor weights,
    # and a '#' there becomes literal text in the question.
    pairs: list[Pair] = Field(min_length=2)

    @field_validator("pairs")
    @classmethod
    def _distinct_lefts(cls, v: list[Pair]) -> list[Pair]:
        lefts = [p.left.casefold() for p in v]
        if len(set(lefts)) != len(lefts):
            raise ValueError("the left side of each matching pair must be distinct")
        return v


Variant = Annotated[
    MCVariant | MAVariant | TFVariant | SAVariant | NumVariant | MatchVariant,
    Field(discriminator="kind"),
]

_KIND_TO_TOOL = {
    "multiple_choice": "add_multiple_choice_variant",
    "multiple_answer": "add_multiple_answer_variant",
    "true_false": "add_true_false_variant",
    "short_answer": "add_short_answer_variant",
    "numerical": "add_numerical_variant",
    "matching": "add_matching_variant",
}


class Group(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_id: str = Field(min_length=1)
    concept_title: str = Field(min_length=1)
    question_type: QuestionType
    variants: dict[str, Variant] = Field(default_factory=dict)


class Bank(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    title: str = "Question bank"
    source: str | None = None
    groups: dict[str, Group] = Field(default_factory=dict)
    finalized: bool = False


# ---- module state (mirrors the checklist/completed convention in tools.py) ----

_bank = Bank(run_id="unsaved")
_out_dir: Path | None = None


def init(run_id: str, out_dir: Path | None = None, title: str = "Question bank",
         source: str | None = None) -> None:
    global _bank, _out_dir
    _bank = Bank(run_id=run_id, title=title, source=source)
    _out_dir = Path(out_dir) if out_dir else None


def reset() -> None:
    """Test hook."""
    init("test", None)


def load(bank_obj: "Bank", out_dir: Path | None = None) -> None:
    """Adopt an EXISTING bank as the working singleton — for editing a finished bank in place (the
    targeted-fix pass reloads a `bank.json`, then a `put_variant` overwrites just the flagged variant
    and autosaves the whole bank). Distinct from `init`, which starts empty."""
    global _bank, _out_dir
    _bank = bank_obj
    _out_dir = Path(out_dir) if out_dir else None


def get() -> Bank:
    return _bank


def is_finalized() -> bool:
    return _bank.finalized


def _autosave() -> None:
    """Persist after every write. The file is tiny and this is the whole point of the
    feature: a crash at variant 19 must not lose the first 18."""
    if _out_dir is None:
        return
    _out_dir.mkdir(parents=True, exist_ok=True)
    (_out_dir / "bank.json").write_text(
        json.dumps(_bank.model_dump(), indent=2), encoding="utf-8"
    )


def create_group(group_id: str, concept_title: str, question_type: str) -> str:
    if question_type not in _KIND_TO_TOOL:
        return (f"ERROR: unknown question_type '{question_type}'. "
                f"Use one of: {', '.join(_KIND_TO_TOOL)}")
    existing = _bank.groups.get(group_id)
    if existing and existing.variants:
        return (f"ERROR: group '{group_id}' already has {len(existing.variants)} variant(s). "
                f"To change its type, use a new group_id.")
    _bank.groups[group_id] = Group(
        group_id=group_id, concept_title=concept_title.strip(), question_type=question_type
    )
    _autosave()
    return (f"OK group '{group_id}' ({question_type}): {concept_title.strip()[:50]}. "
            f"Now add variants A-D with {_KIND_TO_TOOL[question_type]}.")


def unused_correct_positions(group_id: str, exclude_label: str | None = None) -> list[int]:
    """Which correct-answer indices are still free in a multiple-choice group.

    Powers the steering ack. Only meaningful for multiple_choice: the other four types
    have no answer positions, so the 'different correct answer per variation' rule is
    incoherent for them.
    """
    g = _bank.groups.get(group_id)
    if not g or g.question_type != "multiple_choice":
        return []
    mc = [v for lbl, v in g.variants.items()
          if lbl != exclude_label and v.kind == "multiple_choice"]
    if not mc:
        return []
    width = min(len(v.options) for v in mc)
    used = {v.correct_index for v in mc}
    return [i for i in range(width) if i not in used]


def put_variant(v: Variant) -> str:
    """Store a variant, REPLACING any variant already at (group_id, label)."""
    g = _bank.groups.get(v.group_id)
    if g is None:
        known = ", ".join(_bank.groups) or "none yet"
        return (f"ERROR: no group '{v.group_id}'. Call create_question_group first. "
                f"Existing groups: {known}")
    if g.question_type != v.kind:
        return (f"ERROR: group '{v.group_id}' is question_type='{g.question_type}', but you "
                f"called the {v.kind} tool. Use {_KIND_TO_TOOL[g.question_type]}, or create "
                f"a different group.")

    replacing = v.label in g.variants

    # Two variants that test the same thing are the failure this whole feature exists to
    # prevent; a repeated summary is the cheapest signal of it.
    clash = next((lbl for lbl, x in g.variants.items()
                  if lbl != v.label
                  and x.variant_summary.casefold() == v.variant_summary.casefold()), None)
    if clash:
        return (f"ERROR: in group '{v.group_id}' variant {clash} already has the summary "
                f"'{v.variant_summary}'. Each variant must test a different angle on the "
                f"concept. Write a different question, or a summary that says how this "
                f"one differs.")

    if v.kind == "multiple_choice":
        others = [x for lbl, x in g.variants.items()
                  if lbl != v.label and x.kind == "multiple_choice"]
        # Only enforceable while there are at least as many positions as variants.
        if others and len(others) + 1 <= min(len(x.options) for x in others + [v]):
            taken = {x.correct_index: lbl for lbl, x in g.variants.items()
                     if lbl != v.label and x.kind == "multiple_choice"}
            if v.correct_index in taken:
                free = unused_correct_positions(v.group_id, exclude_label=v.label)
                return (f"ERROR: in group '{v.group_id}' variant {taken[v.correct_index]} already "
                        f"puts the correct answer at index {v.correct_index}. Each variant needs a "
                        f"different position. Free positions: {free}. Reorder the options so the "
                        f"correct one lands on a free index.")

    g.variants[v.label] = v
    _autosave()

    verb = "replaced" if replacing else "stored"
    ack = f"OK {v.group_id}/{v.label} {verb} ({v.kind})."
    n = len(g.variants)
    ack += f" Group {v.group_id}: {n} variant(s)."
    free = unused_correct_positions(v.group_id)
    if free:
        ack += f" Correct-answer positions still free: {free}."
    return ack


def report() -> str:
    """Full listing. Called once, not per turn: tool results are re-sent every turn."""
    if not _bank.groups:
        return "Bank is empty. Call create_question_group first."
    lines = [f"Bank '{_bank.run_id}': {len(_bank.groups)} group(s)."]
    for g in _bank.groups.values():
        labels = ", ".join(sorted(g.variants)) or "NONE"
        lines.append(f"  {g.group_id} [{g.question_type}] {g.concept_title[:48]}")
        lines.append(f"    variants: {labels}")
        for lbl in sorted(g.variants):
            v = g.variants[lbl]
            detail = ""
            if v.kind == "multiple_choice":
                detail = f" correct=index {v.correct_index} of {len(v.options)}"
            elif v.kind == "multiple_answer":
                detail = f" correct=indices {sorted(v.correct_indices)} of {len(v.options)}"
            elif v.kind == "true_false":
                detail = f" answer={v.correct_answer}"
            lines.append(f"      {lbl}: {v.question_text[:56]}{detail}")
    problems = validate_final()
    lines.append("")
    lines.append("Ready to finalize." if not problems
                 else "Not ready:\n" + "\n".join(f"  - {p}" for p in problems))
    return "\n".join(lines)


def validate_final() -> list[str]:
    """Backstop. Empty list means the bank is consistent."""
    problems: list[str] = []
    if not _bank.groups:
        problems.append("bank has no groups")
    for g in _bank.groups.values():
        if not g.variants:
            problems.append(f"group '{g.group_id}' has no variants")
            continue
        if g.question_type == "multiple_choice":
            mc = [v for v in g.variants.values() if v.kind == "multiple_choice"]
            width = min(len(v.options) for v in mc)
            if len(mc) <= width:
                used = [v.correct_index for v in mc]
                if len(set(used)) != len(used):
                    problems.append(
                        f"group '{g.group_id}' reuses a correct-answer position: {sorted(used)}"
                    )
        if g.question_type == "true_false":
            answers = {v.correct_answer for v in g.variants.values() if v.kind == "true_false"}
            if len(g.variants) > 1 and len(answers) < 2:
                problems.append(
                    f"group '{g.group_id}' is all-{answers.pop()}; needs at least one of each"
                )
    return problems


def pick_quiz(seed: int, pick_count: int = 1) -> dict:
    """Choose variants deterministically. Recorded in quiz.json so the pick reproduces."""
    rng = random.Random(seed)
    picks = {}
    for gid in sorted(_bank.groups):
        labels = sorted(_bank.groups[gid].variants)
        if labels:
            picks[gid] = rng.sample(labels, min(pick_count, len(labels)))
    return {
        "quiz_id": f"quiz-{_bank.run_id}",
        "bank_id": _bank.run_id,
        "title": _bank.title,
        "seed": seed,
        "picks": picks,
        "groups": [{"group_id": gid, "pick_count": pick_count, "points": 1}
                   for gid in sorted(_bank.groups) if _bank.groups[gid].variants],
    }


def finalize(seed: int | None = None) -> str:
    """Validate, write artefacts, and only then set the flag."""
    problems = validate_final()
    if problems:
        return ("ERROR: not finalized.\n" + "\n".join(f"  - {p}" for p in problems)
                + "\nFix these with more add_* calls, then call finalize_bank again.")

    from coursekit.emit import gift  # local import: bank.py stays free of serialisation concerns

    if seed is None:
        seed = random.Random(_bank.run_id).randint(1000, 9999)
    quiz = pick_quiz(seed)

    _bank.finalized = True
    _autosave()

    if _out_dir is None:
        return "OK bank valid (no output directory set, nothing written)."

    (_out_dir / "quiz.json").write_text(json.dumps(quiz, indent=2), encoding="utf-8")
    (_out_dir / "bank.gift").write_text(gift.emit_bank(_bank), encoding="utf-8")
    (_out_dir / f"quiz_{seed}.gift").write_text(gift.emit_quiz(quiz, _bank), encoding="utf-8")

    n = sum(len(g.variants) for g in _bank.groups.values())
    return (f"OK finalized: {len(_bank.groups)} groups, {n} variants -> "
            f"bank.json, quiz.json, bank.gift, quiz_{seed}.gift. Stop now.")


def build_variant(kind: str, **kwargs) -> Variant:
    """Construct and validate. Raises ValidationError, which tools.py renders for the model."""
    cls = {"multiple_choice": MCVariant, "multiple_answer": MAVariant,
           "true_false": TFVariant, "short_answer": SAVariant,
           "numerical": NumVariant, "matching": MatchVariant}[kind]
    return cls(**kwargs)


__all__ = [
    "Bank", "Group", "Pair", "Variant", "ValidationError",
    "MCVariant", "MAVariant", "TFVariant", "SAVariant", "NumVariant", "MatchVariant",
    "init", "load", "reset", "get", "is_finalized", "create_group", "put_variant", "report",
    "validate_final", "pick_quiz", "finalize", "build_variant", "unused_correct_positions",
]
