"""Calibration fixtures for QUIZ groundedness (EVAL-15) over the SAME short material whose
per-question provenance is known:
  - grounded — questions the material actually answers        → HIGH coverage.
  - model    — questions true & on-topic but NOT in the source (the thin-source case) → LOW coverage.
  - mixed    — n of 4 grounded + the rest model → coverage ~ n/4, so the critic's within-quiz
               discrimination is visible at 75% / 50% / 25%, not just the pure 100% / 0% extremes.
"""

from coursekit.generate.quiz.bank import Bank, Group, MCVariant

MATERIAL = ("A for loop repeats a block of code a set number of times. The loop "
            "`for (let i = 0; i < 5; i++)` runs five times — i takes 0, 1, 2, 3, 4. The condition "
            "`i < 5` is checked before each pass.")

# Question pools over MATERIAL: (question, options, correct_index).
# GROUNDED — the material states or entails the answer; MODEL — correct but not in this material.
_GROUNDED_Q = [
    ("How many times does `for (let i = 0; i < 5; i++)` run?", ["3", "5", "10"], 1),
    ("When is the condition `i < 5` checked?", ["before each pass", "after each pass"], 0),
    ("What values does i take across the loop?", ["0, 1, 2, 3, 4", "1, 2, 3, 4, 5", "0 through 5"], 0),
    ("What does a for loop do?",
     ["repeats a block a set number of times", "runs a block once", "defines a function"], 0),
]
_MODEL_Q = [
    ("What does Python's `range(5)` produce?", ["0..4", "1..5", "a string"], 0),
    ("Which keyword exits a JavaScript loop early?", ["break", "stop", "exit"], 0),
    ("How is a JavaScript array's length read?", [".length", ".size", ".count"], 0),
    ("What does a `while` loop check its condition against?",
     ["a boolean expression", "a counter only", "the array length"], 0),
]

__all__ = ["MATERIAL", "grounded_bank", "model_supplied_bank", "mixed_bank"]


def _mc(gid, label, q, options, correct):
    return MCVariant(group_id=gid, label=label, question_text=q, variant_summary="loop-behaviour question",
                     options=options, correct_index=correct)


def _bank(run_id, variants):
    return Bank(run_id=run_id, title="t",
                groups={"c1": Group(group_id="c1", concept_title="loops",
                                    question_type="multiple_choice",
                                    variants={v.label: v for v in variants})})


def grounded_bank() -> Bank:
    return _bank("gnd-q-grounded", [
        _mc("c1", "A", "How many times does `for (let i = 0; i < 5; i++)` run?", ["3", "5", "10"], 1),
        _mc("c1", "B", "When is the condition `i < 5` checked?",
            ["before each pass", "after each pass"], 0),
    ])


def model_supplied_bank() -> Bank:
    # correct and on-topic, but the material says nothing about any of it → the model's own knowledge
    return _bank("gnd-q-model",
                 [_mc("c1", "AB"[i], q, opts, ci) for i, (q, opts, ci) in enumerate(_MODEL_Q[:2])])


def mixed_bank(n_grounded: int) -> Bank:
    """A 4-question bank: `n_grounded` questions the material answers + the rest model-knowledge.
    Coverage should read ~ n_grounded/4 — 3→75%, 2→50%, 1→25%."""
    picks = _GROUNDED_Q[:n_grounded] + _MODEL_Q[: 4 - n_grounded]
    variants = [_mc("c1", "ABCD"[i], q, opts, ci) for i, (q, opts, ci) in enumerate(picks)]
    return _bank(f"gnd-q-mixed-{n_grounded}", variants)
