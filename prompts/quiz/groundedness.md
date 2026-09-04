---
name: groundedness
category: quiz
description: "Classify a quiz question by whether its answer is GROUNDED in the source material — provenance, not correctness"
---
You are auditing where a quiz QUESTION comes from — its **provenance** relative to the week's source
material. Not whether the marked answer is correct (that is a separate check). Only this: does the
SOURCE actually let a student answer this from what they were taught, or is the question testing
knowledge that lives in your own head and not in the material?

You will be shown the MATERIAL and ONE question with its marked answer (`*` marks the answer). Decide
by a single test:

**Can you quote a phrase from the MATERIAL that supplies the answer?**
- **YES** → **GROUNDED**. Quote that phrase. (If the material states or clearly entails what the
  question turns on, it is grounded — no matter how short the material is. A brief source that
  happens to contain the answer is still grounded.)
- **NO** → **MODEL**. Being on the same *topic* as the material is not enough; if you cannot point to
  where the material gives the answer, the question is testing your own knowledge, not the course's.

Judge only provenance — ignore whether the marked answer is *right* (that is a separate facticity
check). A question can be perfectly correct in general and still be MODEL when the material doesn't
supply it.

**Think briefly**, THEN end with exactly this line and nothing after it:

GROUNDING: <GROUNDED|MODEL> | <one short reason; quote the material for GROUNDED>
