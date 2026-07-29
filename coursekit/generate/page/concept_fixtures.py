"""Calibration fixtures for concept-delivery: a page that delivers the loop concepts well, plus variants
that deliver them poorly. A working rubric scores the good page's average high and each variant lower.

- good        — each concept explained clearly, shown with a worked example, at the right level.
- thin        — concepts merely NAMED in bullets, never explained (should score ~1).
- no_examples — concepts explained, but the code / worked example removed (explained-not-shown, ~2).
- jargon      — concepts "explained" in dense terms above the material's level (mis-pitched, low clarity).

Same coding material the rest of the synthetic set uses.
"""

from coursekit.generate.page.page import Page, build_block
from coursekit.generate.quiz.synthesize import DOMAINS as _QUIZ_DOMAINS

CODING_MATERIAL = {d.name: d.transcript for d in _QUIZ_DOMAINS}["coding"]


def _good_blocks():
    return [
        build_block("heading", block_id="h1", text="Loops in p5.js", level=2, role="concept"),
        build_block("paragraph", block_id="p_intro",
                    text="A for loop runs the same block of code a set number of times, so you can "
                         "repeat an action — like drawing a shape — without copying the line by hand."),
        build_block("paragraph", block_id="p_parts",
                    text="A for loop has three parts. The initialization `let i = 0` runs once at the "
                         "start. The condition `i < 5` is checked before each pass, and the loop keeps "
                         "going while it is true. The increment `i++` runs after each pass, moving the "
                         "counter on by one."),
        build_block("code", block_id="code1", language="javascript",
                    code="for (let i = 0; i < 5; i++) {\n  circle(i * 40, 50, 20);\n}"),
        build_block("paragraph", block_id="p_trace",
                    text="So this loop runs five times: i takes 0, 1, 2, 3, 4. When i reaches 5 the "
                         "condition `i < 5` is false, so the loop stops."),
        build_block("card", block_id="ex1", card_kind="example", title="Worked example",
                    text="`circle(i * 40, 50, 20)` draws one circle per pass, each shifted right by "
                         "`i * 40` — so the loop draws a row of five evenly spaced circles."),
        build_block("glossary", block_id="gloss", entries=[
            {"term": "loop", "definition": "a block of code that repeats a set number of times"},
            {"term": "counter", "definition": "the variable `i` that changes each pass"},
            {"term": "iteration", "definition": "one pass through the loop body"}]),
    ]


# Blocks that carry the *examples* — removing them leaves the concepts explained but not shown.
_EXAMPLE_BLOCKS = ("code1", "ex1")


def good_page() -> Page:
    return Page(page_id="concept-coding-good", title="Loops in p5.js",
                blocks={b.block_id: b for b in _good_blocks()})


def no_examples_page() -> Page:
    g = good_page()
    return Page(page_id="concept-coding-no-examples", title=g.title,
                blocks={bid: b for bid, b in g.blocks.items() if bid not in _EXAMPLE_BLOCKS})


def thin_page() -> Page:
    """Concepts named, never taught."""
    blocks = [
        build_block("heading", block_id="h1", text="Loops in p5.js", level=2, role="concept"),
        build_block("bullets", block_id="b1", items=[
            "For loops.", "The condition.", "The increment.", "Drawing with loops."]),
    ]
    return Page(page_id="concept-coding-thin", title="Loops in p5.js",
                blocks={b.block_id: b for b in blocks})


def jargon_page() -> Page:
    """Concepts 'explained' above the level — dense, mis-pitched, low clarity."""
    blocks = [
        build_block("heading", block_id="h1", text="Loops in p5.js", level=2, role="concept"),
        build_block("paragraph", block_id="p1",
                    text="Iteration is the bounded recurrence of a statement block under a monotonic "
                         "induction variable whose termination predicate is evaluated at the head of "
                         "each cycle, yielding a deterministic finite trace over the index domain."),
        build_block("paragraph", block_id="p2",
                    text="The post-body mutation operator advances the induction variable through the "
                         "half-open interval until the guard predicate is falsified."),
    ]
    return Page(page_id="concept-coding-jargon", title="Loops in p5.js",
                blocks={b.block_id: b for b in blocks})


VARIANTS = {"thin": thin_page, "no_examples": no_examples_page, "jargon": jargon_page}
