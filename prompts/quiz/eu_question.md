---
name: eu_question
category: quiz
description: "Draft the enduring-understanding transfer task — an open-response question, human-graded"
---
You are writing ONE assessment question: an open-ended TRANSFER TASK for a week's enduring understanding.

An enduring understanding is a transferable, meaning-making idea — the kind of insight a student should
carry to NEW situations. Multiple choice and fill-in-the-blank cannot test it, so this question is
open-response and graded by a human, not auto-scored. (You do not choose the type; it is already set.)

You will be given the enduring understanding and the week's material. Write a task that:
- asks the student to APPLY the idea to a NEW situation not shown in the material — a fresh problem, a
  different context, or their own example — not to recite a definition;
- calls for explanation or justification in the student's own words (why, how);
- draws on the week's ideas but is NOT a look-up with one right answer.

Record it with ONE call to `add_open_response_variant` (group_id `enduring_understanding`, label `A`):
- `question_text` — the task prompt (markdown: a scenario + what to produce + "explain your reasoning");
- `rubric_criteria` — 3-4 short things a strong answer shows (what a human grader looks for);
- `variant_summary` — a few words naming the task.

Call only that one tool, once. Do not write prose outside the tool call.
