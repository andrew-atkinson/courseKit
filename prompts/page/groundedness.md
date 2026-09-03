---
name: groundedness
category: page
description: "Classify each claim in a page SECTION by its GROUNDING in the source material — provenance, not correctness"
---
You are auditing where a course page's content **comes from**. Not whether it is correct (that is a
separate check) and not how well it teaches — only its **provenance** relative to the week's source
material: is each claim actually IN the material, or added from your own knowledge?

You will be shown the week's MATERIAL and **one SECTION** of the page. Identify the substantive
**claims** in this section — the factual or conceptual assertions a student would take away — and
classify EACH against the MATERIAL.

The test is strict and concrete:

- **GROUNDED** — you can POINT TO where the material states or entails this claim. In your reason,
  **quote the supporting phrase from the material**. No quote, no GROUNDED.
- **TENSION** — the material addresses this point but the claim DISAGREES with it (a contradiction).
- **MODEL** — you CANNOT find it in the material. It is added from outside — even if it is true,
  plausible, or on the same topic.

Default to **MODEL** when unsure. Being on the same subject is NOT grounding. An **example, analogy,
number, name, or comparison the material does not itself give is MODEL**, however apt — e.g. if the
material explains Perlin noise but never says "marble," then "looks like marble" is MODEL, not
GROUNDED. Only tag GROUNDED when the material actually carries the claim and you can quote it.

If a COURSE DOMAIN is given above and it is **interpretive** (aesthetics, criticism, theory), note in
the reason when a TENSION is a defensible different reading rather than a factual conflict, and when a
MODEL claim is the kind of elaboration the domain welcomes.

Classify EVERY substantive claim in the section — do not skip any. A pure transition or formatting
section may have none; then return an empty list. **Think briefly**, THEN end with exactly this block,
one line per claim, nothing after it:

CLAIMS:
- the loop runs five times: GROUNDED | material says "the loop runs five times, i takes 0..4"
- looks like marble: MODEL | material never mentions marble — an added analogy
- the condition is checked after each pass: TENSION | material says it is checked before
