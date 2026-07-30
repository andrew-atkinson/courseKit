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


def evaluate_page_concepts(page, material: str, provider, model: str, *, project_root=None,
                           concepts: list[str] | None = None) -> PageConcepts:
    """Score the page's delivery of each core concept. When `concepts` is given (from the week's
    consolidated concept map), score against THAT fixed list — no re-derivation, so the scored set is
    stable across reads and matches what generation was told to teach; otherwise the critic identifies
    the concepts from the material itself. Best-effort: a provider error or an unreadable reply yields
    no concepts, never an exception."""
    critic = _critic_body(CONCEPT_CATEGORY, project_root, name="concept_delivery")
    if concepts:
        given = "\n".join(f"- {c}" for c in concepts)
        task = (f"The week's concepts are already identified — score the page's delivery of each of "
                f"these, and only these:\n{given}")
    else:
        task = "Judge how well the page delivers each core concept."
    user = (f"The week's teaching material:\n<material>\n{material}\n</material>\n\n"
            f"The full page, in order:\n{_render_page(page)}\n\n{task}")
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


def evaluate_course_concepts(path, *, weeks=None, provider, model, out_path=None):
    """Score concept delivery for every generated page in a course and write one page-concepts.md.
    Returns (per-page results, out_path_or_None) — for reviewing already-generated pages."""
    from pathlib import Path

    from coursekit import courseconfig
    from coursekit.discover import find_units
    from coursekit.generate.page.concept_map import concept_map_path, load_concept_map
    from coursekit.generate.page.page import Page
    from coursekit.pipeline import _week_matches

    units = find_units(path, subdir="pages")
    if weeks:
        units = [u for u in units if any(_week_matches(w, u) for w in weeks)]

    results = []
    for u in units:
        pj = Path(u.output_dir) / "page.json"
        if not pj.exists():
            continue
        page = Page.model_validate_json(pj.read_text(encoding="utf-8"))
        material = Path(u.transcript_path).read_text(encoding="utf-8")
        # Score against the week's concept map when one exists — a fixed list, not a re-derivation.
        names = None
        key = courseconfig.week_key(u.week_slug) if u.course_root else None
        if key:
            try:
                cmap = load_concept_map(concept_map_path(u.course_root, key))
            except Exception:
                cmap = None
            if cmap and cmap.concepts:
                names = [c.name for c in cmap.concepts]
        pc = evaluate_page_concepts(page, material, provider, model, project_root=u.course_root,
                                    concepts=names)
        pc.page_id = u.week_slug         # label by week for the course report
        results.append(pc)

    if not results:
        return [], None
    if out_path is None:
        out_path = Path(units[0].output_dir).parent / "page-concepts.md"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(render_concepts(r) for r in results), encoding="utf-8")
    return results, out_path
