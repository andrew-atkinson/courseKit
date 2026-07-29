---
name: task
category: page
description: "The brief: organise a week's material into a page"
---
Organise this week into a single course page, working top to bottom. A good page doesn't just present
the material — it pulls the student in, foregrounds what matters, and helps them consolidate:

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
3. Add a heading for each key concept the week teaches, with bullets underneath capturing the main
   points (short phrases). Where the material demonstrates something concrete — code, a worked
   example, a technique — put it next to the concept it illustrates (code goes verbatim in a code
   block).
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
added separately by the instructor. When the page opens with a hook, foregrounds one key idea, and
closes with consolidation, call finalize_page.

Start now.
