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

> **The concept map — a per-week _content_ contract, the analog of course-level `context.yaml`.** Promote "the week's concepts" from something the model re-derives inline (the extraction wobble; the skipped week-7 concepts) to a STRUCTURED, consolidated, instructor-editable artifact both generators AND the evaluator read. **Key finding (2026-07-30):** the raw material already exists — the transcriber's Extract stage writes a `.knowledge.json` beside every video (`concepts` with explanation/why_it_matters, `prerequisites`, `leads_to`, `code_examples`), sitting in `output/week-N/` next to the `week-N.md` coursekit already reads. So this is READ-AND-CONSOLIDATE, not extract-from-scratch. Granularity gap: knowledge.json is fine (week 5 = 38 micro-concepts across 11 videos); the page teaches ~6. The pedagogy literature names both tiers — **knowledge components** (KLI; the fine per-video units) roll up into **learning objectives / teaching concepts** (the coarse ~6), with one **enduring understanding / threshold concept** per week (→ drives the pullquote). Consolidation = "roll KCs up into learning objectives," KCs preserved nested underneath.
>
> **Status (2026-07-30):** v1 BUILT + wired + CLI, suite 615, all offline. (1) `concept_map.py` — three-tier schema (`ConceptMap`→`Concept` nodes, nested `components` KCs, `key_material`, edges), the deterministic `read_week_knowledge` aggregator over the existing `*.knowledge.json`, `.vtconfig/concepts/week-N.yaml` IO. (2) `consolidate.py` + `prompts/page/consolidate.md` — the model pass (KCs → nodes + enduring understanding), JSON-out like the transcriber's extract. (3) Wiring: `context._concept_directive` injects the concepts as an un-skippable teaching checklist + the enduring understanding as the pullquote (generator loads the map best-effort, falls back to inline when absent); `concept_delivery` scores against the fixed list when a map exists (no re-derivation). (4) `coursekit analyze PATH` — its OWN phase between ingest and generate (`ingest → analyze → generate → emit`); reads knowledge.json → consolidates → writes the editable map; `--dry-run` shows KC counts model-free. Confirmed every CC101 week (3–10) has knowledge.json, incl. week 7. **First week-7 regen (2026-07-30):** two issues found + fixed. (a) `.push()`/`.pop()` still skipped — they are `components` under the `arrays` concept, but the teaching checklist only listed concept NAMES, never the components; fixed `context._concept_directive` to surface each concept's `covering: <components>` + a generic "INTRODUCE a method/operation/term the first time, don't only use it later" instruction (no content-specific naming, per the user's generalize rule). (b) Contrast regression — terminal (dark-surface panels) theme rendered the heading-less hook paragraph + standalone pullquote as light ink on the white gap between panels (renderer only panelled heading-led groups); fixed `renderer.render_body` to panel EVERY group on a dark surface. Suite 616. **Next — the user's model run:** the contrast fix is render-only (`emit html` re-renders week-7 from the existing page.json, no model); the push/pop fix needs a `generate --pages --week 7`; then `evaluate --pages --all --week 7` — do the two skipped concepts now land, does concept-delivery score the fixed list.
>
> **Settled:** consolidated granularity; home = `.vtconfig/concepts/week-N.yaml` (auto-seeded, hand-correctable); sequencing **v1 coursekit reads existing knowledge.json (zero transcriber change) → v2 persist the editable artifact → v3 transcriber emits the schema as a 6th stage**; non-transcriber (PDF-ingest) courses get a coursekit model-pass extractor to the same schema. Generalizations from the user: `has_code` → an open-`kind` **faithfully-handled-material** list (`kind` domain-named, `fidelity: verbatim|faithful|illustrative`) — the general form of the no-fabricated-links guardrail, and it aims the facticity critic; `source_videos` → `sources` (video|reading|slides|pdf). **Resolved:** material field named `key_material`; two-tier `concepts` (nodes) ← `components` (KCs) — the concept map's NODES *are* the learning objectives (three tiers, not four: KCs → concept map → enduring understanding), with the enduring understanding kept DISTINCT from and above the key concept (the transferable idea, not the topic). _Done when:_ week-7 regenerated against its concept map develops every listed concept (no skips), and concept-delivery scores against the fixed list, not a re-derivation.
>
> _(Prior focus ✅ done: content-relative page length — thin week-6 concept-delivery 2.2 → 3.0; dense week-7 to 2.6 with two skipped concepts, which THIS focus closes at the root. Before that: page-build runaway fix + add_code alias + columns render.)_

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

- **Studio, Bauhaus and Plotter Styles** they add bullet points on line breaks in the comparison columns, but with code that looks wrong. Also no indents preserved. ![unwanted bullets](<screengrabs/Screenshot 2026-07-29 at 3.32.33 PM.png>) Needs a better way of displaying comparisons other than bulletted lines.
- **Concept-delivery v2** `[evaluate]` — pin concept _extraction_ to the material (counts wobble now); optional course-authored concept list.
- **Targeted auto-regeneration** `[evaluate]` — feed a specific review flag back to the model to fix that item (vs the systemic prompt fix already proven).
- **Multi-model reads** `[evaluate]` — for borderline facticity cases the single critic is a coin-flip; a second _model_ (not seed) would let the union help. Seed-diversity is a proven no-op on the local model.
- **Evaluator blind spot: quality vs presence** `[evaluate]` — a real week-7 "details" Q&A (a muddled, partly-wrong retrieval prompt: spurious array framing; `undefined` vs `NaN` confused) passed all three checks. Two gaps: (1) the pedagogy rubric scores a hook/retrieval/contrast for _existing_, not for being _good_ — a present-but-hollow device still gets 3/3, and the loop-back added more such devices; (2) facticity misses a _near-miss_ — a muddled-but-on-topic answer (right vocabulary, wrong reasoning) reads as plausible. Human review still catches these; the critic is a first-pass filter, not a replacement.
- **Development-adequacy / coherence dimension** `[evaluate]` — the metrics reward structural _presence_ (headings, a retrieval prompt) and _nominal_ coverage, but miss over-compression: week-7 crams functional-abstraction → arrays → array-manipulation → arrays-of-objects → parallax with no transitions and no concrete array example, yet scores pedagogy 14/15 and concept-delivery 3/3. Add a dimension for whether dense content is adequately unpacked, connected, and load-managed (CLT: intrinsic load, segmenting, coherence). The current rubric only faintly sensed it (week-7 SIGNALING 2/3, "the one key idea is diluted").
- **Visual pass of the rendered page** `[evaluate]` — the critic reads block _text_ and never SEES the page, so a structurally broken page (week-7 `--detail full`: empty trailing headings, unreadable near-white text) passed facticity with **0 flags**. Closing the blind spot means rendering the page and evaluating it visually/structurally — a vision model on the HTML, or at minimum structural checks (empty headings, contrast/WCAG, block ordering, coherence). The concrete shape of "judge coherence, not just content."
- **Pedagogy rubric — more dimensions** `[evaluate]` — fold in representation / accessibility / restraint; sharpen the 0–3 anchors; more-extreme calibration variants.
- **Retire the hand-authored synthetic set** `[evaluate]` — the generated set scores cleaner; consider making `synthesize.py` the single source.
- **synthesize.py for GENERATION** `[generate]` — the programmatic generator may make _better_ questions than the model path; explore using it for generation, not only eval. (Look closely, deliberately parked.)
- **Visual / image-bearing question types** `[generate]`.
- **BUG: `--detail full` breaks the page build** `[generate]` — on week-7 the model called `finalize_page` **8×** and rebuilt the whole page repeatedly; its final two passes _split_ the work — one pass added all the content blocks with NO section headings, the next added 5 section headings with NO content — so, since blocks append in insertion order, the page renders as [wall of unstructured content] + [5 empty headings at the end] ("no content in the second half"). Two sub-bugs: the loop does not stop at the first finalize, and headings/content can be emitted in separate passes (insertion-order split). Also seen on this page: near-white theme text (`#e7eef0`) illegible on the white page background (render/contrast bug). CONFIRMED gemma (not gpt-oss) — a gemma × `--detail full` failure, not model-specific. Now the active focus (see Current focus).
- ✅ **FIXED: `add_code` with `text:` drops the code block** `[generate]` — `add_code` now accepts `text` as a lenient alias for `code` (schema + signature updated), so a param slip no longer silently drops a code block. Regression test in test_page_tools.
- ✅ **FIXED: columns collapse multi-line code** `[generate]` — `columns.html.j2` now renders a code-bearing column (any item with a newline) as `<pre>` blocks (monospace, line breaks preserved via nl2br) instead of a bulleted `<li>`; text columns stay bulleted. Regression test in test_page_render.
- **Content-relative page length** `[generate]` — page length is a FIXED `detail` knob (brief/medium/full in `page/context.py`), uniform across every week, default medium; it does not scale with a week's content volume, so a dense week (week-7) gets the same medium treatment as a light one and over-compresses. Make depth adaptive to the material's density (a heuristic on the transcript, or a prompt directive: more distinct concepts ⇒ more room, not a tighter summary). Quick lever today: set the course/week to `detail: full`.
- **Images / diagrams on pages** `[generate]` — pages are text + code only; there is no image block in the page IR, so visual concepts (parallax, coordinate transforms) have no visual. Add an image/diagram block — instructor-supplied first (like embeds, via supplements, no invented URLs), generated diagrams a bigger later step. UDL multiple means of representation. Distinct from the quiz visual-question item above.
- **Composable domain bases** `[profiles]` — ship generic bases (`computer-science`, `digital-art`, …) a course selects one or MORE of and refines; assume multi-domain courses.
- **Domain-suggester tool** `[profiles]` — scan the transcripts/ingestables → propose a starter `domain.md`.
- **Voice / tone profile** `[profiles]` (user, 2026-07-30) — the generated prose (and especially the enduring understanding, e.g. "Complexity is managed by organizing data into structures that allow a single logic pattern to govern many individual entities") reads more formal/academic than the user teaches. A THIRD composable prose layer beside domain (WHAT) and pedagogy strategy (HOW): a `.vtconfig/voice.md` (tone/register/second-person/idioms/playfulness) prepended to generation + consolidation like `domain_preface`. **Sharp insight:** the authentic voice is ALREADY in the transcripts — the formality is INTRODUCED by cleanup passes (the transcriber's format stage "fixes grammar, removes filler"; page generation writes formal written prose), sanding off the spoken register. So (a) an authored `voice.md`, and (b) a **voice-extractor** (like the domain-suggester) that characterizes the instructor's register from the raw transcripts → a starter `voice.md`, are both viable, and (b) works precisely because the voice pre-exists cleanup. User: "let's look at it sometime."
- **One-idea-per-paragraph — DONE as a prompt line (2026-07-30)** `[generate]` — page `task.md` step 3 now says keep each paragraph to one idea; split mechanism from rationale, or two concepts, into separate paragraphs (general prose rule, generalizes — unlike a content-specific nudge). Prompted by a week-7 para fusing the `.sort()` mechanism with the parallax/depth rationale. Relates to the parked coherence dimension; watch for over-fragmentation into many tiny paragraphs.
- **Concept map as a shared tool contract** `[profiles/arch]` (user, 2026-07-28) — promote "the week's concepts" from something coursekit re-derives inline (inconsistently — the extraction wobble) to a STRUCTURED, persistent artifact in `.vtconfig/` (like `context.yaml` / `domain.md`), authored once and consumed by every generator AND the evaluator. It grounds content-relative length far more robustly than a prompt, stabilises concept-delivery (subsumes "Concept-delivery v2" and the domain-suggester family — all are content-analysis → a `.vtconfig` artifact), and enables course-level sequencing/spacing (cross-week prerequisite links). The two tools already meet ONLY through `.vtconfig/` files, never imports — a concept map fits that boundary exactly. Decisions: (1) the SCHEMA/contract — per-week concepts, each with a one-line definition, level, has-code?, and prerequisite links to earlier weeks; (2) WHO writes it — content analysis is upstream (the transcriber's world), but it's a separate repo. Lean: define the schema first, coursekit ships a v1 extractor (instructor-editable, like the domain-suggester), the transcriber can own it later — same "define the seam, migrate later" discipline that created coursekit. This may become the durable v2 of the current content-relative-length focus.
- **Pluggable pedagogic strategies** `[profiles]` — per course/professor; anti-staleness (one fixed style goes stale); today's hook/key-idea/consolidation fix is one _default_ strategy, not the only law.
- **Document the config convention** `[profiles]` — `.yaml` = settings the code reads; `.md` = prose the model reads (`domain.md`, prompt overrides, future pedagogy profile). Put it in `docs/configuration.md`.
- **Course-level evaluator** `[deliver]` — spacing/spaced-retrieval, pacing, sequencing, cross-week coverage. (Spacing is a schedule property, so it belongs here, not on a single page.)
- **Prerequisite gap analysis** `[analyze]` (user, 2026-07-30) — the payoff that makes concept `prerequisites` worth getting right. Principle the user pinned: **prerequisites are a property of the CONCEPT (its intrinsic dependencies), not the COURSE (its coverage)** — deriving them from "what earlier weeks taught" mirrors coverage and makes gap-finding impossible by construction. So the concept map stores coverage-INDEPENDENT prereqs (the consolidation prompt now enforces non-self-referential, true-dependency prereqs); a later cross-week pass matches each concept's prereqs against the actual concept graph across weeks + a small "assumed incoming background" set, and a prereq satisfied by NEITHER is a **content gap** (the course assumes something it never taught and the student doesn't bring). This is the cross-week analysis the `analyze` phase was designed to grow into. Note: prereqs do NOT feed page generation today (only name/gist/key_material/enduring_understanding do), so weak prereqs are latent, not harmful, until this lands. Also fold in `teaches_toward` for sequencing.
- **Canvas extension / LTI** `[deliver]` — plausibility of surfacing the tool inside Canvas. CLARIFY first: _which_ chatbot — coursekit's own generation surfaced interactively, or a separate project?
- **One-off:** regenerate the one thin page (a Functions week scored low on delivery — under-generated).

## Note

`agent/todo.md` predates this file; its live items should migrate here (into the parking lot or a theme) so there is one forward view, not two.
