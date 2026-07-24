# coursekit

Turns a course's lecture transcripts into Canvas-ready artifacts — randomized **quizzes** and course
**pages** — using a local, tool-calling LLM. It runs fully offline against a model you host (LM Studio
by default).

## What it does

Two generators today, both the same shape: point them at a week's transcript and they drive a local
model through **tool calls** into a canonical JSON form, then emit platform files. Prose is never the
artifact — the model *commits* each piece through a tool call, so a revision overwrites rather than
piling up (an early free-text version kept losing final questions among the model's own drafts).

- **Quizzes** — 5 concepts × 4 variants; each concept becomes a Canvas *question group* that draws one
  variant at random, so every student gets a different version. `bank.json` → Canvas QTI `.zip`
  (+ GIFT). → [Generating quizzes](docs/quizzes.md)
- **Pages** — the week's narrative page: a teaching outline (headings, concept bullets, code, glossary)
  the model builds from the transcript, plus instructor-supplied references and embeds. `page.json` →
  Canvas-safe HTML. → [Course pages](docs/pages.md)

Every input converges on one **canonical form** (`bank.json`, `page.json`) that the emitters read —
so adding a platform is one emitter, not a rewrite. That, plus a shared spine (`coursekit/`) both
generators sit on, is the whole architecture. See
[agent/architecture.md](agent/architecture.md) for the map.

## Requirements

- **Python 3.12+** and [uv](https://docs.astral.sh/uv/)
- A **tool-calling model** behind one of the supported providers — by default
  [LM Studio](https://lmstudio.ai/) running its local server
- macOS for the RAM pre-flight check (it degrades to a no-op elsewhere)

## Install

```bash
git clone <this repo> && cd coursekit
uv sync --group dev
```

Create a `.env` in the project root with at least a `MODEL_NAME` and endpoint — see
[Configuration](docs/configuration.md) for the full set. Then verify:

```bash
uv run pytest -q        # 481 tests, all offline — no model needed
```

## Quick start

```bash
# see what it would do — free, no model
uv run python app.py "/path/to/course export" --dry-run

# both quizzes AND pages, one week (the default)
uv run python app.py "/path/to/course export" --week 3

# narrow to one kind
uv run python app.py "/path/to/course export" --pages --week 3
uv run python app.py "/path/to/course export" --quizzes --week 3
```

`PATH` is a markdown file or a directory of per-week transcripts (`week-*.md`). A run generates **both
quizzes and pages** by default (`--all`); `--quizzes` or `--pages` narrows it. Artifacts land beside
the course (`quizzes/` and `pages/` trees), never in this repo. The detailed guides below cover
output, Canvas import, and per-course configuration.

## Commands

| Command                         | What it does                                |
| ------------------------------- | ------------------------------------------- |
| `app.py PATH --dry-run`         | List the weeks it would process. No model.  |
| `app.py PATH --week 3`          | Generate one week. Repeatable.              |
| `app.py PATH --weeks 3-8`       | Generate an inclusive range.                |
| `app.py PATH`                   | Both quizzes and pages, every week found.   |
| `app.py PATH --pages`           | Only pages.                                 |
| `app.py PATH --quizzes`         | Only quizzes.                               |
| `app.py PATH --output-root DIR` | Write elsewhere instead of with the course. |
| `app.py PATH --max-iters N`     | Cap model turns per week (default 80).      |
| `app.py --to-qti DIR`           | One Canvas quiz `.zip` per week. Model-free.|
| `app.py --to-qti DIR --bundle`  | One `.zip` for all quizzes. Model-free.     |
| `app.py --to-html DIR`          | Re-render pages from `page.json`. Model-free.|
| `app.py --to-cc DIR`            | One Canvas `.imscc` of all pages. Model-free.|
| `app.py --ingest DIR`           | Documents (PDF/pptx/txt/md) → `output/week-N.md`. |
| `app.py --ingest DIR --raw`     | Same, extract only — no model, fully offline. |
| `uv run pytest -q`              | Run the test suite. Fully offline.          |

Exit codes: `0` success · `1` a unit failed to finalize · `2` the model could not be loaded.

## Documentation

The README is the high-level read; the detail lives in [`docs/`](docs/):

- **[Generating quizzes](docs/quizzes.md)** — the quiz workflow end to end: dry-run, generate, where
  output lands, and exporting to Canvas as a QTI `.zip`. Plus the six question types and how the
  hardened loop copes with an unreliable local model.
- **[Course pages](docs/pages.md)** — generating a week's page, the two-author split (model outline +
  your supplements), the supplements YAML (references, examples, embeds — including pasted `<iframe>`
  snippets), and re-rendering model-free.
- **[The domain profile](docs/domain-profile.md)** — one `.vtconfig/domain.md` per course that pins
  every generator to the right knowledge domain (p5.js, not Processing) and *corrects a transcript
  that drifts*. The main defence against plausible-but-wrong output.
- **[Page design](docs/design.md)** — the four visual identities (bauhaus, terminal, plotter,
  studio), the `style.yaml` a course picks a theme with, section roles (where design meets
  pedagogy), and the guardrails (Canvas allowlist, WCAG, alt-text) that keep a theme shippable.
- **[Configuration](docs/configuration.md)** — the `.env` environment, choosing a provider, the RAM
  pre-flight, and the per-course `.vtconfig/` files (`quiz.yaml` / `page.yaml`, prompt overrides).
- **[Canvas QTI format](docs/canvasQuizStructure.md)** — the internals behind `qti.py`: the package
  layout, namespaces, and the "imports empty" trap that cost two rounds to find. Read this before
  touching the QTI emitter.

For the architecture, the shared-spine design, and the roadmap, see
[`agent/architecture.md`](agent/architecture.md).
