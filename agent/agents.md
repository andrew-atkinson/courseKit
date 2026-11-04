# `agent/` — working docs

The durable reference and planning material for this project, kept in the repo so it survives a
cold start. Read this first to know which of the others you want.

**This is not the conventions file.** How to *work* here — the facticity discipline, ground-truth
locations, decisions not derivable from the code — lives in [`CLAUDE.md`](../CLAUDE.md) at the repo
root, which loads every session. `agent/` is the deeper material that `CLAUDE.md` points into.

## The docs

| Doc | What it is | Read it when |
| --- | --- | --- |
| [`architecture.md`](architecture.md) | The internal structural map — the generator seam, the output-worth layer, the course model, the one-writer-per-file structure rule, the dependency direction, the order of operations, and what is not yet closed. Its user-facing half (the key, the four layers, what each `coursekit` command reads and writes) is [`docs/architecture.md`](../docs/architecture.md). Mermaid source, render-checked; both are published together as one artifact. | You're weighing a structural change (a new command or generator, a new emitter, the transcriber migration) or need the internals behind the user guide's diagrams. |
| [`roadmap.md`](roadmap.md) | The forward plan and the dated history: the current focus, every open item by area, and a Shipped changelog. | You're choosing what's next, or need to know whether something already landed. |
| [`structure-review.md`](structure-review.md) | The 2026-10 step back that proposed the `CORE` arc: what coursekit is trying to become, and where its structure falls short. A proposal, so it describes the starting point, not today. | You want the reasoning behind a `CORE` item. |
| [`core-1-audit.md`](core-1-audit.md) · [`core-2-design.md`](core-2-design.md) · [`core-3-design.md`](core-3-design.md) | The working record of each `CORE` arc: the audit or design, the increments and their pass criteria, the decisions, and what each step found. | You're continuing an arc, or asking why a piece of it is the way it is. |
| [`local-canvas-testing.md`](local-canvas-testing.md) · [`model-test-plan.md`](model-test-plan.md) | How to verify imports on a local Canvas, and the manual checklist for what the offline suite can't judge. | You're testing an emitter against Canvas, or running acceptance on a model. |
| [`todo.md`](todo.md) | The ideas dump and forward plan — feature ideas (not all to be built), the quizbot→coursekit restructure rationale, and housekeeping. Some entries carry investigation notes (e.g. why per-video Panopto links won't work). | You're picking the next thing to do, or about to propose something that may already have been thought through and parked here. |
| [`GIFT_format_compact.md`](GIFT_format_compact.md) | A token-efficient, rigorous reference for the GIFT quiz format, derived from Moodle's own parser. The spec behind `gift.py`. | You're touching `gift.py` or reasoning about GIFT escaping, type detection, or question syntax. |

## The whole map of entry points

- **[`CLAUDE.md`](../CLAUDE.md)** — conventions and durable facts; loads automatically.
- **[`README.md`](../README.md)** — how to install, configure, and run the tool; the user-facing surface.
- **`agent/`** (this directory) — architecture, plans, and the format reference.
- **`docs/`** — the tracked user guides (`*.md`, `overview.html`, and
  `architecture-diagram.html`, the one-page picture of the pipeline); anything else there is gitignored.

## Keeping this honest

When a doc here makes a factual claim — a line count, a file's role, a "nobody reads this" — it must
be true against the current tree, not a past one. Stale claims in these files have bitten before; the
test-count guardrail ([`tests/test_docs_facts.py`](../tests/test_docs_facts.py)) exists because of it.
If you change what a doc describes, update the doc in the same pass.
