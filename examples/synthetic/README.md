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

## The hand-set vs the generator

The four folders above are the original **hand-authored** set — 24 questions, small enough to read in
one sitting. Alongside them, [`coursekit/generate/quiz/synthesize.py`](../../coursekit/generate/quiz/synthesize.py)
**generates** a larger labelled set deterministically: from a handful of sound seed questions per
domain it derives the same four flaw kinds, one exact label per question, so the answer key is the
construction rather than a second file that can drift. `wrong-answer` and `garbled-syntax` are true
mechanical mutations; `missing-context` and `out-of-scope` are authored per seed (a believable version
of each is domain-specific). It runs no model.

A scoring harness imports `synthesize_all()` directly (Bank objects + expected-verdict map — no disk
needed). To eyeball the fixtures instead:

```bash
uv run python -m coursekit.generate.quiz.synthesize   # dumps to examples/synthetic/generated/ (gitignored)
```

To grow either set: add a domain folder / bank questions for the hand-set, or add `Seed`s and
`OutOfScope`s to a `DomainSpec` in `synthesize.py` — each new seed yields four more labelled cases.
