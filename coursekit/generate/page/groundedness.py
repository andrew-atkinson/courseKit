"""Groundedness evaluation — the FOURTH kind of page check (EVAL-15). BLOCK-ANCHORED.

Facticity asks "is it correct?"; pedagogy "does it scan/signal/engage?"; concept-delivery "does it
teach the concepts?". This asks a question orthogonal to all three — **where does each claim come
from?** Its PROVENANCE relative to the week's material. Two axes:
  - COVERAGE — does a claim engage the material at all? (grounded/tension) vs (model-supplied).
  - CONCORD — of the engaging claims, do they AGREE (grounded) or CONTRADICT (tension)?
Descriptive: 'model-supplied' is information for a cognizant instructor, not a defect; only a TENSION
(a contradiction of the material) is flagged.

**Anchored to the page's own blocks** (like the facticity page critic), NOT one whole-page call. The
first version let the model choose what to measure across the whole page in a single read — it skimmed
a 42-block page down to 11 obvious (grounded) claims, so coverage flattered to 100%. Here every content
block is examined, so the denominator is the page's real structure, not the model's whim.

Read alongside facticity a tension is diagnostic: tension + facticity PASS ≈ the model corrected a
wrong SOURCE (upstream); tension + facticity FAIL ≈ a model error to fix.
"""

import re
from dataclasses import dataclass, field

from coursekit.generate.page.evaluate import _SKIP_KINDS, _format_block
from coursekit.generate.quiz.evaluate import READ_TEMPERATURE, _critic_body

GROUNDEDNESS_CATEGORY = "page"

# one "- <claim>: <TAG> | <note>" line per claim; lenient on the tag spelling.
_LINE = re.compile(r"^[-*]\s*(.+?):\s*(GROUNDED|TENSION|IN.TENSION|MODEL[\w-]*|NOVEL|SUPPLIED)\s*\|\s*(.*)$",
                   re.IGNORECASE | re.MULTILINE)


def _tag(raw: str) -> str:
    r = raw.upper()
    if r.startswith("GROUND"):
        return "grounded"
    if "TENSION" in r:
        return "tension"
    return "model"          # MODEL / MODEL-SUPPLIED / NOVEL / SUPPLIED


@dataclass
class Claim:
    text: str
    tag: str            # grounded | tension | model
    note: str = ""
    block_id: str = ""


@dataclass
class PageGroundedness:
    page_id: str
    claims: list[Claim] = field(default_factory=list)
    raw: str = ""       # the per-block critic replies, kept for debugging a surprising number

    @property
    def total(self) -> int:
        return len(self.claims)

    @property
    def engaging(self) -> int:               # claims that draw on the material (grounded + tension)
        return sum(1 for c in self.claims if c.tag in ("grounded", "tension"))

    @property
    def coverage(self) -> float:             # fraction of claims that engage the faculty's material
        return self.engaging / self.total if self.total else 0.0

    @property
    def tensions(self) -> list[Claim]:
        return [c for c in self.claims if c.tag == "tension"]

    @property
    def model_supplied(self) -> list[Claim]:
        return [c for c in self.claims if c.tag == "model"]


def _parse_claims(reply: str) -> list[Claim]:
    """Pull the `- <claim>: <TAG> | <note>` lines. Lenient — a mangled line is skipped, not fatal."""
    out = []
    for m in _LINE.finditer(reply or ""):
        text = m.group(1).strip().lstrip("*").strip()
        if text.startswith("<") and text.endswith(">"):   # model sometimes echoes the <claim> template
            text = text[1:-1].strip()
        if text.upper() == "CLAIMS":                 # ignore a stray header that matches
            continue
        out.append(Claim(text, _tag(m.group(2)), m.group(3).strip()))
    return out


def evaluate_page_groundedness(page, material: str, provider, model: str, *, week: str = "",
                               project_root=None, progress=None) -> PageGroundedness:
    """Classify the claims in EACH content block by provenance against the material, block by block, so
    every section is examined. Best-effort: a per-block critic error yields no claims for that block,
    never an exception."""
    critic = _critic_body(GROUNDEDNESS_CATEGORY, project_root, name="groundedness")
    claims: list[Claim] = []
    raw_parts: list[str] = []
    for b in page.blocks.values():
        if b.kind in _SKIP_KINDS:                    # a heading is a label, not a claim to trace
            continue
        user = (f"The week's source material:\n<material>\n{material}\n</material>\n\n"
                f"The page section to classify:\n{_format_block(b)}\n\n"
                f"Classify each substantive claim in THIS section by its provenance against the material.")
        messages = [{"role": "system", "content": critic}, {"role": "user", "content": user}]
        try:
            reply = provider.chat(model=model, messages=messages, temperature=READ_TEMPERATURE)
        except Exception as e:
            reply = f"(critic call failed: {e})"
        raw_parts.append(f"## {b.block_id} ({b.kind})\n{reply}")
        block_claims = _parse_claims(reply)
        for c in block_claims:
            c.block_id = b.block_id
        claims += block_claims
        if progress:
            g = sum(1 for c in block_claims if c.tag == "grounded")
            progress(f"  {week} {b.block_id} ({b.kind}) — {len(block_claims)} claim(s), {g} grounded")
    return PageGroundedness(page.page_id, claims, "\n\n".join(raw_parts))


def render_groundedness(pg: PageGroundedness) -> str:
    if not pg.claims:
        return f"# Groundedness — {pg.page_id}\n\n(no claims parsed)\n"
    lines = [f"# Groundedness — {pg.page_id}  "
             f"({pg.coverage * 100:.0f}% engage the material · {len(pg.model_supplied)} model-supplied "
             f"· {len(pg.tensions)} in tension, of {pg.total} claim(s))", ""]
    if pg.tensions:
        lines.append("**In tension with the material** — a contradiction; read against facticity: a "
                     "tension facticity PASSES suggests the *source* is wrong (upstream), one it FLAGS "
                     "is a model error to fix:")
        lines += [f"- ⚠️ ({c.block_id}) {c.text} — {c.note}" for c in pg.tensions]
        lines.append("")
    if pg.model_supplied:
        lines.append("**Model-supplied** — not in the material; the model's own knowledge. Not a defect, "
                     "but the LLM speaking rather than the faculty's material — worth a look for scope:")
        lines += [f"- ({c.block_id}) {c.text} — {c.note}" for c in pg.model_supplied]
        lines.append("")
    # full transparency — every classified claim, so a surprising split is inspectable, not opaque
    lines.append(f"<details><summary>all {pg.total} claims</summary>\n")
    lines += [f"- [{c.tag}] ({c.block_id}) {c.text}" for c in pg.claims]
    lines.append("\n</details>")
    return "\n".join(lines) + "\n"


def evaluate_course_groundedness(path, *, weeks=None, provider, model, out_path=None, progress=None):
    """Classify claim provenance for every generated page in a course → one page-groundedness.md.
    Returns (per-page results, out_path_or_None)."""
    from pathlib import Path

    from coursekit.discover import find_units
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
        n = sum(1 for b in page.blocks.values() if b.kind not in _SKIP_KINDS)
        if progress:
            progress(f"reading {u.week_slug} — {n} section(s)…")
        pg = evaluate_page_groundedness(page, material, provider, model, week=u.week_slug,
                                        project_root=u.course_root, progress=progress)
        pg.page_id = u.week_slug             # label by week for the course report
        results.append(pg)

    if not results:
        return [], None
    if out_path is None:
        out_path = Path(units[0].output_dir).parent / "page-groundedness.md"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(render_groundedness(r) for r in results), encoding="utf-8")
    return results, out_path
