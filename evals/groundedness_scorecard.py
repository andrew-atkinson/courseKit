"""Calibrate the groundedness critic (EVAL-15) — does it read provenance right?

Three pages over the same coding material (page/groundedness_fixtures.py), whose claim provenance is
known. A working critic moves the aggregates the right way:
  - grounded — claims faithfully from the material → HIGH coverage, no tension.
  - model    — claims true but off-topic          → LOW coverage (mostly model-supplied).
  - tension  — claims that contradict the material → at least one tension flagged.

    uv run python evals/groundedness_scorecard.py
    uv run python evals/groundedness_scorecard.py --model qwen/qwen3.6-27b
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from coursekit.generate.page import groundedness as gnd
from coursekit.generate.page.groundedness_fixtures import (
    CODING_MATERIAL,
    grounded_page,
    model_supplied_page,
    near_miss_page,
    tension_page,
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

    def read(name, page):
        print(f"reading the {name} page …", file=sys.stderr)
        return gnd.evaluate_page_groundedness(page, CODING_MATERIAL, provider, model)

    g = read("grounded", grounded_page())
    m = read("model-supplied", model_supplied_page())
    n = read("near-miss", near_miss_page())
    t = read("tension", tension_page())

    checks = [
        (f"grounded: coverage HIGH ({g.coverage*100:.0f}%)", g.coverage >= 0.8),
        (f"grounded: no tension ({len(g.tensions)})", len(g.tensions) == 0),
        (f"model (blatant off-topic): coverage LOW ({m.coverage*100:.0f}%)", m.coverage <= 0.5),
        # THE HARD ONE — on-topic-but-not-in-material must NOT read as grounded (the 'marble' failure).
        (f"near-miss (on-topic added): coverage LOW ({n.coverage*100:.0f}%)", n.coverage <= 0.5),
        (f"tension: >=1 flagged ({len(t.tensions)})", len(t.tensions) >= 1),
    ]
    print(f"\n=== groundedness calibration · model={model} ===")
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    passed = sum(ok for _, ok in checks)
    print(f"\n{passed}/{len(checks)} checks passed.")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
