"""Token-accounting probe: what is the generation prompt actually MADE of?

The companion to errpos.py for the instruction-crowding question (agent/roadmap.md, "Composable
generation"). errpos tests burden #2 (output scope — does quality decay as the output grows); this
tests burden #1 (instruction load — how much standing instruction sits in the prompt, and how much of
it is each thing). It builds the REAL quiz + page prompts for a course's weeks (no model — just assembles
the message strings the generator would send) and decomposes each into:

  transcript · shipped instructions (system rules + task brief) · concept-map directive · domain · voice

If the transcript dwarfs the instructions, trimming rules buys little and the lever is decomposing the
output (feed less material per pass); if instructions are a large share, routing/trimming them matters.
Sizes are characters, with ~tokens ≈ chars/4 (no tokenizer dependency; the RATIOS are the point).

    uv run python evals/tokacct.py "/path/to/course export"            # every week, quiz + page
    uv run python evals/tokacct.py "/path/to/course export" --week 7
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coursekit import courseconfig
from coursekit.discover import find_units
from coursekit.generate.page import context as pctx
from coursekit.generate.page.concept_map import load_for_unit
from coursekit.generate.quiz import context as qctx


def _total(msgs) -> int:
    return sum(len(m["content"]) for m in msgs)


def decompose(kind: str, unit) -> dict | None:
    """Character breakdown of one generator's prompt for one week, by component."""
    cfg = unit.config
    transcript = Path(unit.transcript_path).read_text(encoding="utf-8", errors="replace")
    cm = load_for_unit(unit)
    common = dict(course_title=unit.course_title, week_label=unit.week_label, module=unit.module,
                  project_root=unit.course_root, domain=cfg.domain, voice=cfg.voice)

    if kind == "quiz":
        full = qctx.build_messages(transcript, concept_map=cm, **common)
        no_cm = qctx.build_messages(transcript, concept_map=None, **common)
        voice_chars = len(courseconfig.quiz_voice_preface(cfg.voice))
    else:
        full = pctx.build_messages(transcript, concept_map=cm, **common)
        no_cm = pctx.build_messages(transcript, concept_map=None, **common)
        voice_chars = len(courseconfig.voice_preface(cfg.voice))

    total = _total(full)
    domain_chars = len(courseconfig.domain_preface(cfg.domain))
    cm_chars = total - _total(no_cm)                     # the concept map's contribution, by differencing
    transcript_chars = len(transcript)                    # woven in verbatim, once
    instructions = total - transcript_chars - domain_chars - voice_chars - cm_chars
    return {"total": total, "transcript": transcript_chars, "instructions": instructions,
            "concept map": cm_chars, "domain": domain_chars, "voice": voice_chars}


ORDER = ["transcript", "instructions", "concept map", "domain", "voice"]


def _print(kind: str, rows: list[tuple[str, dict]]) -> None:
    print(f"\n=== {kind.upper()} prompt composition (chars; ~tokens ≈ /4) ===")
    agg = {k: 0 for k in ORDER}
    tot = 0
    for week, d in rows:
        tot += d["total"]
        for k in ORDER:
            agg[k] += d[k]
        parts = "  ".join(f"{k}={100*d[k]/d['total']:4.1f}%" for k in ORDER)
        print(f"  {week:9s} {d['total']:6d}c  {parts}")
    if len(rows) > 1 and tot:
        parts = "  ".join(f"{k}={100*agg[k]/tot:4.1f}%" for k in ORDER)
        print(f"  {'ALL':9s} {tot:6d}c  {parts}")
    # the standing-overhead headline: everything that is NOT the week's own material
    if tot:
        overhead = tot - agg["transcript"]
        print(f"  standing overhead (all but transcript): {100*overhead/tot:.1f}%  "
              f"(~{overhead//4} tokens across {len(rows)} week(s))")


def main() -> int:
    ap = argparse.ArgumentParser(description="Composition of the generation prompt, by component.")
    ap.add_argument("course")
    ap.add_argument("--week", action="append", help="restrict to these week numbers")
    args = ap.parse_args()

    units = find_units(args.course)
    if args.week:
        wanted = set(args.week)
        units = [u for u in units if u.week_slug.split("-")[-1] in wanted or u.week_label in wanted]
    if not units:
        print("No units found (need generated week text under the course).")
        return 1

    for kind in ("quiz", "page"):
        rows = []
        for u in sorted(units, key=lambda u: u.week_slug):
            try:
                rows.append((u.week_slug, decompose(kind, u)))
            except Exception as e:            # a week missing its text/map shouldn't sink the probe
                print(f"  ({u.week_slug} {kind}: skipped — {type(e).__name__}: {e})")
        if rows:
            _print(kind, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
