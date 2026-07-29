"""A pedagogy rubric over a WHOLE page — how well it reads and teaches, not whether it is true.

The facticity critic (page/evaluate.py) asks "is this section correct?" per block. This asks a different
question of the whole page: does it scan, signal its key idea, engage, show worked examples and
contrast, and prompt retrieval? Grounded in CLT + UDL (the frames the page generator itself was built
on, see docs/design.md). The output is a rubric — each criterion scored 0-3 with a one-line note — not a
FLAG/PASS verdict, because pedagogical quality is graded, not binary. Report-only; a coaching artifact.

The v1 criteria are the five with the biggest lift that are checkable on one page:
SCANNABILITY, SIGNALING, ENGAGEMENT, WORKED_EXAMPLES, RETRIEVAL. (Spacing/interleaving is deliberately
NOT here — real spacing is a course-schedule property, a future course-level evaluator.)
"""

import re
from dataclasses import dataclass, field

from coursekit import prompts
from coursekit.generate.page.evaluate import _format_block
from coursekit.generate.quiz.evaluate import READ_TEMPERATURE

PEDAGOGY_CATEGORY = "page"

CRITERIA = ("SCANNABILITY", "SIGNALING", "ENGAGEMENT", "WORKED_EXAMPLES", "RETRIEVAL")

_LINE = re.compile(
    r"^(SCANNABILITY|SIGNALING|ENGAGEMENT|WORKED_EXAMPLES|RETRIEVAL)\s*:\s*([0-3])\s*\|?\s*(.*)$",
    re.IGNORECASE | re.MULTILINE)


@dataclass
class RubricScore:
    criterion: str
    score: int          # 0-3, or -1 when the critic's reply could not be read for this criterion
    note: str = ""


@dataclass
class PageRubric:
    page_id: str
    scores: dict[str, RubricScore] = field(default_factory=dict)
    raw: str = ""       # the critic's full reply, for debugging a bad parse

    @property
    def total(self) -> int:
        return sum(s.score for s in self.scores.values() if s.score >= 0)


def _render_page(page) -> str:
    """The whole page as the rubric sees it — headings carry their role/level (scannability depends on
    that structure), every other block via the facticity critic's per-block formatter."""
    parts = []
    for b in page.blocks.values():
        if b.kind == "heading":
            role = f" role={b.role}" if getattr(b, "role", None) else ""
            parts.append(f"## [heading level={b.level}{role}] {b.text}")
        else:
            parts.append(_format_block(b))
    return "\n\n".join(parts)


def _parse_rubric(reply: str) -> dict[str, tuple[int, str]]:
    """Pull `NAME: <0-3> | <note>` lines out of the reply. Lenient: a criterion the model omitted or
    mangled is simply absent (the caller marks it -1) rather than crashing the review."""
    out: dict[str, tuple[int, str]] = {}
    for m in _LINE.finditer(reply or ""):
        out[m.group(1).upper()] = (int(m.group(2)), m.group(3).strip())
    return out


def evaluate_page_pedagogy(page, material: str, provider, model: str, *, project_root=None) -> PageRubric:
    """Score one page against the five criteria. Best-effort: a provider error or an unreadable reply
    yields -1 scores, never an exception."""
    critic = prompts.load(PEDAGOGY_CATEGORY, "pedagogy", project_root=project_root).body
    user = (f"The week's teaching material:\n<material>\n{material}\n</material>\n\n"
            f"The full page, in order:\n{_render_page(page)}\n\nScore this page.")
    messages = [{"role": "system", "content": critic}, {"role": "user", "content": user}]
    try:
        reply = provider.chat(model=model, messages=messages, temperature=READ_TEMPERATURE)
    except Exception as e:
        reply = f"(critic call failed: {e})"
    parsed = _parse_rubric(reply)
    scores = {c: RubricScore(c, *parsed.get(c, (-1, "not scored"))) for c in CRITERIA}
    return PageRubric(page.page_id, scores, reply)


def render_rubric(rubric: PageRubric) -> str:
    lines = [f"# Page pedagogy — {rubric.page_id}  (total {rubric.total}/{3 * len(CRITERIA)})", ""]
    for c in CRITERIA:
        s = rubric.scores[c]
        shown = "?" if s.score < 0 else str(s.score)
        lines.append(f"- **{c}** {shown}/3 — {s.note}")
    return "\n".join(lines) + "\n"


def evaluate_course_pedagogy(path, *, weeks=None, provider, model, out_path=None):
    """Score every generated page in a course on the rubric and write one page-pedagogy.md. Returns
    (rubrics, out_path_or_None) — for reviewing already-generated pages without regenerating."""
    from pathlib import Path

    from coursekit.discover import find_units
    from coursekit.generate.page.page import Page
    from coursekit.pipeline import _week_matches

    units = find_units(path, subdir="pages")
    if weeks:
        units = [u for u in units if any(_week_matches(w, u) for w in weeks)]

    rubrics = []
    for u in units:
        pj = Path(u.output_dir) / "page.json"
        if not pj.exists():
            continue
        page = Page.model_validate_json(pj.read_text(encoding="utf-8"))
        material = Path(u.transcript_path).read_text(encoding="utf-8")
        rub = evaluate_page_pedagogy(page, material, provider, model, project_root=u.course_root)
        rub.page_id = u.week_slug        # label by week for a course-level report
        rubrics.append(rub)

    if not rubrics:
        return [], None
    if out_path is None:
        out_path = Path(units[0].output_dir).parent / "page-pedagogy.md"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(render_rubric(r) for r in rubrics), encoding="utf-8")
    return rubrics, out_path
