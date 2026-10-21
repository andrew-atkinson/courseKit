# Structure review — the project's ambitions vs its structure (2026-10-19; revised 2026-10-21: units, not weeks)

A step back from the feature queue.
Several recent bugs were silent (a feature switched on that quietly did nothing), and they shared causes.
This review asks why, starting from what coursekit is trying to become rather than from the bugs.
It is a proposal: [architecture.md](architecture.md) stays the description of what *is*, and is updated as each item below lands.
The roadmap carries the work as the `CORE` area.

## 1. What coursekit is trying to be

Read from the vision line, the README, the overview, and the roadmap's areas, the ambition has nine strands:

1. **A generator of many artifact kinds** — quizzes, pages, assignments today; discussions, glossaries, decks, rubrics next (`ASMT`, `PAGE`, `RICH`).
2. **An instrument that measures and repairs** — the critics, groundedness, `fix` (`EVAL`).
3. **A course-level reasoner** — structure, grading, the census and its gaps, sequencing, prerequisites, a time model, advisory (`STRC`, `CRSE`, `FLOW-9`).
4. **Faculty-owned** — coursekit drafts, the faculty decides; everything is a reviewable, hand-editable file (the `propose` pattern).
5. **Robust on unreliable local models** — the hardened tool-calling loop.
6. **Portable delivery** — standard files first, APIs later (`SHIP`).
7. **An app for non-technical faculty** — block-level edit and re-run, versioning, a course dashboard (`UX`, `RICH-6`).
8. **A shared spine** with the transcriber and future tools.
9. **Design as a teaching instrument, authored visually** — the themes and the pedagogy↔design mapping today (`docs/design.md`); a concept-map graph editor, live preview, a theme gallery, and a course-health dashboard next (`UX-4`, `RICH-6`).

Strands 7 and 9 together mean the eventual interface is *visual authoring*: an instructor changes one thing — a concept, a theme, one unit's material — and sees exactly what it affects re-render.
That needs coursekit to know what each artifact was made from and to re-run one operation on one scope, which the current structure can't do (3.3, 3.6).

## 2. What the structure was built for

The structure was designed around strand 1: **a per-week artifact generator.**
A unit of teaching (`Unit` — in practice always a week) goes through a model loop into a canonical IR file, and model-free emitters read that file.
Every verb is its own program that walks the course folder and does its job.

That design is good at what it was built for, and parts of it are the best things in the codebase:

- **The waist** — one IR per artifact kind, emitters that read only the IR, emit with no model.
- **The Generator seam** — the driver knows nothing about quizzes or pages.
- **One writer per file, composed on read** — and files, not a database.

Those stay.
The problem is that strands 3, 4, 7 and 9 have since grown on top of a structure that has no place for them.

## 3. Where the ambition has outgrown the structure

### 3.1 There is no course model

Each verb re-derives "the course" from disk on its own.
There are ~15 independent folder walkers (counted 2026-10-19), and they don't agree: the census looks for `quizzes/*/bank.json`, the QTI emitter for `**/bank.json`, and assignments are found by two different patterns.
Two implementations of one question drift apart — which is exactly the census/emitter grading-group bug.
`Unit` is built by hand in more than one place, so one copy can forget a field — which is exactly ASMT-19 (the targeted quiz's unit has no week number, so its EU question silently never happens).
A course-level reasoner needs **one model of the course that every verb reads.**

### 3.2 The unit is identified by a week number

The code already has the right word — `Unit` — but a unit's identity is a week number.
It is parsed out of names (`week_key` turns `week-3.md` into `"3"`), carried as `week_num`/`week_slug`, written into the IR as `week_ref`, selected with `--week`, scoped in expectations as `scope: week`, reported per week by the census, and declared under `weeks:` in the transcriber's `context.yaml`.
~850 lines of the package mention "week" (counted 2026-10-21).

A week is an arbitrary unit.
Courses meet twice a week, in intensive blocks, on a quarter calendar, self-paced, or by module with no weekly rhythm at all.
"Week" also quietly fuses three different things:

- **The teaching block** — the content taught together (what generation and the concept map are about).
- **Its place in the sequence** — first, second, third (what prerequisites and "teaches toward" are about).
- **Its place in calendar time** — when it happens and how long it lasts (what spacing, pacing and a time model are about — CRSE-2, CRSE-5).

For a weekly course the three coincide, which is how one word came to stand for all of them.
The target separates them: **a unit has an id, an order, a label, an optional module, and an optional calendar slot.**
"Week 3" becomes one possible *label* for a unit, not its identity; a twice-weekly course has two units in a calendar week, and an intensive has several in a day.

Units are also not the only grain.
A single-document quiz fakes a unit slug (`week-N-doc`); module scope exists only inside the census; course-scope artifacts have no natural home.
The ambition needs four grains — **course > module > unit > source document** — and an artifact attached to whichever grain it belongs to (ASMT-19's document-level EU, STRC-1's modules, assignments per module, CRSE's course-level reasoning).

### 3.3 Artifacts have no lifecycle or provenance

An artifact's state is implied by which files exist (`bank.partial.json`, a findings file).
Nothing records what an artifact was made *from* — which source text, concept map, config, prompt, or model.
So coursekit can't tell a current artifact from a stale one (unit 7's out-of-sync quiz went unnoticed), can't show where each unit is in the pipeline (FLOW-9 Phase 2), can't offer undo or history (UX-5), and can't back the vision's "measurably" across runs.

### 3.4 Who decided a value is not recorded

A value can come from the faculty (declared), from a deterministic rule (derived), or from the model (proposed).
Nothing records which.
That is how code ended up making faculty decisions silently — the EU rule, model-chosen rubric points, the equal-weight placeholders that had to be defended in prose.
The census's `expectation_basis` (declared vs modal) is the first place authority became data; it should be the norm wherever a value can come from more than one source.

### 3.5 The contracts are implicit

The loaders follow a written rule — "context is enrichment: degrade, never raise" (`courseconfig`, `coursestructure`, `load_for_unit`).
That was right when context was optional.
Features have since been built that *need* context, but the loaders can't tell them apart from features that don't, so a missing input collapses to `None`/`""` and the feature quietly does less.
There are ~40 broad `except Exception` handlers, ~a third of them falling back to an empty value, and ~30 `getattr(x, name, default)` reads (counted 2026-10-19) — not all wrong, but nothing marks which are.
The offline tests use complete fixtures, so the skip paths never fail a test.

### 3.6 The library is shaped like a CLI

The quiz and page generators hold the artifact being built in module-level variables (`bank._bank`, `page._page`): one job per process, kept correct only by reset discipline.
`cli.py` holds orchestration an app would have to duplicate (review-after-generate, the analyze wiring, evaluate's report assembly).
Errors are process exits and warnings are `print()`s (UX-8).
Strand 7 needs the verbs to be library operations that return results, with the CLI as one thin interface over them.

## 4. The target structure

Four layers, each one only calling down:

1. **Course model.**
   A `Course`, loaded once from the folder by the only walker: the scope tree (course > modules > units > sources), the declared structure, grading and expectations, the concept maps, and an index of every artifact.
   A unit is a view (`course.unit("3")`), never hand-built, with an id, an order, a label, an optional module, and an optional calendar slot.
   The census becomes a report over the `Course`; emitters find artifacts through its index.
2. **Artifact records.**
   A uniform envelope around each IR: kind, scope node, status (in progress / final / evaluated / stale), provenance (input hashes, model, prompt name, config), and its evaluations.
   Stale means an input hash no longer matches.
   The IR stays the waist; the record is metadata beside it.
3. **Operations.**
   Each verb is a library function — `generate(course, scope, kind, options)`, `evaluate`, `fix`, `emit`, `propose`, `census` — that declares which inputs it requires when switched on and returns a result: the artifacts touched plus an outcome report (errors, warnings, skips — UX-8's types).
   Generator state lives in an instance, not a module.
4. **Interfaces.**
   The CLI renders results; the app later renders the same results.

Unchanged: files not a database, one writer per file, the waist, the Generator seam, local-first, no framework.
Out of scope: multi-tenancy and hosting (`SVC-4`).

Three rules hold across the layers (the robustness rules):

- **The consumer decides what is optional, not the loader.**
  Loaders report absence with a reason; a feature that is switched on treats its inputs as required.
- **One builder per object, one function per rule.**
  No second copy of a constructor or a resolution rule.
- **Every skip is recorded.**
  A degrade may be legitimate, but never silent; it lands in the outcome report.

The test pattern that goes with them: for each opt-in feature, a test that switching it on either produces its artifact or fails loudly — never a no-op.

## 5. Getting there without a rewrite

Incremental, one branch per step, each with a pass criterion; features keep shipping between steps.

1. **Contracts first** (`CORE-1`) — UX-8's error/warning/outcome types, the fallback audit, ASMT-19 layer 1 as the first fix.
   Small, and every later step reports through it.
2. **The course model, v1** (`CORE-2`) — one loader and artifact index; move the census and the emit sources onto it first (the two that drifted); build units from it.
   Units are defined here with their own identity (id, order, label, module, calendar slot) — building the course model on week numbers and redoing it later would be the expensive path.
3. **Generator state into instances** (`CORE-3`) — `bank`/`page` lose their module globals.
4. **Artifact records** (`CORE-4`) — status and provenance; census Phase 2 and stale detection fall out of it.
5. **Units, not weeks, everywhere** (`CORE-5`) — move the remaining week-identified code onto units, and add document and module nodes; ASMT-19 layer 2 and STRC-1 build on it.
   It is a migration, not a rename: existing courses keep working.
   On-disk names stay — `week-3` is a perfectly good unit id for a weekly course; what stops is *deriving meaning* from the `week-N` pattern, since order comes from the declared sequence.
   Old names survive as aliases at the edges: `--week` beside `--unit`, `week_ref` read as `unit_ref`, `scope: week` read as `scope: unit`.
   `weeks:` in `context.yaml` is the transcriber's contract, so its successor is agreed with that repo, not changed from this side; coursekit reads `weeks:` as units meanwhile.
6. **Authority as data** (`CORE-6`) — declared / derived / proposed where a value can come from more than one place.
7. **The operations layer** (`CORE-7`) — verbs out of `cli.py` into library functions; the app's prerequisite.

`architecture.md` (last verified 2026-07-31; it predates assignments, the census, grading, and expectations) is refreshed alongside step 2, when the map actually changes.
