# quizbot

Turns lecture transcripts into randomized reinforcement learning Canvas quizzes, using a local LLM.

Point it at a week's transcript and it generates **5 concepts × 4 question variants each**. The
variants are the point: each concept becomes a Canvas _question group_ that draws one question at
random, so every student gets a different version of the same quiz.

The model never writes the quiz as prose. It commits each finished question through a **tool call**,
so revisions overwrite rather than pile up — an earlier free-text version of this lost final
questions among the model's own discarded drafts.

## How it works

```
week-3.md  ──►  local LLM (tool calls)  ──►  bank.json  ──►  Canvas .zip (QTI)
 transcript          via LM Studio          the canonical      one import,
                                              artifact         randomized quizzes
                                                   └──────────►  bank.gift (Moodle/plain text)
```

`bank.json` is the canonical form: platform-neutral, lossless, and the only thing the emitters read.
GIFT and QTI are outputs, never inputs. That split is deliberate — GIFT can't express question
groups, so if it were the working format the randomization would be lost before it started.

**Question types:** multiple choice, true/false, multiple-answer, short answer, numerical, matching.

## Requirements

- **Python 3.12+** and [uv](https://docs.astral.sh/uv/)
- A **tool-calling model** behind one of the supported providers — by default
  [LM Studio](https://lmstudio.ai/) running its local server
- macOS for the RAM pre-flight check (it degrades to a no-op elsewhere)

## Install

```bash
git clone <this repo> && cd quizbot
uv sync --group dev
```

Create a `.env` in the project root:

```bash
MODEL_NAME=unsloth-gemma-4-26b-a4b-it-qat-oq4   # must match an id the provider serves
LOCAL_HOST_URL=http://localhost:1234/v1/
TRANSCRIPTION=/path/to/a/week-3.md              # optional default input
PROVIDER=lm_studio                              # optional; lm_studio | ollama | openai
```

`MODEL_NAME` must match a model id the provider actually serves:

```bash
curl -s http://localhost:1234/v1/models | grep '"id"'
```

Verify the install:

```bash
uv run pytest -q        # 383 tests, all offline — no model needed
```

### Choosing a provider

Model access goes through `coursekit.providers`, so the endpoint is configuration rather than
code. `PROVIDER` selects it:

| `PROVIDER` | Endpoint | Notes |
|---|---|---|
| `lm_studio` *(default)* | `http://localhost:1234/v1/` | local; what this was built and tested against |
| `ollama` | `http://localhost:11434/v1/` | local |
| `openai` | OpenAI | needs `OPENAI_API_KEY` |

`LOCAL_HOST_URL` overrides the endpoint for whichever provider is selected. Only providers
speaking the OpenAI tool-calling format are implemented today; Anthropic uses a different
`tool_use` shape and would need its own implementation behind the same interface.

## Generating quizzes

### See what it would do (free, no model)

```bash
uv run python app.py "/path/to/course export" --dry-run
```

Lists every week it found and where each would be written.

### Generate

```bash
# one week
uv run python app.py "/path/to/course export" --week 3

# a range, or the whole course
uv run python app.py "/path/to/course export" --weeks 3-8
uv run python app.py "/path/to/course export"
```

`PATH` is a markdown file **or** a directory. Given a directory it picks up per-week transcripts
(`week-*.md`). Expect a few minutes per week on a local model.

**Input is decoupled** — any markdown works. If the path happens to sit under a videotranscriber
project (marked by a `.vtconfig/` folder), quizbot reads its `context.yaml` to enrich the prompt
with week titles and module names. It never requires it.

### Where output goes

**With the course, never in this repo.** Artifacts land in a `quizzes/` tree beside the course's
own files:

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

## Generating pages

The same tool builds **course pages** — the week's narrative page a student lands on — with
`--pages`:

```bash
uv run python app.py "/path/to/course export" --pages --week 3
```

A page is a canonical `page.json` (blocks: headings, concept bullets, code, glossary, callouts)
plus a rendered `pages/<week>/<slug>.html`, written beside the course like the quizzes. The model
builds the teaching outline from the transcript; it **never writes a link** — a page's references,
example works, and embeds (p5 sketches, slideshows, videos) come from an instructor-authored
supplements file, merged in at render time so they survive regeneration:

```yaml
# <course root>/.vtconfig/pages/week-3-repetition.yaml
references:
  - label: "Casey Reas — Process Compendium"
    url:   "https://reas.com/"
examples:
  - label: "Week 3 — Loops sketch"
    embed: true                                    # renders as an <iframe> if the host is allowed
    url:   "https://editor.p5js.org/…/full/…"
```

Page prompts live in `prompts/page/` and are overridable per course exactly like the quiz prompts
(`.vtconfig/prompts/page/`); `page.yaml` is the page generator's sibling of `quiz.yaml`.

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
> course-package one brings the quiz in **empty**.

Each quiz arrives with 5 question groups, each drawing 1 of 4 variants, plus a description and
grading criteria.

## Commands

| Command                         | What it does                                |
| ------------------------------- | ------------------------------------------- |
| `app.py PATH --dry-run`         | List the weeks it would process. No model.  |
| `app.py PATH --week 3`          | Generate one week. Repeatable.              |
| `app.py PATH --weeks 3-8`       | Generate an inclusive range.                |
| `app.py PATH`                   | Generate every week found.                  |
| `app.py PATH --pages`           | Generate course pages instead of quizzes.   |
| `app.py PATH --output-root DIR` | Write elsewhere instead of with the course. |
| `app.py PATH --max-iters N`     | Cap model turns per week (default 80).      |
| `app.py --to-qti DIR`           | One Canvas `.zip` per week. Model-free.     |
| `app.py --to-qti DIR --bundle`  | One `.zip` for all weeks. Model-free.       |
| `uv run pytest -q`              | Run the test suite. Fully offline.          |

Exit codes: `0` success · `1` a week failed to finalize · `2` the model could not be loaded.

## Layout

Everything is one package, `coursekit/`, with a **shared spine** and one subpackage per
*generator*. The spine imports nothing from a generator; a generator is the quiz pattern with a
different IR and emitter, so the second one (pages) reuses the driver, providers, prompts, and
config rather than re-copying them.

| Path | Role |
| --- | --- |
| `coursekit/providers/` | Model access: the tool-calling `Provider` contract |
| `coursekit/prompts.py` | Prompt library loader — project overrides beat shipped files |
| `coursekit/courseconfig.py` | Reads a course's `.vtconfig/` — structure, settings, week keys |
| `coursekit/hardware.py` | RAM pre-flight for model loading |
| `coursekit/discover.py` | Finds transcripts, resolves output paths |
| `coursekit/pipeline.py` | The generator-agnostic driver: `run_unit`, `run_course`, the model loop |
| `coursekit/generate/base.py` | The `Generator` seam both generators implement, and `RunResult` |
| `coursekit/generate/quiz/` | The quiz generator — `bank.py` (IR), `tools.py`, `context.py`, `generator.py` |
| `coursekit/generate/page/` | The page generator — `page.py` (IR), `tools.py`, `renderer.py`, `components/` |
| `coursekit/emit/` | Emitters: `gift.py`, `qti.py` (quizzes), `html.py` (pages) |
| `prompts/quiz/` · `prompts/page/` | The shipped prompts, as editable Markdown |
| `app.py` | CLI only — arg parsing and summaries |

### Changing the prompts

The prompts are files, not strings in code — `prompts/quiz/system.md` (the rules governing how the
model records questions) and `prompts/quiz/task.md` (the brief: how many concepts, what mix of
types). Edit them in place to change behaviour everywhere.

To change them for **one course only**, drop a replacement next to that course's content and
quizbot prefers it, falling back to the shipped file for anything you don't override:

```
<course root>/.vtconfig/prompts/quiz/task.md
```

### Per-course settings — `quiz.yaml`

A course can also carry its own settings, in `<course root>/.vtconfig/quiz.yaml`. Every key is
optional; anything absent falls back to the default. This file is quizbot's alone — it sits beside
the transcriber's `config.yaml` but neither tool reads the other's.

```yaml
# <course root>/.vtconfig/quiz.yaml
model: qwen2.5-32b-instruct   # used when MODEL_NAME is not set in the environment
system_prompt: system         # which prompts/quiz/<name>.md to use for the rules…
task_prompt: exam             # …and for the brief (default: system / task)
```

`task_prompt: exam` tells quizbot to load `exam.md` instead of `task.md` — resolved the same way as
any prompt: the course's own `.vtconfig/prompts/quiz/exam.md` if present, otherwise the shipped one.
So a course names a variant here and supplies the variant's file alongside it. `MODEL_NAME` in the
environment still wins over `model` here; the file is the per-course default, not an override.

Everything a course puts under `.vtconfig/` is read but never written by quizbot.

## Notes

**The model is an unreliable driver, and the loop expects it.** A local model will sometimes stop
before finishing or spin on a rejected call. `pipeline.loop` checks the bank rather than trusting
the model, nudges it back on track within a bounded budget, and bails on a rejection spiral instead
of burning the whole turn allowance.

**Guardrails are steering, not just validation.** When the model reuses a correct-answer position,
the rejection tells it which positions are still free. Errors are written for the model to act on.

**Model choice is a RAM question.** On a 32GB machine a ~15GB model is the practical ceiling.
Quizbot warns before a run if the configured model won't fit, and turns LM Studio's opaque load
failure into a readable message.

## Limitations

- **Module placement** isn't supported. Quizzes import into the Quizzes list, not into weekly
  modules.
- **GIFT output is unverified** against a live Moodle. It's there as readable plain text; Canvas QTI
  is the tested path.

Both the per-week `.zip` and the `--bundle` package have been **imported into a live Canvas course
and confirmed working**, with the question groups randomizing as intended.
