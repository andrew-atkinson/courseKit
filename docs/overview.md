# coursekit — what it is and what it does

A capabilities overview.
A styled HTML version of this same content sits beside it at [overview.html](overview.html).
For the high-level product read see the [README](../README.md); for every CLI verb and flag see the [command reference](commands.md).

## In one line

coursekit turns a course's own material — lectures, readings, slides — into correct, well-taught, Canvas/Moodle-ready quizzes and pages, running on a language model you host yourself, so your content never leaves your machine.

## The one load-bearing idea

Every input converges on one canonical form — `bank.json` for quizzes, `page.json` for pages — and every export reads only that form.
Adding a new LMS or file format is therefore one new emitter, not a rewrite of the whole tool.
The model *commits* each finished piece through a structured tool call rather than free text, so a revision overwrites its slot instead of piling up discarded drafts.

## The workflow, phase by phase

coursekit is a command-line tool organized as a small pipeline; each phase is a verb, and it is clear which ones use the model.

- **`ingest`** — turns a week's documents (PDF, PowerPoint, Word, ODT, plain text, Markdown) into the consolidated week text the generators read. A folder of readings and slides becomes one source-tagged week document. `--raw` does deterministic extraction only, fully offline.
- **`propose`** — scans a course tree and *declares* its structure (weeks plus typed sources) into an explicit manifest, instead of guessing structure from filenames. It surfaces any files it couldn't place rather than silently dropping them, and `--model` handles irregular trees that don't encode weeks in their names.
- **`analyze`** — builds each week's concept map, an instructor-editable list of the concepts a week teaches, which grounds both generation and evaluation.
- **`generate`** — the model step: turns week text into randomized quizzes and designed pages. It can target the whole course, selected weeks, or — with `--source` — a single document for an à-la-carte quiz. A run ends with a cold-read review of what it produced, by default.
- **`emit`** — packages the canonical JSON into LMS files, with no model involved: a Canvas quiz `.zip` (QTI), standalone or re-rendered page HTML, a Common Cartridge `.imscc` of pages, or one whole-course `.imscc` of pages and quizzes together in weekly modules.

## Quizzes

Quizzes are randomized: each concept becomes a group of variant questions, and every student draws a different variant per concept.
Six question types are supported — multiple choice, multiple-answer (select all), true/false, short answer, numerical, and matching.
A hardened tool-calling loop copes with an unreliable local model — guardrails are written as steering, so a rejected question becomes a correction the model can act on rather than a failed run.

## Pages

Pages are designed teaching artifacts, not plain text dumps.
They compose from a catalog of typed content blocks — section headings, pull quotes, columns, cards, callouts, glossaries, code, and collapsible "predict-then-reveal" foldouts — each chosen for a documented pedagogical function (drawn from Cognitive Load Theory and Universal Design for Learning).
A page can take one of three functions: a full teaching page, a glossary companion (terms beside the video), or an orientation/overview page; the teaching generator auto-selects a monolithic or decomposed strategy by length.
Everything renders to Canvas-safe HTML — restricted to the properties Canvas's sanitizer actually allows — so it survives import intact, including flexbox layout and native collapsible sections.
Instructor-supplied links, references, and embeds (slideshows, videos, sketches) come in through a per-course supplements file; the model is never allowed to invent a URL.

## The design system

Four shipped visual identities — bauhaus, terminal, plotter, and studio — each a full design language (type, spacing, shape, color, per-component treatment), selected per course in a `style.yaml`.
Themes apply at render time, so changing one re-renders every page model-free.
Every theme is checked for WCAG AA contrast, and every emitted style property is verified against the Canvas allowlist.

## Evaluation — the part most tools don't have

coursekit doesn't just generate; it *measures* whether the result is pedagogically sound, through five calibrated critics that read already-generated content off disk:

- **Facticity** (quizzes and pages) — is each claim or answer correct?
- **Pedagogy rubric** (pages) — does the page scan, signal its key idea, engage, show worked examples, and prompt retrieval? Scored 0–3 with coaching notes, not a pass/fail.
- **Concept delivery** (pages) — for each concept the week teaches, is it actually conveyed well: explained, exemplified, pitched right?
- **Groundedness** (pages and quizzes) — is the content drawn from *the source*, or from the model's own prior knowledge? A low-coverage quiz is a warning that the source is too thin to ground it; on pages, contradictions with the material are flagged.

`evaluate --all` runs the whole battery and writes a report per dimension.
`fix` then regenerates each flagged item in place and re-renders — quizzes and pages, including glossary and overview pages — so a just-flagged item is repaired at once.

## Local-first, portable, faculty-owned

It runs against a model *you* host — LM Studio by default, or any OpenAI-compatible provider — so course material and intellectual property stay on your machine, with no cloud dependency and no per-seat cost.
A per-course domain profile pins every generator to the right knowledge domain (`p5.js`, not Processing) and corrects a transcript that drifts.
The output is standard, reviewable import files that work without an LMS API token — which matters for the many adjunct and contingent faculty who can't get one.
By design it handles instructor-authored material only, never student submissions, which keeps it clear of FERPA scope.

## Status

Today coursekit is a working command-line prototype — a fit for the technically comfortable early adopter.
The generation and evaluation engines are real and run offline against a fast test suite; the road ahead is largely the interface — a friendly app any instructor could use, and eventually a packaged desktop app with the local model bundled in.
