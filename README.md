# coursekit

Turns a course's lecture transcripts — or its readings and slides — into Canvas-ready artifacts: randomized **quizzes** and course **pages**, using a local, tool-calling LLM. It runs fully offline against a model you host (LM Studio by default).

## What it does

Two generators today, both the same shape: point them at a week's transcript and they drive a local model through **tool calls** into a canonical JSON form, then emit platform files. Prose is never the artifact — the model _commits_ each piece through a tool call, so a revision overwrites rather than piling up (an early free-text version kept losing final questions among the model's own drafts).

- **Quizzes** — 5 concepts × 4 variants; each concept becomes a Canvas _question group_ that draws one variant at random, so every student gets a different version. `bank.json` → Canvas QTI `.zip` (+ GIFT). → [Generating quizzes](docs/quizzes.md)
- **Pages** — the week's narrative page: a teaching outline (headings, concept bullets, code, glossary) the model builds from the transcript, plus instructor-supplied references and embeds. `page.json` → Canvas-safe HTML. → [Course pages](docs/pages.md)

Two supporting phases bracket the generators. **Ingest** turns documents (PDF, slides, `.docx`) into the same week text the generators read, so a course with no video still works. **Emit** packages the canonical JSON into Canvas files, model-free — up to a whole-course `.imscc` that imports pages *and* quizzes as week modules in one go.

Every input converges on one **canonical form** (`bank.json`, `page.json`) that the emitters read — so adding a platform is one emitter, not a rewrite. That, plus a shared spine (`coursekit/`) both generators sit on, is the whole architecture. See [agent/architecture.md](agent/architecture.md) for the map.

## Requirements

- **Python 3.12+** and [uv](https://docs.astral.sh/uv/)
- A **tool-calling model** behind one of the supported providers — by default [LM Studio](https://lmstudio.ai/) running its local server
- macOS for the RAM pre-flight check (it degrades to a no-op elsewhere)

## Install

```bash
git clone https://github.com/andrew-atkinson/quizbot.git && cd coursekit
uv sync --group dev     # also installs the `coursekit` command (editable)
```

Create a `.env` in the project root with at least a `MODEL_NAME` and endpoint — see [Configuration](docs/configuration.md) for the full set. Then verify:

```bash
uv run pytest           # 522 tests, all offline — no model needed (names each, not just dots)
```

## Quick start

The CLI has three verbs, one per phase: **`ingest`** (documents → week text), **`generate`** (week text → quizzes/pages, the model), **`emit`** (canonical JSON → Canvas packages, model-free).

```bash
# see what it would do — free, no model
uv run coursekit generate "/path/to/course export" --dry-run

# both quizzes AND pages, one week (the default)
uv run coursekit generate "/path/to/course export" --week 3

# narrow to one kind
uv run coursekit generate "/path/to/course export" --pages --week 3
uv run coursekit generate "/path/to/course export" --quizzes --week 3
```

`PATH` is a markdown file or a directory of per-week transcripts (`week-*.md`). A `generate` run produces **both quizzes and pages** by default; `--quizzes` or `--pages` narrows it. Artifacts land beside the course (`quizzes/` and `pages/` trees), never in this repo. (`python app.py <verb> …` is equivalent to `coursekit <verb> …` everywhere below.) The detailed guides cover output, Canvas import, and per-course configuration.

## Commands

The CLI is three verbs, in the order work flows through them:

- **`ingest`** — turn a week's documents (PDF, slides, `.docx`) into the week text the generators read.
- **`generate`** — turn that week text into quizzes and pages (the model-driven step).
- **`emit`** — package the canonical JSON into Canvas files, model-free — up to a whole-course `.imscc`.

| Ingest Commands               | What it does                                               | Uses LLM |
| ----------------------------- | ---------------------------------------------------------- | -------- |
| `coursekit ingest PATH`       | Documents (PDF/docx/odt/pptx/txt/md) → `output/week-N.md`. | ✓        |
| `coursekit ingest PATH --raw` | Same, extract only, fully offline.                         | x        |

| Generate Commands                               | What it does                                                     | Uses LLM |
| ----------------------------------------------- | ---------------------------------------------------------------- | -------- |
| `coursekit generate PATH`                       | Both quizzes and pages, every week found.                        | ✓        |
| `coursekit generate PATH --dry-run`             | List the weeks it would process.                                 | x        |
| `coursekit generate PATH --week 3`              | One week. `--week` is repeatable; `--weeks 3-8` a range.         | ✓        |
| `coursekit generate PATH --pages`               | Only pages (`--quizzes` for only quizzes).                       | ✓        |
| `coursekit generate PATH --pages --detail full` | Page depth: `brief` / `medium` / `full` (overrides `page.yaml`). | ✓        |
| `coursekit generate PATH --output-root DIR`     | Write elsewhere instead of with the course.                      | ✓        |
| `coursekit generate PATH --max-iters N`         | Cap model turns per week (default 80).                           | ✓        |

| Emit Commands                      | What it does                      | Uses LLM |
| ---------------------------------- | --------------------------------- | -------- |
| `coursekit emit qti PATH`          | One Canvas quiz `.zip` per week.  | x        |
| `coursekit emit qti PATH --bundle` | One `.zip` for all quizzes.       | x        |
| `coursekit emit html PATH`         | Re-render pages from `page.json`. | x        |
| `coursekit emit cc PATH`           | One Canvas `.imscc` of all pages. | x        |
| `coursekit emit course PATH`       | One Canvas `.imscc` of the whole course — pages **and** quizzes, in week modules. | x |

| Test Command       | What it does        | Uses LLM |
| ------------------ | ------------------- | -------- |
| `uv run pytest`    | Run the test suite. | x        |

Exit codes: `0` success · `1` a unit failed to finalize · `2` the model could not be loaded.

## Documentation

The README is the high-level read; the detail lives in [`docs/`](docs/):

- **[Generating quizzes](docs/quizzes.md)** — the quiz workflow end to end: dry-run, generate, where output lands, and exporting to Canvas as a QTI `.zip`. Plus the six question types and how the hardened loop copes with an unreliable local model.
- **[Course pages](docs/pages.md)** — generating a week's page, the two-author split (model outline + your supplements), the supplements YAML (references, examples, embeds — including pasted `<iframe>` snippets), and re-rendering model-free.
- **[The domain profile](docs/domain-profile.md)** — one `.vtconfig/domain.md` per course that pins every generator to the right knowledge domain (p5.js, not Processing) and _corrects a transcript that drifts_. The main defence against plausible-but-wrong output.
- **[Page design](docs/design.md)** — the four visual identities (bauhaus, terminal, plotter, studio), the `style.yaml` a course picks a theme with, section roles (where design meets pedagogy), and the guardrails (Canvas allowlist, WCAG, alt-text) that keep a theme shippable.
- **[Configuration](docs/configuration.md)** — the `.env` environment, choosing a provider, the RAM pre-flight, and the per-course `.vtconfig/` files (`quiz.yaml` / `page.yaml`, prompt overrides).
- **[Canvas QTI format](docs/canvasQuizStructure.md)** — the internals behind `qti.py`: the package layout, namespaces, and the "imports empty" trap that cost two rounds to find. Read this before
  touching the QTI emitter.

For the architecture, the shared-spine design, and the roadmap, see
[`agent/architecture.md`](agent/architecture.md).
