---
name: task
category: quiz
description: "The brief - 5 concepts x 4 variants, type mix, correct-answer position rule, variant summaries"
---

Build a question bank for this lecture.

Five concepts, one question group each:
- c1 to c4: the four most important ideas in the transcript.
- c5: a code-completion question. The student reads code with a gap and picks the code that
  belongs in the gap. Use question_type="multiple_choice" and text_format="markdown".

Types: at least three of the five groups must be "multiple_choice". You may use "multiple_answer",
"true_false", "short_answer", "numerical" or "matching" for the others where the concept genuinely
suits it. Do not pick a type just for variety.

Use "multiple_answer" only when a concept really has several correct answers at once, so the
student must pick every one of them. If exactly one answer is right, it is "multiple_choice".
The marks are worked out for you: just say which options are correct.

Four variants per group, labelled A, B, C, D. Each variant is a DIFFERENT question testing the
same concept, not a reworded copy of the same question.

Every variant needs a variant_summary: a few words naming the angle THAT variant takes, which
becomes its name in the question bank. Within a group they must all differ. For a concept like
"Anatomy of a for loop" the four summaries might be "Purpose of the condition", "What the
incrementer does", "Role of initialization" and "Loop syntax". Write the summary first: if you
cannot say how a variant differs from the other three in a few words, it is too similar and you
should write a different question.

For multiple_choice variants: exactly four options, one correct and three plausible distractors
drawn from mistakes a student would really make. Across a group's four variants the correct
option must sit at index 0 in one, 1 in another, 2 in another and 3 in the last. The tool reply
tells you which positions are still free.

For true_false groups: at least one variant must be true and at least one must be false.

Start by calling create_checklist.
