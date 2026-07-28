"""LLM eval suite — coursekit's judgment *with a live model*.

This is deliberately NOT part of the offline unit suite (`tests/`, which is fully offline and
deterministic). These exercise the real model, so they are slow, non-deterministic, and need a model
up — assertions are therefore *tolerant* (regression guards, not exact-match). Each test skips
cleanly when no model is reachable, so it never blocks a machine without one.

    uv run pytest evals/            # with LM Studio (or your provider) running

The fixture is `examples/synthetic-course`: a transcript that is the ONLY material the critic may
trust, plus a bank with one sound question (c1) and four planted flaws (c2 out-of-scope, c3
missing-context, c4 garbled-syntax, c5 wrong-answer). See its EXPECTED.md.
"""

import os
from pathlib import Path

import pytest

from coursekit import courseconfig
from coursekit.generate.quiz import evaluate as ev
from coursekit.providers import get_provider

SYNTH = str(Path(__file__).resolve().parents[1] / "examples" / "synthetic-course")


def _provider_and_model():
    """A reachable provider+model, or a clean skip — so the suite is a no-op without a model."""
    model = os.getenv("MODEL_NAME") or courseconfig.load(SYNTH, config_name="evaluate.yaml").value("model")
    if not model:
        pytest.skip("no critic model configured (set MODEL_NAME, or evaluate.yaml `model:`)")
    provider = get_provider(os.getenv("PROVIDER", "lm_studio"), base_url=os.getenv("LOCAL_HOST_URL"))
    try:
        provider.chat(model=model, messages=[{"role": "user", "content": "reply with OK"}],
                      temperature=0)
    except Exception as e:  # not reachable — skip rather than fail
        pytest.skip(f"no reachable model ({type(e).__name__}); start your provider to run evals")
    return provider, model


def test_critic_judgment_on_the_synthetic_course():
    """The critic should PASS the sound question and catch the planted flaws. Tolerant of run-to-run
    variance and of c5 (wrong-answer, the hardest — needs the model to trace the loop): the guard is
    'don't false-flag the good one, and catch at least 3 of the 4 flaws, including the out-of-scope'."""
    provider, model = _provider_and_model()
    findings, _ = ev.evaluate_course(SYNTH, provider=provider, model=model)
    by = {f.group_id: f for f in findings}

    assert set(by) >= {"c1", "c2", "c3", "c4", "c5"}, "the synthetic bank changed shape"
    assert by["c1"].verdict == "PASS", f"false-flagged the sound question: {by['c1'].concern!r}"
    assert by["c2"].flagged, "missed the out-of-scope question (p5.FFT is never taught) — the flagship check"

    caught = [g for g in ("c2", "c3", "c4", "c5") if by[g].flagged]
    assert len(caught) >= 3, f"critic caught only {caught} of the four planted flaws"
