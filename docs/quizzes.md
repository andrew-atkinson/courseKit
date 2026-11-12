# Generating quizzes

A quiz is **one question group per concept, × 4 variants** — the number of concepts follows the week's concept map, rather than a fixed five.
Each concept becomes a Canvas _question group_ that draws one variant at random, so every student gets a different version of the same quiz.

You can override the count at two levels: a `questions:` value in a week's `.vtconfig/concepts/week-N.yaml` fixes the number for **that week**, and `questions:` in the course's `.vtconfig/quiz.yaml` fixes it for **every** week — the per-week value wins.
With neither set, the model chooses, guided by the concept map.

### The enduring-understanding question (opt-in)

Multiple choice can't test an _enduring understanding_ — a transferable, meaning-making idea — so it isn't made into a quiz group by default.
Set `eu_question: true` in the course's `.vtconfig/quiz.yaml` and each week's quiz gains **one open-response question**: a short transfer task asking the student to apply the week's enduring understanding to a new situation, with a few rubric criteria folded into the prompt.
It exports as a Canvas essay question and is **graded by hand** (coursekit writes the task and the criteria, never grades the response); the automatic facticity check skips it, since it has no marked answer.
A fuller version — a standalone Canvas assignment with a structured rubric — is on the roadmap.
The question is built from the unit's enduring understanding, which comes from its concept map, so run `coursekit analyze` first.
A unit without one still gets its quiz, and the run prints a warning naming the unit and what's missing — the question is never silently left out.
A single-document quiz (`generate --source`) gets the question too, from the unit the document belongs to; the rest of that quiz is still shaped by the document alone.

To generate **just** the enduring-understanding question — one focused model call, without regenerating the whole quiz — run it directly against a week that already has a concept map:

```bash
uv run python -m coursekit.generate.quiz.eu "/path/to/course" --week 3
```

It adds the question to that week's existing `bank.json` in place (or writes an EU-only bank if none exists), and re-running replaces the question rather than duplicating it.

### The quiz introduction

The last step of a quiz run is the introduction a student reads in Canvas before starting: two or three sentences on what the unit was about and why the quiz is worth taking, written in the course's voice (`.vtconfig/voice.md`).
The model sees only the unit's title, the topics, the big idea, and whether there is an open question, so it can't point the student at a file; a reply that names a file or a link is not kept.
It is saved as `intro` in `bank.json`, where you can edit it, and the next `emit` uses your edit.
The grading line under it is written by coursekit, not the model, so the points and who marks what are always right — for example "7 points marked automatically; the open question (1 point) is marked by your instructor."
A quiz without an introduction (one made before this, or a run whose intro failed, which prints a warning) gets a plain default.
To write just the introduction for a week's existing quiz, without regenerating it:

```bash
uv run python -m coursekit.generate.quiz.intro "/path/to/course" --week 7
```

The brief is `prompts/quiz/intro.md`; a course can override it at `.vtconfig/prompts/quiz/intro.md`.

### The question order

A quiz's order lives in its `quiz.json`, as the `groups` list, and every export follows it: Canvas, the GIFT quiz paper, and `bank.gift` for Moodle.
The default is the order the questions were written in, with open questions last.
To put them in your own order, reorder the `groups` list and set `"order_from": "instructor"`; a later fix, enduring-understanding pass, or intro run keeps your order (and each group's points), adding any new group at the end.
Without that marker, the next of those runs puts the default order back.
A whole new `generate` starts from the default again, since its questions are new.
The introduction describes where the open question sits, so after moving one, re-run the intro command to match.
Programs (and a future front-end) set an order with `coursekit.generate.quiz.bank.set_order`, which refuses a list that misses or repeats a group.
The model commits each question through a tool call — prose is scratch, so a revision overwrites rather than piling up.

The canonical artifact is `bank.json`; the emitters (GIFT, QTI) read only it.
Adding a platform is one emitter, not a rewrite.

## See what it would do (free, no model)

```bash
uv run coursekit generate "/path/to/course export" --dry-run
```

Lists every week it found and where each would be written — a cheap check before spending model time.

## Generate

```bash
uv run coursekit generate "/path/to/course export" --week 3      # one week
uv run coursekit generate "/path/to/course export" --weeks 3-8   # an inclusive range
uv run coursekit generate "/path/to/course export"               # every week found
```

`PATH` is a course folder, a folder inside it, or one unit's document.
Given a folder, it picks up each unit's document (`week-*.md`, or whatever name `structure.coursekit.yaml` declares) and runs them in the course's unit order.
Expect a few minutes per week on a local model.

**Input is decoupled** — any markdown works.
If the path happens to sit under a videotranscriber project (marked by a `.vtconfig/` folder), coursekit reads its `context.yaml` to enrich the prompt with week titles and module names.
It never requires it.

## Target one document instead of the whole week

A whole-week quiz draws on everything in `week-N.md`. Sometimes you want a quiz on **one source** — a single reading, one slide deck, a PDF — not the week entire:

```bash
uv run coursekit generate "/path/to/course" \
  --source "/path/to/course/week-3/readings/Barrett.pdf"
```

It extracts that document, writes it as `source.md`, and generates a quiz into a **distinct** slug — `quizzes/week-3-barrett/` — so a targeted quiz never overwrites the whole-week quiz or another document's.
The unit comes from the declared structure when `structure.coursekit.yaml` lists the document as one of a unit's sources, then from its path (a `week-N` name or ancestor directory); with neither, the slug is just the document name.
Targeted generation is **quizzes only**, and honours the course's `domain.md`, voice, and `quiz.yaml` exactly as a whole-week run does.
The supported document types are the same as `ingest` (PDF, slides, docx, odt, txt, md).

To quiz every source in a week separately, loop over them:

```bash
for f in "/path/to/course/week-3"/*/*; do
  uv run coursekit generate "/path/to/course" --source "$f"
done
```

## Where output goes

**With the course, never in this repo.** Artifacts land in a `quizzes/` tree beside the course's own files:

```
<course root>/quizzes/week-3/
├── bank.json          # canonical: every concept and variant
├── quiz.json          # the quiz: question order, which variants it draws, points, and the seed
├── bank.gift          # all questions, GIFT (plain text)
├── quiz_<seed>.gift   # one deterministic paper
├── record.json        # what the quiz was made from, so coursekit can tell when it's out of date
├── calls.jsonl        # every tool call, replayable without the model
└── reply.txt
```

Use `--output-root DIR` to redirect elsewhere (e.g. scratch during testing).

### Is a quiz still up to date?

Each quiz's `record.json` keeps a fingerprint of exactly what the model was shown at each step (the main run, the enduring-understanding question, the introduction), and the files it read.
To see whether each quiz still matches its course, with no model:

```bash
uv run python -m coursekit.records "/path/to/course"
```

The same command lists every page, assignment, overview, and concept map too ([pages.md](pages.md#is-a-page-still-up-to-date)).

A quiz is **current** when coursekit would brief the model exactly as before; **stale** when the course changed underneath it, with the files named ("`output/week-7.md` changed"); **outdated** when only a newer coursekit's own prompts would brief it differently; and **edited** when someone changed `bank.json` or `quiz.json` by hand since coursekit last wrote them.
A change that doesn't reach the model, like adding another unit to `context.yaml`, changes nothing.
Moving the open question makes only the introduction stale, since it describes the order; re-run the intro command.
A quiz made before records reads **unknown** until it's regenerated.

`evaluate` notes each critic's result in the record too (facticity, groundedness), with a fingerprint of the `bank.json` it read.
The command lists them under the quiz ("evaluated: facticity 2026-11-09 (reviewed 32, flagged 2, errors 0)"), and marks one "of an earlier version" once the quiz has changed since, by a fix or by hand, so you know to evaluate again.
Reordering the questions doesn't count as a change: the questions it judged are the same.
Each critic keeps only its latest result; the full history stays in the course's `evals/` folder.
A quiz made before records gets no record from an evaluation, so it stays unknown.

**Question types:** multiple choice, true/false, multiple-answer, short answer, numerical, matching.

## Exporting to Canvas

QTI generation is **model-free** — it reads `bank.json`, so you can re-export any time without regenerating questions.

```bash
# one .zip per week, written beside each bank.json
uv run coursekit emit qti "/path/to/course export/quizzes"

# OR one package containing every week — a single Canvas import
uv run coursekit emit qti "/path/to/course export/quizzes" --bundle
```

Then in Canvas: **Import Content → Content Type: "QTI .zip file"** → upload the `.zip`.

> Use **"QTI .zip file"**, not "Canvas Course Export Package". These are different importers and the
> course-package one brings the quiz in **empty**. (The full story is in
> [canvasQuizStructure.md](canvasQuizStructure.md).)

Each quiz arrives with one question group per concept (the count set by the week's concept map, or `quiz.yaml`), each drawing 1 of 4 variants, plus a description and grading criteria.
Both the per-week `.zip` and the `--bundle` package have been imported into a live Canvas course and confirmed working, with the groups randomizing as intended.

## Good to know

- **The model is an unreliable driver, and the loop expects it.** It sometimes stops before finishing or spins on a rejected call. `pipeline.loop` checks the bank rather than trusting the model, nudges it back within a bounded budget, and bails on a rejection spiral instead of burning every turn.
- **Guardrails are steering, not just validation.** When the model reuses a correct-answer position, the rejection tells it which positions are still free — errors are written for the model to act on.
- **Module placement comes with `emit course`.** An `emit qti` import lands in the Quizzes list, not in modules; the whole-course cartridge puts each quiz in its unit's module. **GIFT output is unverified** against a live Moodle — it's there as readable plain text; Canvas QTI is the tested path.

See also: [Configuration](configuration.md) (providers, per-course `quiz.yaml`, prompt overrides) and [the domain profile](domain-profile.md) (keeping the model in the right knowledge domain).
