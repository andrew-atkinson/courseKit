---
name: fix
category: quiz
description: "Correct ONE flagged quiz question in place, fixing exactly the flaw the reviewer named"
---
You are correcting ONE quiz question that a reviewer flagged as flawed. You are given the week's
teaching material, the flawed question, and the reviewer's specific concern.

Produce a corrected version that fixes **exactly the flaw the reviewer named** while keeping the
question sound, answerable, and faithful to the material.

Rules:

- Commit the correction through a tool call — do NOT explain in prose. Call the tool for this
  question's type with the **same `group_id` and `variant_label`**, which REPLACES the flawed
  question in place. Keep the same question type.
- The marked answer MUST be correct according to the material. If the flaw was a wrong answer key,
  either re-mark the correct option or rewrite the options so the marked one is right.
- Keep the distractors plausible but genuinely wrong. Keep the stem clear and self-contained (a
  student answers from the stem and options alone, not from the material in front of them).
- If the flaw was structural (the options don't match what the stem asks, the answer is given away in
  the stem, the wording is inconsistent), rewrite whatever is needed so the question is coherent.
- Change only what the flaw requires; keep everything already sound.

Call the tool once with the corrected question, then stop.
