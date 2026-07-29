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

The fixtures are [`examples/synthetic/<domain>`](../examples/synthetic/) — coding, biology, prelaw,
and photo, each a transcript (the only material the critic may trust), a bank of sound questions +
planted flaws, and an `expected.json` answer key. See that folder's README for the scorecard format.

## The scorecard harness (`scorecard.py`)

The pytest above is a tolerant pass/fail *guard*. For the actual measurement — recall **by flaw
type**, false-flag rate on the sound questions, and per-read-vs-union (does an extra cold read add
catches, or is multi-read a no-op on this model?) — run the harness, which scores the critic over the
larger **generated** set (`synthesize_all()`, ~72 labelled cases) rather than the 24-question hand-set:

```bash
uv run python evals/scorecard.py                             # 1 read (default), per-read seeds on
uv run python evals/scorecard.py --reads 5                   # more cold reads
uv run python evals/scorecard.py --model qwen/qwen3.6-35b-a3b # a different critic model (LM Studio JIT-loads it)
uv run python evals/scorecard.py --seed-base none            # seeds off, to compare read variance
```

Every run is saved to `evals/results/<timestamp>-<model>-r<reads>.md` (gitignored) — the scorecard
plus a per-question table showing exactly which questions flagged, missed, or false-flagged, so runs
and models are comparable after the fact. To diff two runs on the questions they share (e.g. a slow
reasoning model vs a fast one):

```bash
uv run python evals/compare.py evals/results/<runA>.md evals/results/<runB>.md
```

The scoring math lives in
[`coursekit/generate/quiz/scoring.py`](../coursekit/generate/quiz/scoring.py) and is unit-tested
offline (`tests/test_scoring.py`) — the harness only gathers the verdicts.

The **page** critic has the same treatment: `evals/page_scorecard.py` scores it over labelled synthetic
page sections (`coursekit/generate/page/synthesize.py` — sound facts plus planted `contradiction`,
`garbled`, and `out-of-scope` sections), reusing the same scoring math.

```bash
uv run python evals/page_scorecard.py                        # 1 read/section, all domains
uv run python evals/page_scorecard.py --hard                  # subtle near-miss / beyond-material flaws
uv run python evals/page_scorecard.py --model qwen/qwen3.6-27b
```

The **page pedagogy rubric** (a second page-evaluator mode — how a page *reads and teaches*, scored 0–3
on scannability / signaling / engagement / worked-examples / retrieval, not FLAG/PASS) has its own
calibration: `evals/pedagogy_scorecard.py` scores one well-built coding page plus deficient variants
(each missing one dimension's blocks) and checks the rubric scores each variant lower on its dropped
dimension.

```bash
uv run python evals/pedagogy_scorecard.py
```
