"""Calibration fixtures for groundedness (EVAL-15): three pages over the SAME coding material whose
claim provenance is KNOWN, so a working critic moves the aggregates the right way (we check the
aggregates, not per-claim matching, since the critic re-extracts claims in its own words):

  - grounded — every claim faithfully from the material  → HIGH coverage, no tension.
  - model    — every claim true but OFF-TOPIC (silent in the material) → LOW coverage (model-supplied).
  - tension  — claims that CONTRADICT the material        → at least one tension flagged.
"""

from coursekit.generate.page.concept_fixtures import CODING_MATERIAL
from coursekit.generate.page.page import Page, build_block

__all__ = ["CODING_MATERIAL", "grounded_page", "model_supplied_page", "near_miss_page", "tension_page"]


def _p(bid, text):
    return build_block("paragraph", block_id=bid, text=text)


def _page(pid, title, paras):
    blocks = [build_block("heading", block_id="h", text=title, level=2, role="concept")]
    blocks += [_p(f"p{i}", t) for i, t in enumerate(paras)]
    return Page(page_id=pid, title=title, blocks={b.block_id: b for b in blocks})


def grounded_page() -> Page:
    return _page("gnd-grounded", "Loops", [
        "A for loop runs the same block of code a set number of times.",
        "The loop has three parts: an initialization that runs once, a condition checked before each "
        "pass, and an increment that runs after each pass.",
        "The loop `for (let i = 0; i < 5; i++)` runs five times, with i taking 0, 1, 2, 3, 4.",
        "When i reaches 5 the condition `i < 5` is false, so the loop stops.",
    ])


def model_supplied_page() -> Page:
    # every claim is TRUE, but the loops material says nothing about any of it → model-supplied
    return _page("gnd-model", "Background", [
        "Python was first released in 1991 by Guido van Rossum.",
        "JavaScript runs inside web browsers and first appeared at Netscape in 1995.",
        "HTML is a markup language for structuring documents, not a programming language.",
        "Git is a distributed version-control system for tracking changes in code.",
    ])


def near_miss_page() -> Page:
    # the HARD case (the real failure the whole-page v1 missed): claims ON-TOPIC and plausible, but the
    # material does NOT carry them — added analogies, examples, extra facts. A lenient critic calls these
    # GROUNDED (topical overlap); a working one calls them MODEL. One grounded control first.
    return _page("gnd-nearmiss", "Loops", [
        "A for loop runs the same block of code a set number of times.",           # grounded control
        "A for loop is like a factory assembly line repeating the same task.",     # MODEL — added analogy
        "Python's `range()` function is another common way to write loops.",       # MODEL — true, off-material
        "A single loop body can hold up to 100 statements.",                       # MODEL — invented detail
    ])


def tension_page() -> Page:
    # claims that ADDRESS the material's topic but CONTRADICT it → tension (one grounded control first)
    return _page("gnd-tension", "Loops", [
        "A for loop runs the same block of code a set number of times.",          # grounded control
        "The loop `for (let i = 0; i < 5; i++)` runs three times.",               # tension — it's five
        "The condition `i < 5` is checked AFTER each pass, not before.",          # tension
        "When i reaches 5 the loop keeps going.",                                 # tension
    ])
