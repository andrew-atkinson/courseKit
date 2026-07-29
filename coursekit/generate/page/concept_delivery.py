"""Concept-delivery evaluation — the THIRD kind of page check.

Facticity (page/evaluate.py) asks "is it correct?"; the pedagogy rubric (page/pedagogy.py) asks "does it
scan/signal/engage?" (form). This asks the question that is the whole point of a page: **does it actually
deliver the concepts the week is meant to teach?** The critic first identifies the core concepts from the
MATERIAL, then scores how well the PAGE delivers each — clear explanation, a worked example, the right
level — 0–3 per concept. Report-only; a coaching artifact, graded not binary.

Reuses the domain-aware review loader (`_critic_body`) and the whole-page renderer (`_render_page`).
"""

import re
from dataclasses import dataclass, field

from coursekit.generate.page.pedagogy import _render_page
from coursekit.generate.quiz.evaluate import READ_TEMPERATURE, _critic_body

CONCEPT_CATEGORY = "page"

# One "- <concept>: <0-3> | <note>" line per concept.
_LINE = re.compile(r"^[-*]\s*(.+?):\s*([0-3])\s*\|\s*(.*)$", re.MULTILINE)


@dataclass
class ConceptScore:
    concept: str
    score: int          # 0-3
    note: str = ""


@dataclass
class PageConcepts:
    page_id: str
    concepts: list[ConceptScore] = field(default_factory=list)
    raw: str = ""

    @property
    def average(self) -> float:
        scored = [c.score for c in self.concepts if c.score >= 0]
        return sum(scored) / len(scored) if scored else 0.0


def _parse_concepts(reply: str) -> list[tuple[str, int, str]]:
    """Pull the `- <concept>: <0-3> | <note>` lines. Lenient — a mangled line is skipped, not fatal."""
    out = []
    for m in _LINE.finditer(reply or ""):
        name = m.group(1).strip().lstrip("*").strip()
        if name.upper() == "CONCEPTS":          # ignore a stray header that happens to match
            continue
        out.append((name, int(m.group(2)), m.group(3).strip()))
    return out


def evaluate_page_concepts(page, material: str, provider, model: str, *, project_root=None) -> PageConcepts:
    """Identify the week's concepts from the material and score the page's delivery of each. Best-effort:
    a provider error or an unreadable reply yields no concepts, never an exception."""
    critic = _critic_body(CONCEPT_CATEGORY, project_root, name="concept_delivery")
    user = (f"The week's teaching material:\n<material>\n{material}\n</material>\n\n"
            f"The full page, in order:\n{_render_page(page)}\n\n"
            f"Judge how well the page delivers each core concept.")
    messages = [{"role": "system", "content": critic}, {"role": "user", "content": user}]
    try:
        reply = provider.chat(model=model, messages=messages, temperature=READ_TEMPERATURE)
    except Exception as e:
        reply = f"(critic call failed: {e})"
    concepts = [ConceptScore(n, s, note) for n, s, note in _parse_concepts(reply)]
    return PageConcepts(page.page_id, concepts, reply)


def render_concepts(pc: PageConcepts) -> str:
    if not pc.concepts:
        return f"# Concept delivery — {pc.page_id}\n\n(no concepts parsed)\n"
    lines = [f"# Concept delivery — {pc.page_id}  "
             f"(avg {pc.average:.1f}/3 over {len(pc.concepts)} concept(s))", ""]
    for c in pc.concepts:
        shown = "?" if c.score < 0 else str(c.score)
        lines.append(f"- **{c.concept}** {shown}/3 — {c.note}")
    return "\n".join(lines) + "\n"
