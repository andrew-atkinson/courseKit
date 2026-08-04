"""Error-position probe: does quiz-flag rate rise with a question's POSITION in the generation?

One of the assessment probes for the instruction-crowding question (see agent/roadmap.md, "Composable
generation"). If quality decays as the single generation grows, the output is too long for one pass and
the answer is to DECOMPOSE it — not to trim instructions. This reads a course's archived evaluation runs
off disk (the `evals/<timestamp>/quiz-review.md` snapshots plus the latest `quizzes/quiz-review.md`) and
the `bank.json` files, and reports the flag rate by three position cuts:

  - VARIANT LETTER (A→D)  — within-group emission order; a rising line = the model tiring inside a group.
  - GROUP POSITION third  — early/mid/late group of the week; late elevation = output-scope crowding.
  - LAST group            — the confound check: the last group is usually the abstract "enduring
                            understanding", which flags more for CONTENT reasons; isolating it tells a
                            position effect apart from that content effect.

It needs NO model. Numerator (flags) and denominator (questions) are aligned to the same reviewed weeks,
so the rates are honest. It is only as strong as the archive is deep — a handful of flags is a hint, not
a verdict; it sharpens as more `generate`/`evaluate` runs accumulate in `evals/`.

    uv run python evals/errpos.py "/path/to/course export"
"""

import argparse
import glob
import json
import os
import re
from collections import Counter

# Matches both review formats: "## week-6 · func_comp/C — FLAG" and "[FLAG] week-3 g1/B: …".
_FLAG = re.compile(r"(week-\d+)\s*[·.]*\s*([A-Za-z0-9_]+)/([A-D])\b")


def collect_flags(course: str) -> set[tuple[str, str, str]]:
    """Every flagged (week, group_id, variant_label) across the archived runs + the latest review."""
    flags: set[tuple[str, str, str]] = set()
    reviews = glob.glob(os.path.join(course, "evals", "*", "quiz-review.md"))
    reviews.append(os.path.join(course, "quizzes", "quiz-review.md"))
    for rv in reviews:
        if os.path.exists(rv):
            with open(rv, encoding="utf-8") as f:
                for line in f:
                    m = _FLAG.search(line)
                    if m:
                        flags.add((m.group(1), m.group(2), m.group(3)))
    return flags


def position_table(course: str, reviewed: set[str]) -> dict:
    """Map each variant of the REVIEWED weeks to its position (letter, group-third, is-last-group), so
    the denominator covers exactly the weeks the flags came from."""
    pos = {}
    for bj in sorted(glob.glob(os.path.join(course, "quizzes", "week-*", "bank.json"))):
        week = os.path.basename(os.path.dirname(bj))
        if week not in reviewed:
            continue
        groups = json.load(open(bj, encoding="utf-8")).get("groups", {})
        gids = list(groups)
        for gi, gid in enumerate(gids):
            for label in sorted(groups[gid].get("variants", {})):
                frac = (gi + 1) / len(gids)
                third = "early" if frac <= 1 / 3 else "mid" if frac <= 2 / 3 else "late"
                pos[(week, gid, label)] = dict(letter=label, third=third,
                                               last=(gi == len(gids) - 1))
    return pos


def _cut(pos: dict, matched: list, keyfn, order: list) -> str:
    tot, flg = Counter(), Counter()
    for k in pos:
        tot[keyfn(pos[k])] += 1
    for f in matched:
        flg[keyfn(pos[f])] += 1
    lines = []
    for b in order:
        r = 100 * flg[b] / tot[b] if tot[b] else 0.0
        lines.append(f"  {str(b):10s}: {flg[b]:2d}/{tot[b]:3d} = {r:5.1f}%")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Quiz-flag rate by position in the generation.")
    ap.add_argument("course", help="course root (holds quizzes/ and evals/)")
    args = ap.parse_args()

    flags = collect_flags(args.course)
    reviewed = {f[0] for f in flags}
    pos = position_table(args.course, reviewed)
    matched = [f for f in flags if f in pos]

    if not pos:
        print("No reviewed weeks with a bank.json found — generate + review a course first.")
        return 1

    print(f"reviewed weeks: {sorted(reviewed)}")
    print(f"questions in them: {len(pos)}   flags: {len(flags)}   matched to a bank: {len(matched)}")
    if len(matched) < 20:
        print("!! small sample — read the rates below as DIRECTIONAL, not conclusive; "
              "re-run as more evals/ runs accumulate.")
    print()
    print("── by VARIANT LETTER (within-group emission order) ──")
    print(_cut(pos, matched, lambda p: p["letter"], list("ABCD")))
    print("\n── by GROUP POSITION third ──")
    print(_cut(pos, matched, lambda p: p["third"], ["early", "mid", "late"]))
    print("\n── LAST group (enduring-understanding content confound check) ──")
    print(_cut(pos, matched, lambda p: "last" if p["last"] else "other", ["other", "last"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
