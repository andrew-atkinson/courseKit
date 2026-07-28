"""Score the quiz critic against the synthetic set — the model-in-the-loop measurement harness.

Runs the cold-read critic over every synthesized domain (coursekit.generate.quiz.synthesize), gathers
each question's per-read verdicts, and prints the scorecard from coursekit.generate.quiz.scoring:
recall by flaw type, false-flag rate on the sound questions, per-read vs union, and the read-
disagreement rate that says whether multi-read is doing anything on this model.

Every run is saved to evals/results/<timestamp>-<model>-r<reads>.md (the scorecard + a per-question
table), so runs and models can be compared after the fact.

Not a pytest (it is the deliverable output, not a pass/fail gate). Run it directly:

    uv run python evals/scorecard.py                       # 1 read (default), seeds on if honoured
    uv run python evals/scorecard.py --reads 5             # more cold reads
    uv run python evals/scorecard.py --model qwen/qwen3.6-35b-a3b   # a different critic model (LM Studio JIT-loads it)
    uv run python evals/scorecard.py --seed-base none      # seeds off, to compare read variance

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

from coursekit.generate.quiz import evaluate as ev
from coursekit.generate.quiz import scoring
from coursekit.generate.quiz.synthesize import synthesize_all
from coursekit.providers import get_provider


def _seed_supported(provider, model) -> bool:
    """LM Studio versions vary on whether they honour `seed`; a rejected seed would error every read.
    Probe once and degrade to seed-less rather than tanking the whole run."""
    try:
        provider.chat(model=model, messages=[{"role": "user", "content": "reply OK"}],
                      temperature=0, seed=1)
        return True
    except Exception as e:
        print(f"note: endpoint rejected `seed` ({type(e).__name__}); running without it", file=sys.stderr)
        return False


def main() -> int:
    load_dotenv(override=True)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=os.getenv("MODEL_NAME"),
                    help="critic model id (defaults to MODEL_NAME; LM Studio JIT-loads a known id)")
    ap.add_argument("--reads", type=int, default=int(os.getenv("EVAL_READS", ev.DEFAULT_READS)))
    ap.add_argument("--seed-base", default="1000",
                    help="integer base for per-read seeds, or 'none' to send no seed")
    ap.add_argument("--domains", default="",
                    help="comma-separated subset of domains to run (default: all), e.g. --domains coding")
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

    seed_base = None
    if args.seed_base.lower() != "none":
        seed_base = int(args.seed_base) if _seed_supported(provider, model) else None

    wanted = {d.strip() for d in args.domains.split(",") if d.strip()}
    cases: list[scoring.CaseResult] = []
    for name, ds in synthesize_all().items():
        if wanted and name not in wanted:
            continue
        print(f"reading {name} ({len(ds.bank.groups)} questions × {args.reads}) …", file=sys.stderr)
        rows = ev.read_verdicts(ds.bank, ds.transcript, provider, model,
                                reads=args.reads, seed_base=seed_base)
        for gid, _label, _stem, verdicts in rows:
            flaw = ds.expected[gid]["flaw"]        # None for the sound (PASS) cases
            cases.append(scoring.CaseResult(name, gid, flaw, tuple(verdicts)))

    sc = scoring.build_scorecard(cases, model=model, n_reads=args.reads)
    seeds_note = f"on, base {seed_base}" if seed_base is not None else "off"
    print("\n" + scoring.render(sc))
    print(f"(seeds {seeds_note})\n")

    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-")
    out = results_dir / f"{stamp}-{slug}-r{args.reads}.md"
    out.write_text(
        f"# Critic scorecard\n\n"
        f"- model: `{model}`\n- reads: {args.reads}\n- seeds: {seeds_note}\n- when: {stamp}\n\n"
        f"```\n{scoring.render(sc)}```\n\n"
        f"## Per-question detail\n\n{scoring.render_cases(cases)}",
        encoding="utf-8")
    print(f"saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
