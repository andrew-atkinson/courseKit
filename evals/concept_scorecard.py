"""Calibrate the concept-delivery rubric — does it score a page that DELIVERS the concepts above ones
that deliver them poorly?

Scores one well-delivered coding page and three deficient variants (concepts merely named; explained but
no example; explained in jargon above the level — page/concept_fixtures.py). A working rubric gives the
good page the highest average concept score and each variant a lower one.

    uv run python evals/concept_scorecard.py
    uv run python evals/concept_scorecard.py --model qwen/qwen3.6-27b
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from coursekit.generate.page import concept_delivery as cd
from coursekit.generate.page.concept_fixtures import CODING_MATERIAL, VARIANTS, good_page
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

    print("scoring the good page …", file=sys.stderr)
    good = cd.evaluate_page_concepts(good_page(), CODING_MATERIAL, provider, model)

    rows, passes = [], 0
    for name, make in VARIANTS.items():
        print(f"scoring the {name} variant …", file=sys.stderr)
        v = cd.evaluate_page_concepts(make(), CODING_MATERIAL, provider, model)
        discriminates = v.average < good.average
        passes += discriminates
        rows.append((name, v.average, len(v.concepts), discriminates))

    lines = [f"=== concept-delivery calibration · model={model} ===\n",
             f"good page: avg {good.average:.2f}/3 over {len(good.concepts)} concept(s)\n",
             f"{'variant':14} {'avg':>6} {'concepts':>9} {'lower than good?':>17}"]
    for name, avg, n, ok in rows:
        lines.append(f"{name:14} {avg:>6.2f} {n:>9} {('yes' if ok else 'NO'):>17}")
    lines.append(f"\ndiscrimination: {passes}/{len(VARIANTS)} variants scored below the good page")
    report = "\n".join(lines)
    print("\n" + report + "\n")

    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-")
    out = results_dir / f"{stamp}-{slug}-concepts.md"
    out.write_text(f"# Concept-delivery calibration\n\n- model: `{model}`\n- when: {stamp}\n\n"
                   f"```\n{report}\n```\n\n## Good page, full breakdown\n\n{cd.render_concepts(good)}",
                   encoding="utf-8")
    print(f"saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
