"""A cold-read critic pass over generated PAGE sections — the pages half of the output-worth evaluator.

Mirrors quiz/evaluate.py: a fresh read of each content block against the week's material, flagging
sections that drift from the material, assert something it does not support, define a term wrongly, or
show broken code. It is the facticity gate for the narrative page — the same defence against
plausible-but-wrong output the quiz critic gives the questions. Report-only; a human stays in the loop.

Reuses the generic critic machinery from quiz/evaluate.py (verdict parsing, the union, the Finding
record, render_review); only per-block formatting and page discovery are page-specific. A shared critic
core is worth extracting once a third consumer appears — not before (same discipline as the rename).
"""

from pathlib import Path

from coursekit.generate.quiz.evaluate import (
    DEFAULT_READS,
    READ_TEMPERATURE,
    Finding,
    _critic_body,
    _parse_verdict,
    _union,
    render_review,
)

PAGE_CATEGORY = "page"

# A heading is a section label, not a factual claim — nothing to cold-read. Everything else carries
# content the material has to support.
_SKIP_KINDS = {"heading"}


def _format_block(b) -> str:
    """Render one block as the critic sees it — its kind plus the content that must be faithful."""
    kind = b.kind
    if kind == "bullets":
        return "[bullets]\n" + "\n".join(f"- {i}" for i in b.items)
    if kind == "glossary":
        return "[glossary]\n" + "\n".join(f"{e.term} — {e.definition}" for e in b.entries)
    if kind == "code":
        return f"[code{(' ' + b.language) if b.language else ''}]\n{b.code}"
    if kind == "callout":
        return f"[callout/{b.tone}]\n{b.text}"
    if kind == "card":
        return f"[card/{b.card_kind}] {b.title}\n{b.text}"
    if kind == "details":
        return f"[details] {b.summary}\n{b.text}"
    if kind == "columns":
        return "[columns]\n" + "\n".join(f"  {c.title}: " + "; ".join(c.items) for c in b.columns)
    if kind == "image":
        return f"[image] {b.alt}" + (f" — {b.caption}" if getattr(b, "caption", None) else "")
    # paragraph, pullquote, and any future text block
    return f"[{kind}]\n{getattr(b, 'text', '')}"


def _preview(b) -> str:
    """A short human label for a block in the review (goes in the Finding's subject line)."""
    for attr in ("text", "summary", "code"):
        if getattr(b, attr, None):
            return getattr(b, attr)
    if getattr(b, "items", None):
        return "; ".join(b.items)
    if getattr(b, "entries", None):
        return "; ".join(f"{e.term}: {e.definition}" for e in b.entries)
    if getattr(b, "columns", None):
        return " | ".join(c.title for c in b.columns)
    return b.kind


def _one_read(critic: str, material: str, b, provider, model: str,
              *, seed: int | None = None) -> tuple[str, str, str]:
    user = (f"The week's teaching material:\n<material>\n{material}\n</material>\n\n"
            f"The page section to review:\n{_format_block(b)}\n\nEvaluate this section.")
    messages = [{"role": "system", "content": critic}, {"role": "user", "content": user}]
    kwargs = {"model": model, "messages": messages, "temperature": READ_TEMPERATURE}
    if seed is not None:
        kwargs["seed"] = seed
    try:
        return _parse_verdict(provider.chat(**kwargs))
    except Exception as e:                       # one flaky read must not abort the review
        return "ERROR", f"critic call failed: {e}"[:160], ""


def evaluate_page(page, material: str, provider, model: str, *, week: str = "",
                  project_root=None, reads: int = DEFAULT_READS, progress=None) -> list[Finding]:
    """Cold-read every content block of a page against the week's material. `progress(msg)`, when
    given, is called after each section — a live heartbeat for a slow local model."""
    critic = _critic_body(PAGE_CATEGORY, project_root)
    findings = []
    for b in page.blocks.values():
        if b.kind in _SKIP_KINDS:
            continue
        results = [_one_read(critic, material, b, provider, model) for _ in range(max(1, reads))]
        verdict, concern, fix, n_flag = _union(results)
        if progress:
            progress(f"  {'⚑' if verdict == 'FLAG' else '·'} {week} {b.block_id} ({b.kind}) — {verdict}")
        findings.append(Finding(week, b.block_id, b.kind, _preview(b).strip(),
                                verdict, concern, fix, n_flag=n_flag, n_reads=len(results)))
    return findings


def evaluate_course_pages(path, *, weeks=None, provider, model, out_path=None,
                          reads: int = DEFAULT_READS, progress=None) -> tuple[list[Finding], Path | None]:
    """Discover a course's weeks, pair each `page.json` with its transcript, cold-read every section,
    and write one `page-review.md`. Returns (findings, review_path_or_None). `progress(msg)` gives a
    per-week / per-section heartbeat."""
    from coursekit.discover import find_units
    from coursekit.generate.page.page import Page
    from coursekit.pipeline import _week_matches

    units = find_units(path, subdir="pages")
    if weeks:
        units = [u for u in units if any(_week_matches(w, u) for w in weeks)]

    findings: list[Finding] = []
    for u in units:
        pj = Path(u.output_dir) / "page.json"
        if not pj.exists():
            continue
        page = Page.model_validate_json(pj.read_text(encoding="utf-8"))
        material = Path(u.transcript_path).read_text(encoding="utf-8")
        n = sum(1 for b in page.blocks.values() if b.kind not in _SKIP_KINDS)
        if progress:
            progress(f"cold-reading {u.week_slug} — {n} section(s)…")
        findings += evaluate_page(page, material, provider, model, week=u.week_slug,
                                  project_root=u.course_root, reads=reads, progress=progress)

    if not findings:
        return [], None
    if out_path is None:
        out_path = Path(units[0].output_dir).parent / "page-review.md"     # the course's pages/ tree
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_review(findings, title="Page review", noun="section"), encoding="utf-8")
    return findings, out_path
