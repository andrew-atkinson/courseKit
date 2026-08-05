---
name: segment
category: page
description: "Analyze-time: mark where each concept's teaching begins, to partition the week by concept"
---
You are given a list of teaching CONCEPTS in the order they are taught, and the week's TRANSCRIPT split into numbered chunks.

For each concept, identify the chunk where its teaching BEGINS — the first chunk that starts explaining that concept: its definition, its discussion, or the example that demonstrates it. Everything from that chunk up to where the next concept begins belongs to that concept, so make sure a concept's worked example, code, case, or figure falls inside its own span, not the previous concept's.

The concepts are taught roughly in order, so the starting chunk numbers should increase.

Output ONLY a JSON array of chunk numbers, one per concept, in the same order as the concepts were listed. For N concepts, output exactly N numbers. Example, for three concepts: [1, 4, 9].

No prose, no explanation — just the array.
