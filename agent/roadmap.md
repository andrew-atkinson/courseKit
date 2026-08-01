# coursekit roadmap

The forward-looking view. For the detailed record — measurements, dated decisions, per-course results — see the working log (kept offline). This file is the map; the log is the diary.

## Vision

> coursekit turns a course's own material into Canvas-ready artifacts that are **correct, well-taught, and reviewable** — locally, and measurably.

Every decision checks against that line: does it make artifacts more correct, better-taught, more reviewable, or the tool more usable to a real instructor? If not, it goes to the parking lot.

## How we work (the cadence)

1. **One active focus at a time.** A single _current milestone_ (below). Everything else waits.
2. **Parking lot.** A new idea gets written down immediately so it is never lost — and is **not acted on** until a regroup. Ideas are welcome; acting on them mid-focus is not.
3. **Every milestone has a "done when."** A concrete, ideally measurable acceptance (e.g. "recall > X", "5/5 discrimination", "the review runs from one command"). No open-ended work.
4. **Regroup at milestones.** When the current thing lands: review the parking lot, re-prioritise, pick the next focus. Only then.

## Current focus

> **Between focuses — regroup.** No single active milestone right now: the last stretch shipped the concept map / `analyze` phase, the targeted fix loop, and images-on-pages (see **Shipped**). The strongest candidates for the next focus, from the parking lot: the **visual / design-forward track** (next concrete build: generated diagrams), and **composable generation** (the attention/crowding answer — validate empirically first with an A/B, don't rewrite blind). Pick one deliberately.

## Workstreams

Four workstreams. Each: the goal, where it stands, and the next move.

### 1. Generate — artifacts from a course's material

- **Goal:** good quizzes and pages (later: assignments, modules, discussions, rubrics) from any course.
- **Status:** quizzes + pages solid — canonical IR (`bank.json` / `page.json`), hardened tool-call loop, design system, emitters. This is the mature, steady core.
- **Next:** steady; new generators are a breadth decision, not a current need.

### 2. Evaluate — measure quality, and improve from it

_(Evaluation exists to improve; the loop-back is its point — so "improve" lives here.)_

- **Goal:** trustworthy, measurable quality gates that raise generation quality.
- **Status:** **all three checks built + calibrated** —
  - _Facticity_ (is it correct?): quiz + page critics, domain-aware; ~98–100% recall / 0% false-flag on the synthetic sets; validated on a real course.
  - _Form_ (does it scan/signal/engage/retrieve?): the pedagogy rubric; 5/5 discrimination; drove a real prompt loop-back (course pedagogy 9.25 → 13.5 / 15).
  - _Concept delivery_ (does it actually teach the concepts?): v1; 3/3 discrimination with graded middle.
  - Backed by synthetic calibration infra (`synthesize`, `scoring`, the scorecards).
- **Next:** the loop is closed — `evaluate --all` reports all three checks and `fix` repairs flagged items in place. Parked deepenings: the coherence/development-adequacy dimension and the visual (render-and-see) pass.

### 3. Profiles — work across domains and teaching styles

- **Goal:** the tool adapts to different subjects and different instructors, composably.
- **Status:** the `domain.md` profile exists and now feeds both generators _and_ critics. Everything else is a parking-lot idea.
- **Next:** (parked) composable domain bases + a domain-suggester; pluggable pedagogy strategies; a voice/tone profile.

### 4. Deliver & course-scope — into Canvas, and across weeks

- **Goal:** artifacts land in the LMS; the tool can reason about a whole course, not just a week.
- **Status:** file delivery solid (QTI `.zip`, HTML, CC, whole-course `.imscc` — verified in real Canvas). Course-level reasoning and any API/extension path are unbuilt.
- **Next:** (parked) Canvas API/extension; a course-level evaluator (pacing, spacing, sequencing); the front-end / form-factor track.

## Parking lot

Captured, deliberately not active. Reviewed at each regroup. `[theme]` tags where it belongs.

- **assignments and discussions** need to be added.
- **Quiz introduction** needs reworking. Very generic and factual but doesn't give a good reason for taking the quiz (other than it being mandatory). Need to explore more engaging quiz forms within the remit of canvas.
- **Studio, Bauhaus and Plotter Styles** they add bullet points on line breaks in the comparison columns, but with code that looks wrong. Also no indents preserved. ![unwanted bullets](<screengrabs/Screenshot 2026-07-29 at 3.32.33 PM.png>) Needs a better way of displaying comparisons other than bulletted lines.
- **Concept-delivery v2** `[evaluate]` — pin concept _extraction_ to the material (counts wobble now); optional course-authored concept list.
- **Multi-model reads** `[evaluate]` — for borderline facticity cases the single critic is a coin-flip; a second _model_ (not seed) would let the union help. Seed-diversity is a proven no-op on the local model.
- **Evaluator blind spot: quality vs presence** `[evaluate]` — a real week-7 "details" Q&A (a muddled, partly-wrong retrieval prompt: spurious array framing; `undefined` vs `NaN` confused) passed all three checks. Two gaps: (1) the pedagogy rubric scores a hook/retrieval/contrast for _existing_, not for being _good_ — a present-but-hollow device still gets 3/3, and the loop-back added more such devices; (2) facticity misses a _near-miss_ — a muddled-but-on-topic answer (right vocabulary, wrong reasoning) reads as plausible. Human review still catches these; the critic is a first-pass filter, not a replacement.
- **Development-adequacy / coherence dimension** `[evaluate]` — the metrics reward structural _presence_ (headings, a retrieval prompt) and _nominal_ coverage, but miss over-compression: week-7 crams functional-abstraction → arrays → array-manipulation → arrays-of-objects → parallax with no transitions and no concrete array example, yet scores pedagogy 14/15 and concept-delivery 3/3. Add a dimension for whether dense content is adequately unpacked, connected, and load-managed (CLT: intrinsic load, segmenting, coherence). The current rubric only faintly sensed it (week-7 SIGNALING 2/3, "the one key idea is diluted").
- **Visual pass of the rendered page** `[evaluate]` — the critic reads block _text_ and never SEES the page, so a structurally broken page (week-7 `--detail full`: empty trailing headings, unreadable near-white text) passed facticity with **0 flags**. Closing the blind spot means rendering the page and evaluating it visually/structurally — a vision model on the HTML, or at minimum structural checks (empty headings, contrast/WCAG, block ordering, coherence). The concrete shape of "judge coherence, not just content."
- **Pedagogy rubric — more dimensions** `[evaluate]` — fold in representation / accessibility / restraint; sharpen the 0–3 anchors; more-extreme calibration variants.
- **Retire the hand-authored synthetic set** `[evaluate]` — the generated set scores cleaner; consider making `synthesize.py` the single source.
- **synthesize.py for GENERATION** `[generate]` — the programmatic generator may make _better_ questions than the model path; explore using it for generation, not only eval. (Look closely, deliberately parked.)
- **Visual / image-bearing question types** `[generate]`.
- **Composable generation — the attention/crowding answer** `[generate/arch]` (user, 2026-07-31) — instruction crowding is a first-order, GROWING concern: the monolithic single-shot page generation overloads a small model's finite attention, and every capability we add (images, concept checklist, contrast, one-idea) taxes the same budget. **Already biting** — the same root cause explains the fading retrieval foldouts, errors clustering later in a long generation, and the `--detail full` runaway. **Direction:** decompose generation into focused sub-tasks, each with a tight instruction set + small context, so crowding can't happen — and the **concept map is the natural decomposition seam** (it is already the plan): one pass for the frame (hook + enduring understanding + recap from prereqs), one focused pass PER concept (its material + KCs + "teach this one thing well"), one for the close (summary + retrieval), then a light assembler. **Two separable axes:** (1) decompose the GENERATION (attacks attention); (2) emit MULTIPLE pages per week — per concept or grouped — which segments pedagogically (CLT), aids navigation, AND is authentic to the real course (the CC101 module is many wiki pages, not one giant page); generating per-page gives both benefits at once. **Validate empirically first (the project's calibration discipline):** an A/B — same week generated monolithically vs concept-map-decomposed — scored by the three existing evaluators (facticity error rate, pedagogy RETRIEVAL, concept-delivery). That measures whether decomposition lifts quality before a big rewrite. **Cost:** a real architecture change (Generator seam runs one conversation per unit today; this needs several sub-conversations + an assembler + a coherence/through-line layer, more model calls but each smaller/faster/higher-quality). This is the scaling answer for staying quality-competitive on LOCAL models as the tool gets richer.
- **Retrieval-foldout finalize gate is PROVISIONAL — revisit/remove** `[generate]` (user, 2026-07-31) — `page.validate_final` now hard-requires a retrieval `details` block so foldouts stop being dropped. But this imposes a PEDAGOGICAL requirement to solve a TECHNICAL problem (local-model attention crowding): retrieval isn't right for every page type (a pure reference/intro page), and a hard gate can be satisfied by a hollow foldout. Keep it for now; it's a stopgap, not an invariant. Remove it (or make it page-type-aware) once composable generation manages attention properly, and if pages become multi-page/typed. Code comment marks it provisional at `page.validate_final`.
- **Images / diagrams on pages — generated diagrams (next rung)** `[generate/visual]` — instructor-supplied inline images shipped (see Shipped). The bigger step: the model AUTHORS a diagram itself (SVG/mermaid) for structural concepts (coordinate systems, data flow), no instructor file needed. Continues the visual/design-forward track.
- **Composable domain bases** `[profiles]` — ship generic bases (`computer-science`, `digital-art`, …) a course selects one or MORE of and refines; assume multi-domain courses.
- **Domain-suggester tool** `[profiles]` — scan the transcripts/ingestables → propose a starter `domain.md`.
- **Multi-source convergence for the concept map** `[analyze/arch]` (user, 2026-07-30) — a real course mixes video + readings + slides, but `analyze` today uses the RICHEST SINGLE source: if any `knowledge.json` exists (video-only — only the transcriber makes it) it builds from those KCs and never reads the week text; else it falls back to the text. So a MIXED week reflects the videos only — readings/slides ingested as text (coursekit ingest produces week text, NO knowledge.json) are invisible. Not biting yet (each of the user's courses is single-medium today), but the architecture should answer for it. Root: the two ingest paths converge at the TEXT layer (both aim at `week-N.md`) but only the transcriber produces the STRUCTURED knowledge layer. **Principled fix (same canonical-form discipline as `bank.json`, one level up):** every ingest adapter emits the SAME per-source knowledge artifact, each tagged with a `kind` (video/reading/slides), and `analyze` aggregates across all of them — medium-agnostic. The seed already exists: `build_concept_map_from_text`/`extract.md` turn text → the concept schema; run that PER-SOURCE (per document/transcript) rather than per-week-text and the existing aggregator unions it. Cheap interim: stop short-circuiting — feed knowledge.json KCs AND the week text to consolidation (but the week text isn't a guaranteed union either — ingest writes `output/week-3.md`, transcriber `output/week 3/week-3.md` — same convergence problem at the text layer). This also finally makes "the week text is the union of all sources" true at both layers.
- **Voice / tone profile** `[profiles]` (user, 2026-07-30) — the generated prose (and especially the enduring understanding, e.g. "Complexity is managed by organizing data into structures that allow a single logic pattern to govern many individual entities") reads more formal/academic than the user teaches. A THIRD composable prose layer beside domain (WHAT) and pedagogy strategy (HOW): a `.vtconfig/voice.md` (tone/register/second-person/idioms/playfulness) prepended to generation + consolidation like `domain_preface`. **Sharp insight:** the authentic voice is ALREADY in the transcripts — the formality is INTRODUCED by cleanup passes (the transcriber's format stage "fixes grammar, removes filler"; page generation writes formal written prose), sanding off the spoken register. So (a) an authored `voice.md`, and (b) a **voice-extractor** (like the domain-suggester) that characterizes the instructor's register from the raw transcripts → a starter `voice.md`, are both viable, and (b) works precisely because the voice pre-exists cleanup. User: "let's look at it sometime." **Blocks the concept-map-parametrized titles below — that idiom IS this profile.**
- **Concept-map-parametrized section titles in the professor's idiom** `[generate/profiles]` (user, 2026-07-31) — PARKED, blocked on the voice/tone profile above. Assessed 2026-07-31: the request is to title each section NOT with the raw concept name but by passing the concept (name/gist/level, from the map) as a PARAMETER to the model to get "an equivalent title in the idiom of the professor." **We have one half, not the other.** Present: the concept map is already loaded into page generation (`load_for_unit`), so the concept is available to parametrize a title. Missing — and it is the defining ingredient: any representation of the professor's titling *idiom* (register, voice). No voice artifact exists; the only "style" in the repo is visual design tokens (themes), which is orthogonal. Without a captured idiom the model would echo the concept name or invent a generic title — exactly what the user said NOT to do — and inferring the idiom ad hoc mid-generation reintroduces the attention crowding that produces the `》`/`>>` heading junk in the first place. **Right sequencing:** build the voice/tone profile as an editable artifact first (the analog of the concept map / `domain.md`), THEN (c) is a clean title step parametrized by (concept, idiom). This is also the deeper fix for the heading-creep symptom — a titling pass fed the concept + idiom, rather than free-authoring headings deep in a crowded generation.
- **Pluggable pedagogic strategies** `[profiles]` — per course/professor; anti-staleness (one fixed style goes stale); today's hook/key-idea/consolidation fix is one _default_ strategy, not the only law.
- **Document the config convention** `[profiles]` — `.yaml` = settings the code reads; `.md` = prose the model reads (`domain.md`, prompt overrides, future pedagogy profile). Put it in `docs/configuration.md`.
- **Course-level evaluator** `[deliver]` — spacing/spaced-retrieval, pacing, sequencing, cross-week coverage. (Spacing is a schedule property, so it belongs here, not on a single page.)
- **Prerequisite gap analysis** `[analyze]` (user, 2026-07-30) — the payoff that makes concept `prerequisites` worth getting right. Principle the user pinned: **prerequisites are a property of the CONCEPT (its intrinsic dependencies), not the COURSE (its coverage)** — deriving them from "what earlier weeks taught" mirrors coverage and makes gap-finding impossible by construction. So the concept map stores coverage-INDEPENDENT prereqs (the consolidation prompt now enforces non-self-referential, true-dependency prereqs); a later cross-week pass matches each concept's prereqs against the actual concept graph across weeks + a small "assumed incoming background" set, and a prereq satisfied by NEITHER is a **content gap** (the course assumes something it never taught and the student doesn't bring). This is the cross-week analysis the `analyze` phase was designed to grow into. Note: prereqs do NOT feed page generation today (only name/gist/key_material/enduring_understanding do), so weak prereqs are latent, not harmful, until this lands. Also fold in `teaches_toward` for sequencing.
- **Front-end / form factor** `[deliver]` (2026-07-30) — the CLI is a prototype; a friendly GUI is the highest-leverage step for reaching beyond early adopters, and eventually a packaged desktop app with Ollama bundled (so no manual model setup). The decisive usability track. Product rationale lives in the offline product doc.
- **Visual / design-forward track** `[deliver/visual]` (2026-07-30) — a coherent direction, not one feature: design-forward, pedagogically-grounded visual output + a visual authoring surface is the product's most authentic differentiation (the pedagogy↔design CLT/UDL layer already exists; the concept map already IS a graph). The front-end and "design for engagement" are the SAME build. Clusters parked items into one thesis: generated diagrams on pages (images shipped; diagrams next); the visual/design-legibility evaluator (a vision model that SEES the page); a concept-map-as-node-graph editor (Novak form, replaces YAML authoring); live page preview + theme gallery; evaluation as a course-health dashboard; embedded interactive sketches (p5.js iframes). Product rationale + a visual-first mockup live offline.
- **Canvas extension / LTI** `[deliver]` — plausibility of surfacing the tool inside Canvas. CLARIFY first: _which_ chatbot — coursekit's own generation surfaced interactively, or a separate project?
- **RAM pre-flight false positive** `[deliver]` (user, 2026-07-31) — `hardware.check_fit` warns "model ~14.7 GB but budget ~9.2 GB (available × 0.7), may fail to load" when loading right after ejecting another model; the model loads fine (available RAM not yet reclaimed; LM Studio evicts-then-loads + macOS swap). Advisory only (prints, never blocks). Fix: when a _different_ model is loaded, add its footprint back to `available` before the budget check (it will be evicted), or add a total-RAM factor (transcriber uses available-0.7 / total-0.35). Low priority — it's a cosmetic false alarm.
- **One-off:** regenerate the one thin page (a Functions week scored low on delivery — under-generated).

### Carried over from the increment history (reconciled 2026-07-30)

Increments 1–10 are complete in code; these are the live remnants, so nothing real is lost. The offline plan file is now history.

- **Non-coding readings → page end-to-end** `[generate]` — Increment 8's acceptance gate: a real readings/PDF course (no transcripts) through `ingest → generate --pages`, confirming a sensible non-coding page. A user model run.
- **Canvas API push** `[deliver]` — Increment 3/6 Phase 3: `POST /api/v1/courses/:id/pages` with the rendered HTML; defaults to dry-run, gated on a running Canvas + token. File emitters stay first-class regardless.
- **Quiz deterministic verifier** `[evaluate]` — Increment 10 steps 4–5: execute/compute decidable questions (loop trace, arithmetic) in a sandbox instead of trusting the LLM. Deliberately deprioritised — the critic's 100% wrong-answer recall weakened the rationale; revisit only if a decidable-slice failure resurfaces.

## Shipped

A running changelog — one line per completed feature, newest first, with its commit(s). The sections above stay forward-looking; deep detail lives in the offline log + git. (Increments 1–9 — GIFT/QTI/CC emitters, `courseconfig`, the quizbot→coursekit rename, the design system, document ingest — predate this changelog; see `architecture.md`'s "Order of operations" and git history.)

- 2026-07-31 · **Equation renders plainly, not as literal source** — a bare `$…=…$` span (an equation the model delimited, no LaTeX command inside) was shipping with its dollar signs intact; a deterministic renderer pass now strips the delimiters, gated on a relation inside a math-only body so prose dollars (`$5 and $10`, a `$5 - $10` range) stay untouched, and running after the LaTeX passes so unresolved `\command` spans are still preserved for MathJax. `7569632`
- 2026-07-31 · **Versioned evaluation run-store** — each `evaluate` snapshots the run immutably to `<course>/evals/<timestamp>/` (review files + `summary.json` with the coursekit commit, model, and counts) and appends `evals/log.jsonl`, so quality is a readable trend, never an overwritten file; the top-level `*-review.md` stay as latest copies. `883e34f`
- 2026-07-31 · **Images on pages** — inline `ImageBlock` + `add_image`: the model places a `ref`/alt slot (never a URL), the instructor supplies the file via supplements, the renderer resolves it or shows a placeholder. `ecb26b3`
- 2026-07-31 · **Targeted fix loop (quiz + page)** — regenerate each flagged item in place + verify; from-review default (`parse_review`), a progress heartbeat, and the emit robustness guard (skip an out-of-sync week rather than KeyError). `024cc32`
- 2026-07-31 · **Canvas whole-course `.imscc` import — verified in real Canvas** (manual acceptance gate; pages + quizzes as week modules; no code commit).
- 2026-07-30 · **Concept map + the `analyze` phase** — per-week concept map (schema, `consolidate`, the `analyze` verb) from `knowledge.json`, with a text-fallback extractor for non-transcriber courses; wired into page generation (an un-skippable teaching checklist) + concept-delivery scoring. `838a12a`, `b755318`
- 2026-07-30 · **Content-relative page length + teaching structure** — task.md sizes the page to the concept count; one-idea-per-paragraph; each concept its own section. `e1ac724`
- 2026-07-29 · **Page-build hardening** — `add_code` `text` alias, columns multi-line code rendering, longer-content handling, finalize-stop dispatch (fixes the `--detail full` runaway). `0766f86`
- 2026-07-29 · **Concept-delivery evaluation** + `evaluate --all` / `--no-review`. `509d4ba`, `31d20ba`
- 2026-07-28 · **Page pedagogy rubric** — evaluate covers pages + pedagogy, critic domain-awareness, and the loop-back prompt fix (course pedagogy 9.25 → 13.5/15). `06ab78b`
- 2026-07-28 · **Page facticity review** + section scoring. `f55677a`
- 2026-07-27–28 · **Quiz evaluator** — cold-read critic, synthetic calibration, multi-read union, scorecards, reads param. `fe87d05`, `775ebe9`, `9f9a224`, `29840e5`, `b54c400`, `a770f99`
- 2026-07-31 · **Retrieval-foldout finalize gate** — `page.validate_final` requires a `details` block so foldouts stop being dropped (marked provisional; see the parking-lot note). `a58ed2c`
- 2026-07-31 · **Flexible quiz question count** — the quiz now reads the week's concept map and makes one group per teaching concept + one for the enduring understanding (variants drawn from each concept's knowledge components), replacing the hardcoded five; the model suggests the count from the map (or from the material when no map). Overrides at two levels: `questions:` on a week's `.vtconfig/concepts/week-N.yaml` (per-week, wins) and `questions:` in `.vtconfig/quiz.yaml` (per-course). Shared `concept_map.load_for_unit` used by both generators; `quiz/context._shape_directive`; task.md generalized. `ad54acc`

## Note

`agent/todo.md` predates this file; its live items should migrate here (into the parking lot or a theme) so there is one forward view, not two.
