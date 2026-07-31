---
name: task
category: page
description: "The brief: organise a week's material into a page"
---
Organise this week into a single course page. A good page doesn't just present the material — it pulls
the student in, foregrounds what matters, and helps them consolidate.

**Size the page to the material, not to a fixed length.** Let the page's depth follow how much the week
actually teaches: a week with many distinct concepts earns a fuller page — each concept its own real
section with an explanation and a worked example — while a week with only one or two ideas stays tight.
Never pad a thin week with ceremony, and never compress a rich week into a summary. The number of
concepts the week teaches is what grounds the length.

Build it top to bottom:

1. **Recap (only if the week builds on earlier ones).** Open with a heading with `role: review`
   whose text **names the topic you are recapping** — the prior week's theme, e.g. "Still Life"
   (it renders as "Still Life Recap"). Then add **two to four `add_details`, one per recall question** —
   each summary is a question the student answers from memory ("What did last week establish about
   X?") and each text is the answer. They render as accordions inside a Recap box, so the student
   predicts before revealing. Make the questions genuinely worth answering, not trivial. Skip the
   recap entirely if the material doesn't look back.
2. **Open with a hook.** Before any definitions, give the student a reason to care: a concrete
   scenario, a question worth chewing on, or the problem this week solves ("You can place one shape by
   hand — but what about five hundred?"). One short paragraph, or a callout. Make it real, not a
   throat-clearing sentence — this is the page's first job, to earn attention.
3. **Teach each concept in its own section — with real content, not just a label.** For every core
   concept the week teaches, add a heading and then actually teach it: a short explanation of what it
   is and why it matters (a sentence or two, or substantive bullets — not a bare list of terms), and,
   wherever the material shows it, a concrete **code example or worked demonstration right beside it**
   (code goes verbatim in a code block). A heading with three abstract bullets is not teaching the
   concept — the nuts and bolts are the point, so give every concept its example where one exists.
   Where the material has a common mistake, an off-by-one, or a manual-vs-automated approach, show the
   two side by side with `add_columns` (wrong vs. right, before vs. after) — the contrast is what makes
   the idea stick, so reach for it wherever the week offers one.
   **Where a concept is inherently visual, place an image.** For a diagram, an example work, a chart, or
   any visual the material shows or describes, call `add_image` with a short `ref` and real `alt` text.
   You never supply the file — the instructor adds it under that ref — so never write a URL, and reach
   for an image only where a visual genuinely teaches, not as decoration.
   **Keep each paragraph to one idea.** When a paragraph would carry both how something works and why
   it matters — its mechanism and its purpose — or two different concepts, split it into separate
   paragraphs. A reader should be able to name the single point of each paragraph.
4. **Foreground the one key idea.** Decide the single thing this week hinges on — the sentence a
   student should keep even if they forget the details — and set it with `add_pullquote`, once. If you
   cannot name one, the page has no centre; find it before moving on.
5. Add the week's key terms as a **glossary** near the **end** of the page — it labels itself, needs no
   separate heading, and renders as a framed "Key Terms" box. For terms specific to a single concept,
   put a glossary *under that concept's heading* (with more concepts after it) instead, where it folds
   into the concept as a subsection.
6. Add a callout for any common pitfall or warning the material calls out.
7. **Close by consolidating.** End with a heading `role: summary` and a few bullets of the week's key
   takeaways — then give the student one thing to DO with the material: an `add_details` recall prompt
   whose summary is a question about *this* week ("Predict: how many times does this loop run?") and
   whose text is the answer, or a short practice task. Reading is not remembering; the page should ask
   the student to retrieve before they leave.

Give each block a short, stable block_id. Do not include any links, URLs, or references — those are
added separately by the instructor. When the page opens with a hook, foregrounds one key idea, closes
with consolidation, and includes at least one retrieval prompt (a predict/recall `add_details` — the
closing one, or the recap's questions), call finalize_page. A page without a retrieval prompt will not
finalize.

Start now.
