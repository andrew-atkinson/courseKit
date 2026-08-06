"""Glossary COMPANION pages — the short 'terms beside the video' review artifact (a page FUNCTION).

A glossary companion is not a compressed teaching page; it is a different artifact with a smaller job:
the week's key terms + one-line definitions, for a student to review beside the lecture video. Because
its length is bounded by the number of terms (not the transcript's length), it sidesteps the problem
the removed `--detail` knob hit — "be brief about text you can't see the extent of." Brevity here is a
property of the FUNCTION, not a per-pass directive.

Extraction is model-driven — one bounded tool-call pass per material chunk, calling only `add_glossary`,
grounded ONLY in the week's material — while assembly and dedup are deterministic. Writes to the
canonical `pages/<week>-glossary/` tree so evaluate/fix/emit see it, and renders with the week's
supplements, so an instructor-supplied video embed appears beside the terms automatically.

    uv run python -m coursekit.generate.page.glossary "/path/to/course" --week 7
"""

import argparse
import os
from pathlib import Path

from coursekit import courseconfig, prompts
from coursekit.discover import find_units, slugify
from coursekit.generate.page import decompose
from coursekit.generate.page import page as pageir
from coursekit.generate.page import tools

_GLOSSARY_SPECS = [s for s in tools.TOOL_SPECS if s["name"] == "add_glossary"]


def _harvest_new_glossary() -> list[dict]:
    """Pull every glossary block currently in the IR out into plain term/definition dicts and REMOVE
    the blocks. Called after each chunk pass so the next pass's (often same-block_id) glossary can't
    overwrite this chunk's terms — accumulation lives here, deterministically, not in the IR."""
    pg = pageir.get()
    out = []
    for bid in [bid for bid, b in list(pg.blocks.items()) if b.kind == "glossary"]:
        out += [{"term": e.term, "definition": e.definition} for e in pg.blocks[bid].entries]
        del pg.blocks[bid]
    return out


def build_glossary_page(unit, provider, model, out_dir, *, project_root=None):
    """Build the week's glossary companion into `out_dir`. Returns (page, problems); problems empty
    means it finalized. One `add_glossary` pass per material chunk; terms are harvested per chunk and
    deduped into one glossary block deterministically."""
    project_root = project_root or unit.course_root
    cfg = unit.config
    transcript = Path(unit.transcript_path).read_text(encoding="utf-8", errors="replace")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = slugify(unit.week_label) if unit.week_label else unit.week_slug
    pageir.init(page_id=f"{unit.course_slug}-{unit.week_slug}-glossary", out_dir=out_dir,
                title=f"{unit.week_label or unit.week_slug} — Key Terms", page_type="glossary",
                week_ref=unit.week_slug, slug=f"{base}-glossary")
    tools.reset_state()
    tools.set_call_log(out_dir / "calls.jsonl")

    # The single section heading is placed deterministically; the pass only fills the terms beneath it.
    pageir.put_block(pageir.build_block("heading", block_id="terms-h", text="Key Terms", role="review"))

    system = (courseconfig.domain_preface(cfg.domain)
              + prompts.load("page", "glossary", project_root=project_root).body)
    budget = int(cfg.value("max_pass_chars", decompose.DEFAULT_PASS_CHARS))
    chunks = decompose._material_chunks(transcript, budget)   # long weeks → bounded passes, nothing dropped
    stats: dict = {}

    def _extract() -> list[dict]:
        collected: list[dict] = []
        for k, chunk in enumerate(chunks):
            cont = ("" if len(chunks) == 1 else
                    f"\n\n(This is part {k + 1} of {len(chunks)} of the material; add any NEW terms it "
                    f"introduces — do not repeat terms already covered.)")
            decompose._run_pass(provider, model, system,
                                f"The week's material:\n<material>\n{chunk}\n</material>{cont}",
                                specs=_GLOSSARY_SPECS, stats=stats)
            collected += _harvest_new_glossary()
        return collected

    collected = _extract()
    retries = 0
    while not collected and retries < decompose.RETRY_EMPTY:   # an empty glossary is a flaky pass — retry fresh
        retries += 1
        collected = _extract()

    seen: dict[str, dict] = {}                                   # dedup by term, first definition wins
    for e in collected:
        seen.setdefault(e["term"].strip().lower(), e)
    if seen:
        pageir.put_block(pageir.build_block("glossary", block_id="terms", entries=list(seen.values())))
    print(f"  glossary: {len(seen)} term(s){f' (retry{retries})' if retries else ''}"
          f"{f' over {len(chunks)} chunk(s)' if len(chunks) > 1 else ''}")

    if stats.get("errors"):
        from collections import Counter
        kinds = ", ".join(f"{k}×{v}" for k, v in Counter(stats["error_types"]).items())
        print(f"  ⚠ {stats['errors']} pass error(s) — candidate timeouts/overheating: {kinds}")

    problems = pageir.validate_final()
    if not problems:
        pageir.finalize()
    else:
        print("  (did not finalize: " + "; ".join(problems) + ")")
    decompose._render(unit, out_dir, project_root)
    return pageir.get(), problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a week's glossary companion (the 'terms beside the "
                                             "video' review page).")
    ap.add_argument("course")
    ap.add_argument("--week", required=True, help="week number (e.g. 7) or label")
    args = ap.parse_args()

    units = [u for u in find_units(args.course)
             if u.week_slug.split("-")[-1] == args.week or u.week_label == args.week]
    if not units:
        print(f"No unit for week {args.week!r} under {args.course}.")
        return 1
    unit = units[0]

    from coursekit.cli import _build_provider
    provider = _build_provider()
    cfg = courseconfig.load(args.course, config_name="page.yaml")
    model = os.getenv("MODEL_NAME") or cfg.value("model")

    out_dir = Path(unit.course_root) / "pages" / f"{unit.week_slug}-glossary"
    print(f"Glossary companion → {out_dir}")
    pg, problems = build_glossary_page(unit, provider, model, out_dir)
    print(f"\n{len(pg.blocks)} block(s), {'finalized' if not problems else 'NOT finalized'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
