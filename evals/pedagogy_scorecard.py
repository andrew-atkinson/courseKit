"""Calibrate the page pedagogy rubric — does it discriminate a well-built page from deficient variants?

Scores one well-made coding page and, for each of the five criteria, a variant with that dimension's
blocks removed (page/pedagogy_fixtures.py). A working rubric scores the good page high on every
criterion and each variant LOW on exactly its missing one. Prints a discrimination table and saves it.

    uv run python evals/pedagogy_scorecard.py
    uv run python evals/pedagogy_scorecard.py --model qwen/qwen3.6-27b

Needs a reachable model — MODEL_NAME + LOCAL_HOST_URL from .env, PROVIDER defaults to lm_studio.
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from coursekit.generate.page import pedagogy as ped
from coursekit.generate.page.pedagogy_fixtures import CODING_MATERIAL, deficient_page, good_page
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
    good = ped.evaluate_page_pedagogy(good_page(), CODING_MATERIAL, provider, model)

    rows, passes = [], 0
    for crit in ped.CRITERIA:
        print(f"scoring the no-{crit.lower()} variant …", file=sys.stderr)
        variant = ped.evaluate_page_pedagogy(deficient_page(crit), CODING_MATERIAL, provider, model)
        g, d = good.scores[crit].score, variant.scores[crit].score
        discriminates = d < g          # the variant should score lower on the dimension it dropped
        passes += discriminates
        rows.append((crit, g, d, discriminates))

    header = f"=== pedagogy rubric calibration · model={model} ===\n"
    lines = [header,
             f"{'criterion':16} {'good':>5} {'deficient':>10} {'discriminates?':>15}"]
    for crit, g, d, ok in rows:
        gs = "?" if g < 0 else str(g)
        ds = "?" if d < 0 else str(d)
        lines.append(f"{crit:16} {gs:>5} {ds:>10} {('yes' if ok else 'NO'):>15}")
    lines.append(f"\ndiscrimination: {passes}/{len(ped.CRITERIA)} criteria "
                 f"(good scores higher than its deficient variant)")
    lines.append(f"\ngood page total: {good.total}/{3 * len(ped.CRITERIA)}")
    report = "\n".join(lines)
    print("\n" + report + "\n")

    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-")
    out = results_dir / f"{stamp}-{slug}-pedagogy.md"
    out.write_text(
        f"# Page pedagogy rubric — calibration\n\n- model: `{model}`\n- when: {stamp}\n\n"
        f"```\n{report}\n```\n\n## Good page, full rubric\n\n{ped.render_rubric(good)}",
        encoding="utf-8")
    print(f"saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
