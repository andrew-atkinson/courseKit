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

> ✅ **Done** — `coursekit evaluate --all` verified on the real course: all three checks produced useful, specific output in one pass. Regrouping to pick the next focus.

## Themes

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
- **Next:** ✅ done — `coursekit evaluate --all` now reports all three; the deeper rubrics ride one umbrella flag.

### 3. Profiles — work across domains and teaching styles

- **Goal:** the tool adapts to different subjects and different instructors, composably.
- **Status:** the `domain.md` profile exists and now feeds both generators _and_ critics. Everything else is a parking-lot idea.
- **Next:** (parked) composable domain bases + a domain-suggester; pluggable pedagogy strategies.

### 4. Deliver & course-scope — into Canvas, and across weeks

- **Goal:** artifacts land in the LMS; the tool can reason about a whole course, not just a week.
- **Status:** file delivery solid (QTI `.zip`, HTML, CC, whole-course `.imscc`). Course-level reasoning and any API/extension path are unbuilt.
- **Next:** (parked) Canvas API/extension; a course-level evaluator (pacing, spacing, sequencing).

## Parking lot

Captured, deliberately not active. Reviewed at each regroup. `[theme]` tags where it belongs.

- **Concept-delivery v2** `[evaluate]` — pin concept _extraction_ to the material (counts wobble now); optional course-authored concept list.
- **Targeted auto-regeneration** `[evaluate]` — feed a specific review flag back to the model to fix that item (vs the systemic prompt fix already proven).
- **Multi-model reads** `[evaluate]` — for borderline facticity cases the single critic is a coin-flip; a second _model_ (not seed) would let the union help. Seed-diversity is a proven no-op on the local model.
- **Pedagogy rubric — more dimensions** `[evaluate]` — fold in representation / accessibility / restraint; sharpen the 0–3 anchors; more-extreme calibration variants.
- **Retire the hand-authored synthetic set** `[evaluate]` — the generated set scores cleaner; consider making `synthesize.py` the single source.
- **synthesize.py for GENERATION** `[generate]` — the programmatic generator may make _better_ questions than the model path; explore using it for generation, not only eval. (Look closely, deliberately parked.)
- **Visual / image-bearing question types** `[generate]`.
- **Composable domain bases** `[profiles]` — ship generic bases (`computer-science`, `digital-art`, …) a course selects one or MORE of and refines; assume multi-domain courses.
- **Domain-suggester tool** `[profiles]` — scan the transcripts/ingestables → propose a starter `domain.md`.
- **Pluggable pedagogic strategies** `[profiles]` — per course/professor; anti-staleness (one fixed style goes stale); today's hook/key-idea/consolidation fix is one _default_ strategy, not the only law.
- **Document the config convention** `[profiles]` — `.yaml` = settings the code reads; `.md` = prose the model reads (`domain.md`, prompt overrides, future pedagogy profile). Put it in `docs/configuration.md`.
- **Course-level evaluator** `[deliver]` — spacing/spaced-retrieval, pacing, sequencing, cross-week coverage. (Spacing is a schedule property, so it belongs here, not on a single page.)
- **Canvas extension / LTI** `[deliver]` — plausibility of surfacing the tool inside Canvas. CLARIFY first: _which_ chatbot — coursekit's own generation surfaced interactively, or a separate project?
- **One-off:** regenerate the one thin page (a Functions week scored low on delivery — under-generated).

## Note

`agent/todo.md` predates this file; its live items should migrate here (into the parking lot or a theme) so there is one forward view, not two.
