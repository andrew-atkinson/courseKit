"""Calibrate the QUIZ groundedness critic (EVAL-15) — does it read provenance right?

Banks over the same short material (quiz/groundedness_fixtures.py):
  - grounded — questions the material answers        → HIGH coverage.
  - model    — correct but not-in-material questions  → LOW coverage (the thin-source warning).
  - mixed    — n of 4 grounded + the rest model       → coverage ~ n/4 (75% / 50% / 25%), so the
               critic's within-quiz discrimination is visible, not just the pure extremes.

    uv run python evals/quiz_groundedness_scorecard.py
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from coursekit.generate.quiz import groundedness as gnd
from coursekit.generate.quiz.groundedness_fixtures import (
    MATERIAL,
    grounded_bank,
    mixed_bank,
    model_supplied_bank,
)
from coursekit.providers import get_provider


def main() -> int:
    load_dotenv(override=True)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=os.getenv("MODEL_NAME"))
    args = ap.parse_args()
    model = args.model
    if not model:
        print("no model given (pass --model or set MODEL_NAME)", file=sys.stderr)
        return 2
    provider = get_provider(os.getenv("PROVIDER", "lm_studio"), base_url=os.getenv("LOCAL_HOST_URL"))
    try:
        provider.chat(model=model, messages=[{"role": "user", "content": "reply OK"}], temperature=0)
    except Exception as e:
        print(f"no reachable model ({type(e).__name__}); start your provider", file=sys.stderr)
        return 2

    def read(name, bank):
        print(f"reading the {name} bank …", file=sys.stderr)
        return gnd.evaluate_bank_groundedness(bank, MATERIAL, provider, model)

    g = read("grounded", grounded_bank())
    m = read("model-supplied", model_supplied_bank())

    checks = [
        (f"grounded: coverage HIGH ({g.coverage*100:.0f}%)", g.coverage >= 0.8),
        (f"model (not in source): coverage LOW ({m.coverage*100:.0f}%)", m.coverage <= 0.5),
    ]
    banks = [("grounded", g, 2), ("model", m, 2)]
    # mixed banks: n/4 grounded → expect coverage ~ n/4. Coverage is a multiple of 0.25, so
    # tolerance 0.13 means "exactly right" — one misjudged question moves it a full 0.25 and fails.
    for n, want in ((3, 0.75), (2, 0.50), (1, 0.25)):
        mx = read(f"mixed-{n}g", mixed_bank(n))
        banks.append((f"mixed-{n}g", mx, 4))
        checks.append((f"mixed {n}/4 grounded: coverage ~{want*100:.0f}% ({mx.coverage*100:.0f}%)",
                       abs(mx.coverage - want) <= 0.13))
    print(f"\n=== quiz groundedness calibration · model={model} ===")
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    passed = sum(ok for _, ok in checks)
    print(f"\n{passed}/{len(checks)} checks passed.")

    # Per-question tags — the point of the mixed banks: SEE which question the critic flipped/dropped.
    print("\n--- per-question verdicts (G=grounded · M=model · a MISSING count = unparsed/dropped) ---")
    for name, bg, n_expected in banks:
        tags = " ".join(f"[{it.tag[0].upper()}] {it.stem[:40]}" for it in bg.items)
        drop = "" if len(bg.items) == n_expected else f"  ⚠️ {n_expected - len(bg.items)} dropped"
        print(f"{name}: {tags or '(none)'}{drop}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
