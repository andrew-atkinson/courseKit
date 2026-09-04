"""Groundedness for QUIZZES (EVAL-15, quiz side) — per-variant provenance against the source.

The page version (page/groundedness.py) classifies each PAGE claim; this classifies each QUIZ
QUESTION: does the source actually let a student answer it, or is it testing the model's own knowledge?
That is the exact concern that surfaced EVAL-15 — a targeted quiz on a ~10-word ISO slide produced a
full, correct quiz the model clearly answered from its OWN photography knowledge, not the slide. A
question can be perfectly CORRECT (facticity passes) and still be ungrounded, which quietly breaks the
"a course's OWN material" thesis. So for quizzes the KEY signal is low coverage — a warning the source
is too thin to ground the quiz.

Anchored per-variant (like the facticity quiz critic), so no under-extraction. Attribution-forcing
prompt (grounded requires quoting the material) so topical overlap isn't mistaken for grounding.
Discovery reuses `_iter_quiz_banks`, so it covers whole-week AND targeted quizzes.
"""

import re
from dataclasses import dataclass, field

from coursekit.generate.quiz.evaluate import (
    READ_TEMPERATURE,
    _critic_body,
    _format_question,
    _iter_quiz_banks,
)

GROUNDEDNESS_CATEGORY = "quiz"

# Tolerant: markdown emphasis / colon / spaces around the label, and the `| reason` is optional —
# a reply that ends `GROUNDING: GROUNDED` with no reason must still parse, not silently drop the
# question (a dropped question shrinks the coverage denominator and distorts the score).
_GROUNDING = re.compile(
    r"GROUNDING[\s:*_]*(GROUNDED|TENSION|IN.TENSION|MODEL[\w-]*|NOVEL|SUPPLIED)"
    r"(?:[\s|:*_–-]*(.*))?",
    re.IGNORECASE)


def _tag(raw: str) -> str:
    # Two-tag: does the material ground the question, or not? (A stray TENSION reply — the material
    # engages the question but disagrees with the marked answer — still counts as grounded here;
    # whether the answer is right is facticity's job.)
    r = raw.upper()
    return "model" if r.startswith(("MODEL", "NOVEL", "SUPPLIED")) else "grounded"


def _parse_grounding(reply: str) -> tuple[str, str] | None:
    """(tag, reason) from the critic's `GROUNDING: <TAG> | <reason>` line, or None if unreadable."""
    m = _GROUNDING.search(reply or "")
    return (_tag(m.group(1)), (m.group(2) or "").strip()) if m else None


@dataclass
class GroundItem:
    group_id: str
    label: str
    stem: str
    tag: str            # grounded | model
    note: str = ""


@dataclass
class BankGroundedness:
    quiz_id: str
    items: list[GroundItem] = field(default_factory=list)
    raw: str = ""

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def engaging(self) -> int:
        return sum(1 for it in self.items if it.tag == "grounded")

    @property
    def coverage(self) -> float:
        return self.engaging / self.total if self.total else 0.0

    @property
    def model_supplied(self) -> list[GroundItem]:
        return [it for it in self.items if it.tag == "model"]


def evaluate_bank_groundedness(bank, material: str, provider, model: str, *, quiz_id: str = "",
                               project_root=None, progress=None) -> BankGroundedness:
    """Classify each quiz variant's provenance against the material, question by question. Best-effort:
    a per-question critic error yields no item for that question, never an exception."""
    critic = _critic_body(GROUNDEDNESS_CATEGORY, project_root, name="groundedness")
    items: list[GroundItem] = []
    raw_parts: list[str] = []
    for g in bank.groups.values():
        for v in g.variants.values():
            user = (f"The week's source material:\n<material>\n{material}\n</material>\n\n"
                    f"The quiz question to classify:\n{_format_question(v)}\n\n"
                    f"Classify this question's provenance against the material.")
            messages = [{"role": "system", "content": critic}, {"role": "user", "content": user}]
            try:
                reply = provider.chat(model=model, messages=messages, temperature=READ_TEMPERATURE)
            except Exception as e:
                reply = f"(critic call failed: {e})"
            raw_parts.append(f"## {g.group_id}/{v.label}\n{reply}")
            parsed = _parse_grounding(reply)
            if parsed:
                items.append(GroundItem(g.group_id, v.label, v.question_text.strip(), parsed[0], parsed[1]))
            if progress:
                progress(f"  {quiz_id} {g.group_id}/{v.label} — {parsed[0] if parsed else '?'}")
    return BankGroundedness(quiz_id, items, "\n\n".join(raw_parts))


def render_groundedness(bg: BankGroundedness) -> str:
    if not bg.items:
        return f"# Quiz groundedness — {bg.quiz_id}\n\n(no questions classified)\n"
    lines = [f"# Quiz groundedness — {bg.quiz_id}  "
             f"({bg.coverage * 100:.0f}% answerable from the material · {len(bg.model_supplied)} "
             f"model-knowledge, of {bg.total} question(s))", ""]
    if bg.model_supplied:
        lines.append("**Testing the model's knowledge, not the source** — the material does not supply "
                     "the answer. A low count is fine; a high one means the source is too thin to ground "
                     "this quiz (the questions are correct, but they aren't testing *your* material):")
        lines += [f"- ({it.group_id}/{it.label}) {it.stem} — {it.note}" for it in bg.model_supplied]
        lines.append("")
    lines.append(f"<details><summary>all {bg.total} questions</summary>\n")
    lines += [f"- [{it.tag}] ({it.group_id}/{it.label}) {it.stem}" for it in bg.items]
    lines.append("\n</details>")
    return "\n".join(lines) + "\n"


def evaluate_course_groundedness(path, *, weeks=None, provider, model, out_path=None, progress=None):
    """Classify question provenance for every quiz in a course (whole-week AND targeted) → one
    quiz-groundedness.md. Returns (per-quiz results, out_path_or_None)."""
    from pathlib import Path

    from coursekit import courseconfig
    from coursekit.generate.quiz.bank import Bank

    root = courseconfig.find_root(path) or Path(path).expanduser().resolve()
    results = []
    for slug, bj, tpath, proot in _iter_quiz_banks(path, weeks):
        bank = Bank.model_validate_json(bj.read_text(encoding="utf-8"))
        material = tpath.read_text(encoding="utf-8")
        if progress:
            n = sum(len(g.variants) for g in bank.groups.values())
            progress(f"reading {slug} — {n} question(s)…")
        results.append(evaluate_bank_groundedness(bank, material, provider, model, quiz_id=slug,
                                                   project_root=proot, progress=progress))

    if not results:
        return [], None
    out_path = Path(out_path) if out_path else root / "quizzes" / "quiz-groundedness.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(render_groundedness(r) for r in results), encoding="utf-8")
    return results, out_path
