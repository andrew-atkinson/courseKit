---
name: concept_section
category: page
description: "Decomposition prototype: teach ONE concept as a page section, from its own material"
---
Teach ONE concept as a single page section. You are given the concept and only the material that concerns it — use only that material. The section's heading is already placed on the page for you; add ONLY the teaching content beneath it, and do not add another heading.

You may also be told which concept comes just before this one on the page and which comes just after. If so, open by briefly connecting to the previous concept (a linking phrase, not a re-teaching) and end by pointing toward the next, so the sections read as one flowing page rather than isolated boxes. Teach ONLY the current concept — never teach a neighbour; use the neighbours only to connect.

With tool calls only, composing the section body from these components — choose by **function**:

{palette}

In order:

1. Explain the concept: one or two `add_paragraph` blocks — what it is and why it matters, one idea per paragraph, not a bare list of terms.
2. Where the material shows a concrete example, include it right there — code verbatim in `add_code`, a visual the concept is built around in `add_image` (short `ref` + real `alt`), a common mistake or wrong-vs-right / before-vs-after in `add_columns`. **Introduce anything you show with a sentence first — what it is and why it's here — and never place two shown blocks (code, image, …) back to back with nothing between them: if a second builds on the first, a line of prose must connect them and explain the relationship.**
3. If the concept has its own key terms, add a short `add_glossary`.

Use only code and examples that appear in the material — never invent an example, a variable name, or an entity. If the material shows no example for this concept, include none rather than making one up.

When the material shows an idea EVOLVE — a version shown, then changed, corrected, or refined later — use the FINAL, latest form, not an earlier one. A lecture often demonstrates a naive or buggy first attempt before the working conclusion; the page should show the conclusion (use an earlier version only as an explicit, labelled wrong-vs-right contrast).

Stay on THIS concept only — do not open other sections, do not add a heading, do not summarise the week. Give each block a short, stable block_id. No links or URLs.
