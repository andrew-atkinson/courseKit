"""Calibration fixtures for the page pedagogy rubric: one well-built coding page + deficient variants.

Pedagogy is a whole-page property, so — unlike the single-paragraph facticity sections — this is a full,
multi-block "Loops" page that hits all five rubric dimensions. Each deficient variant removes exactly the
blocks that carry ONE dimension (strip the headings → no scannability; strip the pull-quote → no
signaling; …). A working rubric scores the good page high everywhere and each variant low on its missing
dimension — a clean discrimination test, offline and controlled. The material is the coding transcript
the rest of the synthetic set already uses.
"""

from coursekit.generate.page.page import Page, build_block
from coursekit.generate.quiz.synthesize import DOMAINS as _QUIZ_DOMAINS

CODING_MATERIAL = {d.name: d.transcript for d in _QUIZ_DOMAINS}["coding"]


def _good_blocks():
    return [
        build_block("heading", block_id="h_review", text="Before we start", level=2, role="review"),
        build_block("paragraph", block_id="p_hook",
                    text="Ever retyped the same `circle()` line five times to draw a row? A loop writes "
                         "it once and repeats it — change one number and the whole row moves."),
        build_block("heading", block_id="h_concept", text="How a for loop works", level=2, role="concept"),
        build_block("paragraph", block_id="p_concept",
                    text="A for loop repeats a block a set number of times. It has three parts: an "
                         "initialization that runs once, a condition checked before each pass, and an "
                         "increment that runs after each pass."),
        build_block("code", block_id="code1", language="javascript",
                    code="for (let i = 0; i < 5; i++) {\n  circle(i * 40, 50, 20);\n}"),
        build_block("pullquote", block_id="pull1",
                    text="Change one number, and every circle moves at once."),
        build_block("heading", block_id="h_example", text="By hand vs. with a loop", level=2, role="example"),
        build_block("columns", block_id="cols1", columns=[
            {"title": "By hand", "items": ["circle(0, 50, 20)", "circle(40, 50, 20)",
                                           "…three more lines", "five places to edit"]},
            {"title": "With a loop", "items": ["one loop draws all five", "change 5 to 8 for eight",
                                               "one place to edit"]}]),
        build_block("card", block_id="ex1", card_kind="example", title="Worked example",
                    text="To draw 8 circles instead of 5, change the condition to `i < 8`. The body is "
                         "untouched — the loop count is the only thing that varies."),
        build_block("details", block_id="det1",
                    summary="Predict: how many times does the body of `for (let i = 0; i < 5; i++)` run?",
                    text="Five times — i takes 0, 1, 2, 3, 4, then 5 fails the condition and it stops."),
        build_block("glossary", block_id="gloss1", entries=[
            {"term": "loop", "definition": "a block of code that repeats"},
            {"term": "iteration", "definition": "one pass through the loop body"}]),
        build_block("heading", block_id="h_summary", text="Recap", level=2, role="summary"),
        build_block("bullets", block_id="recap", items=[
            "A for loop repeats a block a set number of times.",
            "The condition is checked before each pass; the loop stops when it is false.",
            "Change the limit to change how many times the loop runs."]),
    ]


# The blocks that CARRY each dimension — removing them is what makes a variant deficient in it.
DIMENSION_BLOCKS = {
    "SCANNABILITY": ["h_review", "h_concept", "h_example", "h_summary"],   # the labelled structure
    "SIGNALING": ["pull1"],                                                # the foregrounded key idea
    "ENGAGEMENT": ["p_hook", "det1"],                                      # the hook + the invitation to predict
    "WORKED_EXAMPLES": ["cols1", "ex1"],                                   # the contrast + the worked example
    "RETRIEVAL": ["det1", "recap"],                                        # the predict prompt + the recap
}


def good_page() -> Page:
    return Page(page_id="pedagogy-coding-good", title="Loops in p5.js",
                blocks={b.block_id: b for b in _good_blocks()})


def deficient_page(criterion: str) -> Page:
    """The good page with the blocks that carry `criterion` removed."""
    remove = set(DIMENSION_BLOCKS[criterion])
    g = good_page()
    return Page(page_id=f"pedagogy-coding-no-{criterion.lower()}", title=g.title,
                blocks={bid: b for bid, b in g.blocks.items() if bid not in remove})
