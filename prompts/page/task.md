---
name: task
category: page
description: "The brief: organise a week's material into a page"
---
Organise this week into a single course page, working top to bottom:

1. If the week builds on earlier ones, open with a **recap**: add a heading with `role: review`
   whose text **names the topic you are recapping** — the prior week's theme, e.g. "Still Life"
   (it renders as "Still Life Recap"). Then add **two to four `add_details`, one per recall question** —
   each summary is a question the student answers from memory ("What did last week establish about
   X?") and each text is the answer. They render as accordions inside a Recap box, so the student
   predicts before revealing. Make the questions genuinely worth answering, not trivial. Skip the
   recap entirely if the material doesn't look back.
2. Add a heading for each key concept the week teaches, with bullets underneath capturing the main
   points. Keep bullets to short phrases.
3. Where the material demonstrates something concrete — code, a worked example, a technique — put it
   next to the concept it illustrates (code goes verbatim in a code block).
4. Add the week's key terms as a **glossary** at the **end** of the page — it labels itself, needs no
   separate heading, and renders as a framed "Key Terms" box. For terms specific to a single concept,
   put a glossary *under that concept's heading* (with more concepts after it) instead, where it folds
   into the concept as a subsection.
5. Add a callout for any common pitfall or warning the material calls out.

Give each block a short, stable block_id. Do not include any links, URLs, or references — those are
added separately by the instructor. When the page reads as a clear outline of the week, call
finalize_page.

Start now with the first heading.
