# `agent/` — working docs

The durable reference and planning material for this project, kept in the repo so it survives a
cold start. Read this first to know which of the others you want.

**This is not the conventions file.** How to *work* here — the facticity discipline, ground-truth
locations, decisions not derivable from the code — lives in [`CLAUDE.md`](../CLAUDE.md) at the repo
root, which loads every session. `agent/` is the deeper material that `CLAUDE.md` points into.

## The docs

| Doc | What it is | Read it when |
| --- | --- | --- |
| [`architecture.md`](architecture.md) | The structural map — data flow, the shared spine, the dependency direction, and the migration plan. Mermaid source; also published as an artifact. | You need to see how quizbot, `coursekit`, and the videotranscriber fit, or you're weighing a structural change (the rename, a new generator, the transcriber migration). |
| [`todo.md`](todo.md) | The ideas dump and forward plan — feature ideas (not all to be built), the quizbot→coursekit restructure rationale, and housekeeping. Some entries carry investigation notes (e.g. why per-video Panopto links won't work). | You're picking the next thing to do, or about to propose something that may already have been thought through and parked here. |
| [`GIFT_format_compact.md`](GIFT_format_compact.md) | A token-efficient, rigorous reference for the GIFT quiz format, derived from Moodle's own parser. The spec behind `gift.py`. | You're touching `gift.py` or reasoning about GIFT escaping, type detection, or question syntax. |

## The whole map of entry points

- **[`CLAUDE.md`](../CLAUDE.md)** — conventions and durable facts; loads automatically.
- **[`README.md`](../README.md)** — how to install, configure, and run the tool; the user-facing surface.
- **`agent/`** (this directory) — architecture, plans, and the format reference.
- **`docs/`** — more references, but **gitignored**, so nothing there is in version control. The
  most valuable of them, the Canvas QTI format notes (`docs/canvasQuizStructure.md`), is the reason
  the tracked references were moved here to `agent/` instead.

## Keeping this honest

When a doc here makes a factual claim — a line count, a file's role, a "nobody reads this" — it must
be true against the current tree, not a past one. Stale claims in these files have bitten before; the
test-count guardrail ([`tests/test_docs_facts.py`](../tests/test_docs_facts.py)) exists because of it.
If you change what a doc describes, update the doc in the same pass.
