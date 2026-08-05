---
name: concept_section
category: page
description: "Decomposition prototype: teach ONE concept as a page section, from its own material"
---
Teach ONE concept as a single page section. You are given the concept and only the material that concerns it — use only that material. The section's heading is already placed on the page for you; add ONLY the teaching content beneath it, and do not add another heading.

You may also be told which concept comes just before this one on the page and which comes just after. If so, open by briefly connecting to the previous concept (a linking phrase, not a re-teaching) and end by pointing toward the next, so the sections read as one flowing page rather than isolated boxes. Teach ONLY the current concept — never teach a neighbour; use the neighbours only to connect.

With tool calls only:

1. Explain the concept: one or two `add_paragraph` blocks — what it is and why it matters, one idea per paragraph, not a bare list of terms.
2. Where the material shows code or a worked example, put it right there with `add_code` (verbatim). Where the material shows a common mistake or a wrong-vs-right / before-vs-after, use `add_columns` for the contrast — that is what makes the idea stick.
3. If the concept has its own key terms, add a short `add_glossary`.

Use only code and examples that appear in the material — never invent an example, a variable name, or an entity. If the material shows no example for this concept, include none rather than making one up.

Stay on THIS concept only — do not open other sections, do not add a heading, do not summarise the week. Give each block a short, stable block_id. No links or URLs.
