---
name: close
category: page
description: "Decomposition prototype: close the page — summary + a retrieval prompt"
---
Close the page. The summary heading is already placed on the page for you; add ONLY the closing content beneath it, and do not add another heading.

You are given the week's concepts and its enduring understanding. With tool calls only, in this order:

1. `add_bullets` with a few of the week's key takeaways — drawn ONLY from the concepts listed. Do not introduce a topic that is not among them.
2. One `add_details` as a retrieval prompt: its `summary` is a "Predict: …" question about this week's material (something the student answers from memory), and its `text` is the answer. Reading is not remembering — make the student retrieve before they leave.

Do not re-teach the concepts or add other sections. Give each block a short, stable block_id. No links or URLs.
