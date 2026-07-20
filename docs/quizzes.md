# Generating quizzes

A quiz is **5 concepts × 4 variants**. Each concept becomes a Canvas *question group* that draws one
variant at random, so every student gets a different version of the same quiz. The model commits each
question through a tool call — prose is scratch, so a revision overwrites rather than piling up.

The canonical artifact is `bank.json`; the emitters (GIFT, QTI) read only it. Adding a platform is one
emitter, not a rewrite.

## See what it would do (free, no model)

```bash
uv run python app.py "/path/to/course export" --dry-run
```

Lists every week it found and where each would be written — a cheap check before spending model time.

## Generate

```bash
uv run python app.py "/path/to/course export" --week 3      # one week
uv run python app.py "/path/to/course export" --weeks 3-8   # an inclusive range
uv run python app.py "/path/to/course export"               # every week found
```

`PATH` is a markdown file **or** a directory. Given a directory it picks up per-week transcripts
(`week-*.md`). Expect a few minutes per week on a local model.

**Input is decoupled** — any markdown works. If the path happens to sit under a videotranscriber
project (marked by a `.vtconfig/` folder), coursekit reads its `context.yaml` to enrich the prompt
with week titles and module names. It never requires it.

## Where output goes

**With the course, never in this repo.** Artifacts land in a `quizzes/` tree beside the course's own
files:

```
<course root>/quizzes/week-3/
├── bank.json          # canonical: every concept and variant
├── quiz.json          # which variants a quiz draws, and the seed
├── bank.gift          # all questions, GIFT (plain text)
├── quiz_<seed>.gift   # one deterministic paper
├── calls.jsonl        # every tool call, replayable without the model
└── reply.txt
```

Use `--output-root DIR` to redirect elsewhere (e.g. scratch during testing).

**Question types:** multiple choice, true/false, multiple-answer, short answer, numerical, matching.

## Exporting to Canvas

QTI generation is **model-free** — it reads `bank.json`, so you can re-export any time without
regenerating questions.

```bash
# one .zip per week, written beside each bank.json
uv run python app.py --to-qti "/path/to/course export/quizzes"

# OR one package containing every week — a single Canvas import
uv run python app.py --to-qti "/path/to/course export/quizzes" --bundle
```

Then in Canvas: **Import Content → Content Type: "QTI .zip file"** → upload the `.zip`.

> Use **"QTI .zip file"**, not "Canvas Course Export Package". These are different importers and the
> course-package one brings the quiz in **empty**. (The full story is in
> [canvasQuizStructure.md](canvasQuizStructure.md).)

Each quiz arrives with 5 question groups, each drawing 1 of 4 variants, plus a description and grading
criteria. Both the per-week `.zip` and the `--bundle` package have been imported into a live Canvas
course and confirmed working, with the groups randomizing as intended.

## Good to know

- **The model is an unreliable driver, and the loop expects it.** It sometimes stops before finishing
  or spins on a rejected call. `pipeline.loop` checks the bank rather than trusting the model, nudges
  it back within a bounded budget, and bails on a rejection spiral instead of burning every turn.
- **Guardrails are steering, not just validation.** When the model reuses a correct-answer position,
  the rejection tells it which positions are still free — errors are written for the model to act on.
- **Module placement isn't supported** yet: quizzes import into the Quizzes list, not into weekly
  modules. **GIFT output is unverified** against a live Moodle — it's there as readable plain text;
  Canvas QTI is the tested path.

See also: [Configuration](configuration.md) (providers, per-course `quiz.yaml`, prompt overrides) and
[the domain profile](domain-profile.md) (keeping the model in the right knowledge domain).
