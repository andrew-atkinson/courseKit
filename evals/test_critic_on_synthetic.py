"""LLM eval — the quiz critic's judgment across domains, with a live model.

NOT part of the offline `tests/` suite: it needs a model, is slow and non-deterministic, so it lives
outside `testpaths`, skips cleanly when no model is reachable, and asserts *tolerant* regression
guards rather than exact matches. Its real output is the printed per-domain scorecard.

Fixtures: `examples/synthetic/<domain>/` (coding, biology, prelaw, photo). Each has a transcript that
is the only material the critic may trust, a bank of sound questions + planted flaws, and an
`expected.json` answer key. Run:

    uv run pytest evals/ -s                 # -s to see the scorecard
    EVAL_READS=5 uv run pytest evals/ -s    # more cold reads per question (better recall, more calls)
"""

import json
import os
from pathlib import Path

import pytest

from coursekit import courseconfig
from coursekit.generate.quiz import evaluate as ev
from coursekit.providers import get_provider

SYNTH = Path(__file__).resolve().parents[1] / "examples" / "synthetic"
DOMAINS = sorted(p.name for p in SYNTH.iterdir() if (p / "expected.json").exists()) if SYNTH.is_dir() else []


def _provider_and_model():
    model = os.getenv("MODEL_NAME") or courseconfig.load(str(SYNTH), config_name="evaluate.yaml").value("model")
    if not model:
        pytest.skip("no critic model configured (set MODEL_NAME, or evaluate.yaml `model:`)")
    provider = get_provider(os.getenv("PROVIDER", "lm_studio"), base_url=os.getenv("LOCAL_HOST_URL"))
    try:
        provider.chat(model=model, messages=[{"role": "user", "content": "reply with OK"}], temperature=0)
    except Exception as e:
        pytest.skip(f"no reachable model ({type(e).__name__}); start your provider to run evals")
    return provider, model


def _score(domain, provider, model, reads):
    """(true_flag, missed, false_flag, true_pass) for one domain, vs its expected.json."""
    course = SYNTH / domain
    expected = json.loads((course / "expected.json").read_text())
    findings, _ = ev.evaluate_course(str(course), provider=provider, model=model, reads=reads)
    by = {f.group_id: f for f in findings}
    tp = miss = fp = tn = 0
    for gid, exp in expected.items():
        got = by[gid].flagged if gid in by else False
        want = exp["verdict"] == "FLAG"
        tp += want and got
        miss += want and not got
        fp += (not want) and got
        tn += (not want) and (not got)
    return tp, miss, fp, tn


def test_critic_stats_across_domains():
    provider, model = _provider_and_model()
    assert DOMAINS, "no synthetic domains found under examples/synthetic/"
    reads = int(os.getenv("EVAL_READS", ev.DEFAULT_READS))

    rows, TP = [], [0, 0, 0, 0]
    for d in DOMAINS:
        tp, miss, fp, tn = _score(d, provider, model, reads)
        for i, val in enumerate((tp, miss, fp, tn)):
            TP[i] += val
        rec = tp / (tp + miss) if (tp + miss) else 1.0
        fpr = fp / (fp + tn) if (fp + tn) else 0.0
        rows.append((d, tp + miss, tp, miss, fp, rec, fpr))

    tp, miss, fp, tn = TP
    recall = tp / (tp + miss) if (tp + miss) else 1.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    print(f"\n\n=== critic eval · model={model} · {reads} reads/question ===")
    print(f"{'domain':9} {'flaws':>6} {'caught':>7} {'missed':>7} {'false+':>7} {'recall':>7} {'FPR':>6}")
    for d, n, c, m, f, r, fr in rows:
        print(f"{d:9} {n:>6} {c:>7} {m:>7} {f:>7} {r:>6.0%} {fr:>5.0%}")
    print(f"{'ALL':9} {tp + miss:>6} {tp:>7} {miss:>7} {fp:>7} {recall:>6.0%} {fpr:>5.0%}\n")

    # tolerant regression guards (the scorecard above is the real signal)
    assert recall >= 0.70, f"aggregate recall {recall:.0%} below the 70% guard"
    assert fpr <= 0.35, f"false-flag rate {fpr:.0%} above the 35% guard"
