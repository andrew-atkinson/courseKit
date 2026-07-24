---
name: task
category: quiz
description: "The brief - N concept groups x M variants, type mix, correct-answer position rule, variant summaries"
---

Build a question bank for this lecture.

Write {n_questions} question groups, one per concept — the {n_questions} most important ideas in the
transcript. Choose a question type for each group that genuinely fits the concept; never pick a type
just for variety.

Most groups should be "multiple_choice". Use "multiple_answer", "true_false", "short_answer",
"numerical" or "matching" only where a concept really suits it. Use "multiple_answer" only when a
concept has several correct answers at once, so the student must pick every one; if exactly one answer
is right, it is "multiple_choice". The marks are worked out for you: just say which options are correct.

{n_variants} variants per group, labelled A, B, C, … Each variant is a DIFFERENT question testing the
same concept, not a reworded copy.

Every variant needs a variant_summary: a few words naming the angle THAT variant takes, which becomes
its name in the question bank. Within a group they must all differ. Write the summary first: if you
cannot say in a few words how a variant differs from the others, it is too similar — write a different
question. For a concept like "The exposure triangle" the summaries might be "Role of aperture",
"Effect of shutter speed", "What ISO controls" and "How the three trade off".

For multiple_choice variants: exactly four options, one correct and three plausible distractors drawn
from mistakes a student would really make. Across a group's variants the correct option should sit at
a different position each time (A at index 0, B at index 1, and so on, as far as the variant count
allows). The tool reply tells you which positions are still free.

For true_false groups: at least one variant must be true and at least one must be false.

Anything domain-specific about what to ask — a code-completion question for a programming course, a
visual-analysis question for an art course — comes from the COURSE DOMAIN above when the course
declares one. Otherwise, take your cue from the material itself.

Start by calling create_checklist.
