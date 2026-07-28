# Synthetic evaluation courses

A controlled test bed for the quiz **critic** (`coursekit evaluate`) across several knowledge
domains, so its judgment can be measured — not just spot-checked — before it's wired into generation.

Each domain (`coding`, `biology`, `prelaw`, `photo`) is a tiny one-week course:

- `output/week-1.md` — a short transcript that is the **only** material the critic may trust.
- `quizzes/week-1/bank.json` — a bank of **sound** questions plus **planted flaws**, one flaw kind
  per question: `out-of-scope` (asks about something the transcript never teaches), `wrong-answer`
  (marks an option the material contradicts), `missing-context` (asks "why is X?" with no scenario),
  `garbled-syntax` (nonsense code/notation).
- `expected.json` — the answer key: which questions should PASS and which should FLAG, and why.

The eval suite (`evals/test_critic_on_synthetic.py`) runs the critic over every domain and prints a
per-domain scorecard — **recall** (planted flaws caught) and **false-flag rate** (sound questions
wrongly flagged):

```bash
uv run pytest evals/ -s                 # with a model running; -s shows the scorecard
EVAL_READS=5 uv run pytest evals/ -s    # more cold reads per question
```

To grow the set: add another `examples/synthetic/<domain>/` with the same three files, or add
questions to an existing domain's bank + `expected.json`. Regenerate the `bank.json`/`expected.json`
with the builder in the repo history if you prefer editing Python to editing JSON by hand.
