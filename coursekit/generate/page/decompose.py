"""PROTOTYPE — per-concept decomposed page generation (the composable-generation experiment).

Instead of ONE monolithic pass over the whole week transcript, build the page as focused passes that
write into the shared page IR in order:

  1. a FRAME pass (hook + the enduring-understanding pullquote),
  2. one pass PER concept — seeing only that concept's keyword-SLICED material (a few K chars, not the
     whole 30-128K-char week: the token-accounting probe showed the transcript is 80-92% of the prompt,
     so shrinking per-pass material is the real lever),
  3. a CLOSE pass (summary + a retrieval `details`).

Because the passes run in concept-map order and each emits its heading THEN its content, the assembler
is implicit and the heading-order failure (all headings dumped at the end) is structurally impossible.

Writes to a separate `<course>/pages-decomposed/<week>/` tree so it sits beside the monolithic page for
an A/B, scored by the same evaluators. EXPERIMENTAL — not wired into the CLI.

    uv run python -m coursekit.generate.page.decompose "/path/to/course" --week 7 [--review]
"""

import argparse
import os
import re
from pathlib import Path

from coursekit import courseconfig, prompts
from coursekit.discover import find_units, slugify
from coursekit.generate.page import page as pageir
from coursekit.generate.page import tools
from coursekit.generate.page.concept_map import load_for_unit
from coursekit.providers.base import Reply

_ADD_SPECS = [s for s in tools.TOOL_SPECS if s["name"].startswith("add_")]
_STOP = {"a", "an", "the", "and", "or", "of", "to", "in", "is", "it", "for", "with", "that",
         "this", "as", "on", "by", "be", "are", "we", "you", "your", "how", "what", "why", "its"}


# --------------------------------------------------------------------- material slicing (deterministic)
def _keywords(concept) -> set[str]:
    words: set[str] = set()
    for src in [concept.name, concept.gist, *(concept.components or [])]:
        for w in re.findall(r"[A-Za-z0-9_]+", (src or "").lower()):
            if len(w) >= 4 and w not in _STOP:
                words.add(w)
    return words


def slice_material(transcript: str, concept, *, max_chars: int = 2500) -> str:
    """A keyword-relevance slice of the transcript for ONE concept — the crux of the decomposition.
    Chunks the transcript on blank lines, scores each chunk by how many of the concept's keywords it
    contains, takes the highest-scoring chunks (in document order) up to a small budget. Falls back to
    the head of the transcript when nothing matches."""
    chunks = [c.strip() for c in re.split(r"\n\s*\n", transcript) if c.strip()]
    if not chunks:
        return transcript[:max_chars]
    kw = _keywords(concept)
    scored = [(sum(1 for k in kw if k in c.lower()), i, c) for i, c in enumerate(chunks)]
    if max((s for s, _, _ in scored), default=0) == 0:      # nothing matched — head of the transcript
        return transcript[:max_chars]
    picked: list[tuple[int, str]] = []
    total = 0
    for score, i, c in sorted(scored, key=lambda t: (-t[0], t[1])):
        if score == 0 and picked:
            break
        if picked and total + len(c) > max_chars:
            break
        picked.append((i, c))
        total += len(c)
    if not picked:
        return transcript[:max_chars]
    picked.sort()
    return "\n\n".join(c for _, c in picked)


# --------------------------------------------------------------------- the passes (model-driven)
def _run_pass(provider, model, system: str, user: str, *, max_turns: int = 8,
              max_nudges: int = 3) -> int:
    """Drive one bounded tool-call pass that writes blocks into the shared page IR. Returns the number
    of blocks it added. The model calls `add_*` tools; when it replies in PROSE without having produced
    anything, nudge it back to tool calls (the small model narrates instead of calling tools) — the same
    remedy the monolithic loop and the fix loop use. A prose reply AFTER blocks exist means the section
    is simply done."""
    before = len(pageir.get().blocks)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    nudges = 0
    for _ in range(max_turns):
        try:
            reply = provider.chat_with_tools(model=model, messages=messages, tools=_ADD_SPECS)
        except Exception:
            break
        if reply.wants_tools:
            provider.append_assistant(messages, reply)
            provider.append_tool_results(messages, tools.run_tool_calls(reply.tool_calls))
            continue
        if len(pageir.get().blocks) > before or nudges >= max_nudges:
            break                                   # produced its blocks then stopped, or gave up
        nudges += 1
        provider.append_assistant(messages, Reply(finish_reason=reply.finish_reason,
                                                  content=reply.content))
        provider.append_user(messages, "Record this section now by CALLING the add_* tools; "
                                        "do not reply in prose.")
    return len(pageir.get().blocks) - before


def _brief(concept) -> str:
    lines = [f"Concept: {concept.name}"]
    if concept.gist:
        lines.append(f"Why it matters: {concept.gist}")
    if concept.level:
        lines.append(f"Level (Bloom): {concept.level}")
    if concept.components:
        lines.append("Knowledge components: " + ", ".join(concept.components))
    return "\n".join(lines)


def _neighbour_context(concepts, i: int) -> str:
    """A sliding window for coherence: tell the current concept's pass what sits BEFORE and AFTER it, by
    name + gist only (not their material — that keeps the token win and stops the model teaching a
    neighbour). Edges point at the page's opening / closing instead."""
    def label(c):
        return f"{c.name} — {c.gist}" if c.gist else c.name
    prev = label(concepts[i - 1]) if i > 0 else "the page's opening (the hook and the key idea)"
    nxt = label(concepts[i + 1]) if i < len(concepts) - 1 else "the closing summary"
    return (f"This section follows: {prev}.\nIt leads into: {nxt}.\n"
            f'Open by connecting to what came before and end by pointing toward what comes next — '
            f'but teach ONLY "{concepts[i].name}", never a neighbour.')


def generate_page_decomposed(unit, provider, model, out_dir, *, project_root=None, neighbours=True):
    """Build the page for `unit` by frame → per-concept → close passes into `out_dir`. Returns
    (page, problems) where problems is `validate_final()` (empty means it finalized). `neighbours` adds
    the prev/next coherence window to each concept pass (name+gist only)."""
    project_root = project_root or unit.course_root
    cfg = unit.config
    cm = load_for_unit(unit)
    if cm is None or not cm.concepts:
        raise SystemExit(f"{unit.week_slug}: no concept map (run `analyze` first).")
    transcript = Path(unit.transcript_path).read_text(encoding="utf-8", errors="replace")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(unit.week_label) if unit.week_label else unit.week_slug
    pageir.init(page_id=f"{unit.course_slug}-{unit.week_slug}", out_dir=out_dir,
                title=unit.week_label or unit.week_slug, page_type="week_intro",
                week_ref=unit.week_slug, slug=slug)
    tools.reset_state()
    tools.set_call_log(out_dir / "calls.jsonl")

    dpre, vpre = courseconfig.domain_preface(cfg.domain), courseconfig.voice_preface(cfg.voice)

    def sysmsg(name):
        return dpre + vpre + prompts.load("page", name, project_root=project_root).body

    names = ", ".join(c.name for c in cm.concepts)
    eu = cm.enduring_understanding or "(none stated)"

    n = _run_pass(provider, model, sysmsg("frame"),
                  f"Topic: {unit.week_label or unit.week_slug}\nEnduring understanding: {eu}\n"
                  f"Concepts this week: {names}")
    print(f"  frame: +{n} block(s)")

    # Boundary-correct per-concept material from `analyze` (one contiguous verbatim span per concept, so
    # the example travels with its definition); fall back to the keyword slicer per concept when absent.
    from coursekit.generate.page import segment as seg
    materials = seg.load_materials_for_unit(unit) or {}

    full = len(transcript)
    for i, c in enumerate(cm.concepts):
        # The heading text IS the concept name — place it deterministically (in order), so every
        # concept becomes its own titled section and the model only has to fill the content beneath it.
        pageir.put_block(pageir.build_block("heading", block_id=f"sec-{i}", text=c.name, role="concept"))
        material = materials.get(c.name) or slice_material(transcript, c)
        src = "map" if materials.get(c.name) else "slice"
        window = ("\n\n" + _neighbour_context(cm.concepts, i)) if neighbours else ""
        n = _run_pass(provider, model, sysmsg("concept_section"),
                      f"{_brief(c)}{window}\n\nThe material for this concept:\n"
                      f"<material>\n{material}\n</material>")
        print(f"  {c.name[:34]:34s} [{src}]: {len(material):5d}/{full} chars → +{n} content block(s)")

    # Same deterministic-heading treatment as the concepts — place the summary heading first so the
    # close pass can only add content beneath it (last run it emitted the heading last → empty section).
    pageir.put_block(pageir.build_block("heading", block_id="sec-summary", text="Wrapping Up",
                                        role="summary"))
    n = _run_pass(provider, model, sysmsg("close"),
                  f"Concepts this week: {names}\nEnduring understanding: {eu}")
    print(f"  close: +{n} content block(s)")

    problems = pageir.validate_final()
    if not problems:
        pageir.finalize()
    else:
        print("  (did not finalize: " + "; ".join(problems) + ")")
    _render(unit, out_dir, project_root)
    return pageir.get(), problems


def _render(unit, out_dir, project_root) -> None:
    """Best-effort HTML render beside page.json — mirrors the monolithic generator + fix loop."""
    try:
        from coursekit.emit import html as html_emit
        from coursekit.generate.page.renderer import load_supplements
        from coursekit.generate.page.style import load_style
        supplements = load_supplements(project_root, unit.week_slug)
        html_emit.write_html(pageir.get(), Path(out_dir), supplements, load_style(project_root))
    except Exception as e:
        print(f"  (render skipped: {type(e).__name__}: {e})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Prototype: per-concept decomposed page generation.")
    ap.add_argument("course")
    ap.add_argument("--week", required=True, help="week number (e.g. 7) or label")
    ap.add_argument("--review", action="store_true",
                    help="also cold-read the result and print the flag count (extra model calls)")
    ap.add_argument("--no-neighbours", action="store_true",
                    help="drop the prev/next coherence window (A/B: does the window help?)")
    args = ap.parse_args()

    units = [u for u in find_units(args.course)
             if u.week_slug.split("-")[-1] == args.week or u.week_label == args.week]
    if not units:
        print(f"No unit for week {args.week!r} under {args.course}.")
        return 1
    unit = units[0]

    from coursekit.cli import _build_provider
    provider = _build_provider()
    model = os.getenv("MODEL_NAME") or courseconfig.load(
        args.course, config_name="page.yaml").value("model")

    out_dir = Path(unit.course_root) / "pages-decomposed" / unit.week_slug
    print(f"Decomposed generation → {out_dir}")
    pg, problems = generate_page_decomposed(unit, provider, model, out_dir,
                                            neighbours=not args.no_neighbours)
    headings = sum(1 for b in pg.blocks.values() if b.kind == "heading")
    print(f"\n{len(pg.blocks)} block(s), {headings} section heading(s), "
          f"{'finalized' if not problems else 'NOT finalized'}")

    if args.review:
        from coursekit.generate.page import evaluate as pev
        material = Path(unit.transcript_path).read_text(encoding="utf-8", errors="replace")
        findings = pev.evaluate_page(pg, material, provider, model, week=unit.week_slug,
                                     project_root=unit.course_root)
        flagged = [f for f in findings if f.flagged]
        print(f"\ncold read: {len(flagged)}/{len(findings)} section(s) flagged")
        for f in flagged:
            print(f"  [{f.verdict}] {f.group_id}: {f.concern}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
