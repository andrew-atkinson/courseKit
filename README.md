# coursekit

**Turn a course's own material into correct, well-taught, Canvas/Moodle-ready content — on a model you run yourself.** Point it at a week's lectures, readings, or slides and it drafts the quizzes and pages, checks them for pedagogical soundness, and packages them for your LMS — without your content ever leaving your machine.

> **Status: working prototype.** Today coursekit is a command-line tool, which means it's a fit for the technically comfortable early adopter. The goal is a friendly app any instructor can use; the interface is where much of the road ahead lies. What's below is real and runs — just from a terminal, for now.

## Who it's for

- **Teaching-focused faculty** who want their courses to be more engaging and better-taught, and who'd rather spend their time on the _subject_ than on tooling.
- **Adjunct and contingent faculty** who often can't get an LMS admin account or API token — coursekit produces standard import files, so you don't need one.
- **Instructional designers and centers for teaching & learning** who support many courses and want a repeatable way to draft and audit them.
- **Institutions** that want to raise engagement and online-course quality while keeping faculty content in faculty hands.

## What you can do

Each is "you have something → coursekit gives you something."

- **Audit an existing course for pedagogical soundness.** You have a course's material and want to know whether it actually teaches well. coursekit reads each page and quiz and reports back on three axes — is it _correct_ (facticity), does it _scan, signal, and engage_ (form), and does it actually _deliver each concept_ — as coaching, not just a pass/fail.
- **Turn a week's material into engaging, portable LMS content.** You have a transcript or readings and want quizzes and a teaching page. coursekit drafts randomized quizzes (every student gets a different variant) and a designed course page, then packages them as standard Canvas QTI / Common Cartridge files — portable, reviewable, no API token required.

On the roadmap (not yet): refreshing and updating existing content in place, building a course from just an outline, and reasoning about the spacing and timing of content across a whole term.

## Why it's different

- **Portable, reviewable artifacts.** Everything converges on one neutral form and emits to standard files (Canvas QTI `.zip`, Common Cartridge `.imscc`, Moodle GIFT). You get a reviewable package you can import anywhere — no lock-in to one platform's API, and it works for the many faculty who can't get a token.
- **Local-first.** It runs against a model _you_ host, so your course material and your intellectual property stay on your machine — no cloud dependency.
- **Evaluation, not just generation.** Most tools generate; coursekit also _measures_ whether the result is pedagogically sound. (This is the newest angle, and one we're still deepening.)

## How it works

Every input converges on one **canonical form** (`bank.json` for quizzes, `page.json` for pages) that the emitters read — so adding a platform is one emitter, not a rewrite.
Two generators sit on a shared spine (`coursekit/`), and the model _commits_ each piece through a tool call rather than free text, so a revision overwrites rather than piling up drafts.
See [agent/architecture.md](agent/architecture.md) for the map.

## Requirements

- **Python 3.12+** and [uv](https://docs.astral.sh/uv/)
- A **tool-calling model** behind one of the supported providers — by default [LM Studio](https://lmstudio.ai/) running its local server. (Setting up a local model is the main friction today; a future packaged app aims to remove it.)
- macOS for the RAM pre-flight check (it degrades to a no-op elsewhere)

## Install

```bash
git clone https://github.com/andrew-atkinson/quizbot.git && cd coursekit
uv sync --group dev     # also installs the `coursekit` command (editable)
```

Create a `.env` in the project root with at least a `MODEL_NAME` and endpoint — see [Configuration](docs/configuration.md) for the full set.
Then verify:

```bash
uv run pytest           # 711 tests, all offline — no model needed (names each, not just dots)
```

## Quick start

The CLI has four phases: **`ingest`** (documents → week text), **`analyze`** (week text → the concept map that grounds generation), **`generate`** (week text → quizzes/pages, the model), **`emit`** (canonical JSON → LMS packages, model-free).

```bash
# see what it would do — free, no model
uv run coursekit generate "/path/to/course" --dry-run

# both quizzes AND pages, one week (the default)
uv run coursekit generate "/path/to/course" --week 3

# narrow to one kind
uv run coursekit generate "/path/to/course" --pages --week 3

# check what you already have for pedagogical soundness
uv run coursekit evaluate "/path/to/course" --all
```

The full command surface — every verb, flag, and what uses the model — is the **[command reference](docs/commands.md)**.

## Documentation

The README is the high-level read; the detail lives in [`docs/`](docs/):

- **[Command reference](docs/commands.md)** — every CLI verb and flag, and which use the model.
- **[Evaluating and fixing](docs/evaluating.md)** — the audit → repair loop: `analyze` (the concept map), `evaluate` (the cold-read checks), and `fix` (regenerate flagged items in place). The part that makes a local model trustworthy.
- **[Generating quizzes](docs/quizzes.md)** — the quiz workflow end to end: dry-run, generate, where output lands, and exporting to Canvas as a QTI `.zip`. Plus the six question types and how the hardened loop copes with an unreliable local model.
- **[Course pages](docs/pages.md)** — generating a week's page, the two-author split (model outline + your supplements), the supplements YAML (references, examples, embeds — including pasted `<iframe>` snippets), and re-rendering model-free.
- **[The domain profile](docs/domain-profile.md)** — one `.vtconfig/domain.md` per course that pins every generator to the right knowledge domain (p5.js, not Processing) and _corrects a transcript that drifts_. The main defence against plausible-but-wrong output.
- **[Page design](docs/design.md)** — the four visual identities (bauhaus, terminal, plotter, studio), the `style.yaml` a course picks a theme with, section roles (where design meets pedagogy), and the guardrails (Canvas allowlist, WCAG, alt-text) that keep a theme shippable.
- **[Configuration](docs/configuration.md)** — the `.env` environment, choosing a provider, the RAM pre-flight, and the per-course `.vtconfig/` files (`quiz.yaml` / `page.yaml`, prompt overrides).
- **[Canvas QTI format](docs/canvasQuizStructure.md)** — the internals behind `qti.py`: the package layout, namespaces, and the "imports empty" trap that cost two rounds to find. Read this before touching the QTI emitter.

For the architecture, the shared-spine design, and the roadmap, see [`agent/architecture.md`](agent/architecture.md).
