"""Compare two saved scorecard runs question-by-question (evals/results/*.md).

Parses the per-question tables from two run files and, over the questions they share, reports each
model's recall / false-flag and every question where their verdicts differ — so a slow reasoning model
can be judged against a fast one on exactly the cases that matter, with no re-running.

    uv run python evals/compare.py evals/results/<runA>.md evals/results/<runB>.md
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coursekit.generate.quiz.scoring import parse_cases_table, summarize_rows


def _model_of(text: str) -> str:
    m = re.search(r"model:\s*`([^`]+)`", text)
    return m.group(1) if m else "?"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file_a")
    ap.add_argument("file_b")
    args = ap.parse_args()

    ta, tb = Path(args.file_a).read_text(encoding="utf-8"), Path(args.file_b).read_text(encoding="utf-8")
    ra, rb = parse_cases_table(ta), parse_cases_table(tb)
    common = sorted(set(ra) & set(rb))
    if not common:
        print("no overlapping questions between the two runs", file=sys.stderr)
        return 1

    ca, cb = {k: ra[k] for k in common}, {k: rb[k] for k in common}
    (reca, fpra), (recb, fprb) = summarize_rows(ca), summarize_rows(cb)

    print(f"\ncomparing {len(common)} shared question(s)\n")
    print(f"  A = {_model_of(ta)}")
    print(f"  B = {_model_of(tb)}\n")
    print(f"  recall      A {reca}   B {recb}")
    print(f"  false-flag  A {fpra}   B {fprb}\n")

    diffs = [k for k in common if ca[k]["verdict"] != cb[k]["verdict"]]
    if not diffs:
        print("  the two models agreed on every shared question.\n")
        return 0
    print(f"  {len(diffs)} disagreement(s):")
    print(f"    {'question':16} {'expected':16} {'A':6} {'B':6}")
    for k in diffs:
        print(f"    {k[0] + '/' + k[1]:16} {ca[k]['expected']:16} {ca[k]['verdict']:6} {cb[k]['verdict']:6}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
