"""Score the PAGE critic against the synthetic page set — the model-in-the-loop measurement harness.

The pages analogue of evals/scorecard.py: cold-reads every labelled section (page/synthesize.py) with
the real page critic and prints recall by flaw type, false-flag rate on the sound sections, and per
domain — reusing the same scoring math (coursekit.generate.quiz.scoring). Every run is saved to
evals/results/<timestamp>-<model>-pages-r<reads>.md.

    uv run python evals/page_scorecard.py
    uv run python evals/page_scorecard.py --model qwen/qwen3.6-27b

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

from coursekit.generate.page import evaluate as pev
from coursekit.generate.page.synthesize import synthesize_all_hard_pages, synthesize_all_pages
from coursekit.generate.quiz import scoring
from coursekit.providers import get_provider


def main() -> int:
    load_dotenv(override=True)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=os.getenv("MODEL_NAME"),
                    help="critic model id (defaults to MODEL_NAME; LM Studio JIT-loads a known id)")
    ap.add_argument("--reads", type=int, default=1)
    ap.add_argument("--domains", default="",
                    help="comma-separated subset of domains to run (default: all)")
    ap.add_argument("--hard", action="store_true",
                    help="use the HARD set (subtle near-miss / beyond-material flaws) instead of the blatant one")
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

    wanted = {d.strip() for d in args.domains.split(",") if d.strip()}
    page_sets = synthesize_all_hard_pages() if args.hard else synthesize_all_pages()
    cases: list[scoring.CaseResult] = []
    for name, ds in page_sets.items():
        if wanted and name not in wanted:
            continue
        n = len(ds.page.blocks)
        print(f"reading {name} ({n} sections × {args.reads}) …", file=sys.stderr)
        findings = pev.evaluate_page(ds.page, ds.transcript, provider, model, reads=args.reads)
        for f in findings:
            flaw = ds.expected[f.group_id]["flaw"]        # None for the sound (PASS) sections
            cases.append(scoring.CaseResult(name, f.group_id, flaw, tuple([f.verdict] * f.n_reads)))

    sc = scoring.build_scorecard(cases, model=model, n_reads=args.reads)
    print("\n" + scoring.render(sc))

    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-")
    tag = "pages-hard" if args.hard else "pages"
    out = results_dir / f"{stamp}-{slug}-{tag}-r{args.reads}.md"
    out.write_text(
        f"# Page critic scorecard\n\n"
        f"- model: `{model}`\n- reads: {args.reads}\n- when: {stamp}\n\n"
        f"```\n{scoring.render(sc)}```\n\n"
        f"## Per-section detail\n\n{scoring.render_cases(cases)}",
        encoding="utf-8")
    print(f"saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
