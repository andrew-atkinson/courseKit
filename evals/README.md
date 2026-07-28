# evals — coursekit against a live model

The suite in `tests/` is fully offline and deterministic. **This** suite is the opposite: it
exercises coursekit's *relationship to the LLM* — the parts whose quality only shows with a real
model in the loop (today, the quiz **evaluator**; later, generation quality and the page critic).

Because a model is involved these tests are **slow, non-deterministic, and model-dependent**, so:

- They live **outside `tests/`** (not in `testpaths`), so a normal `uv run pytest` never runs them
  and the offline test count is unaffected.
- Each test **skips cleanly** when no model is reachable — it never fails a machine without one.
- Assertions are **tolerant** — regression guards ("don't false-flag the sound question; catch at
  least 3 of the 4 planted flaws, including the out-of-scope one"), not exact matches, because a
  local model catches a *different* 3-of-4 on different runs.

Run it with your provider up (LM Studio by default):

```bash
uv run pytest evals/
# or point the critic at a specific/stronger model:
MODEL_NAME=<model> uv run pytest evals/
```

The fixture is [`examples/synthetic-course`](../examples/synthetic-course/) — a transcript that is the
only material the critic may trust, a bank with one sound question and four planted flaws, and an
`EXPECTED.md` answer key.
