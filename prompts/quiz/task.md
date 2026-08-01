---
name: task
category: quiz
description: "The brief - one group per concept (count set by the concept map or config), four variants, type mix, position rule, variant summaries"
---

Build a question bank for this lecture.

One question group per concept the lecture teaches. **How many groups** is set at the end of this
brief — from the week's concept map, or the course's configuration; follow it, and let the content
decide the number rather than forcing a fixed count. If the course's domain note asks for a particular
kind of question or a subject emphasis, follow that too.

Types: at least half of the groups must be "multiple_choice". You may use "multiple_answer",
"true_false", "short_answer", "numerical" or "matching" for the others where the concept genuinely
suits it. Do not pick a type just for variety.

Use "multiple_answer" only when a concept really has several correct answers at once, so the
student must pick every one of them. If exactly one answer is right, it is "multiple_choice".
The marks are worked out for you: just say which options are correct.

Four variants per group, labelled A, B, C, D. Each variant is a DIFFERENT question testing the
same concept, not a reworded copy of the same question.

Every variant needs a variant_summary: a few words naming the angle THAT variant takes, which
becomes its name in the question bank. Within a group they must all differ. For a concept like
"The rule of thirds" the four summaries might be "Placing the horizon", "Positioning the subject",
"Why the eye rests there" and "When to break it". Write the summary first: if you cannot say how a
variant differs from the other three in a few words, it is too similar and you should write a
different question.

For multiple_choice variants: exactly four options, one correct and three plausible distractors
drawn from mistakes a student would really make. Across a group's four variants the correct
option must sit at index 0 in one, 1 in another, 2 in another and 3 in the last. The tool reply
tells you which positions are still free.

If the material is technical and contains code, a code-completion question is a strong choice where
it fits — the student reads code with a gap and picks the code that belongs (question_type
"multiple_choice", text_format "markdown"). Let the material decide; never force one onto a subject
that has no code.

For true_false groups: at least one variant must be true and at least one must be false.

Start by calling create_checklist.
