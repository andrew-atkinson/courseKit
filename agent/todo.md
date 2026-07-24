# Todos

## feature list dump

Somethings are just ideas and not necessarily to be implemented, this is just a holding place but can be referenced to move the project forward.

### List items

- the quiz instructions should say what videos the questions are from. Ideally it would provide a link to the video, so the student could review it. It also should introduce the quiz better.
  - **Investigated 2026-07-18 — the obvious approach won't work.** The `video_url` in the transcript
    front matter points at `aacontent.b-cdn.net`, the staging copy used to feed the transcriber. The
    Canvas course does not reference that domain at all: students watch videos embedded from
    **Panopto** (`example.hosted.panopto.com`). Linking the CDN URL would send students out of
    Canvas to a parallel copy.
  - **Per-video Panopto links aren't reliably recoverable.** The Panopto GUIDs live in the Canvas
    page embeds, but their titles are course-authored ("Rotations", "Shearing") while the transcripts
    use filename-derived ones ("2 for loops"). Some embeds have `title=""`. Any auto-matching would
    be fuzzy and would silently mislink. Fixing this properly belongs in the **videotranscriber** —
    it already reads a `canvas_manifest`, so that's where a Panopto URL could be captured at source.
  - **Viable alternative: link the quiz to its Canvas week page.** The pages are named predictably —
    `week-3-repetition.html`, `week-10-data-and-visualization.html` — and that slug is exactly what
    quizbot's existing `slugify(week_label)` already produces. Canvas rewrites the placeholder
    `$WIKI_REFERENCE$/pages/week-3-repetition` at import time, so no IDs, GUIDs or hardcoded domains
    are needed, and it degrades to plain text if the page is missing. One link per quiz rather than
    per question, but it lands the student on the page that holds the videos. Needs one Canvas test
    to confirm the placeholder resolves.
  - Splitting this into two items of very different cost:
    - **Name the source video per question** — doable now, `video_title` is in the front matter, no
      linking risk. The wrinkle: quizbot generates per _week_, not per video, so the model would need
      to attribute each concept to a video.
    - **Link the quiz to its Canvas week page** — the `$WIKI_REFERENCE$` approach above.
- could the videotranscriber be adapted to transcribe other teaching materials into a similar format for the chatbot, such as readings (PDFs), slide shows (without video), even external links to other online materials?
- added spaced learning into the quizzes? such as adding a question from a previous week.
  - Note: the bank format already supports this — `bank.json` is per-week, so a "revision" quiz could
    draw groups from several weeks' banks without regenerating anything. `qti.bundle()` already
    combines multiple banks into one package.
- parameterize quiz number of questions and randomize question bank. Different numbers of questions, whether or not there are variations and random. Also, different types of questions lead to different ideas about random/number: probably a faculty member is not going to want a randomised essay question for example.
- if the courseconfig.py needs a canvas manifest, what creates that manifest?
- in prompts/pages/system.md it is assuming that this is only for coding. We need a level of abstraction for different types of content. What if this was a photo or art course? This would be useless. It also seems that both the system and task files are project specific and so should live in the project folder, but should also be strucutred by generated out of the content.
- voice - the current voice is very dry and factual. and borrrrring.
- **Syntax highlighting for code blocks — and the deeper idea behind it** (user, 2026-07-20). The
  user's insight: code highlighting makes *semantic* distinctions (keyword / string / comment /
  number) through color, and that maps to *pedagogic* distinctions (concept / example / caveat).
  Two threads:
  1. **Highlight `code` blocks.** Tokenise with a lexer (Pygments) and emit **inline-styled**
     `<span>`s (Pygments' `noclasses=True` inline formatter → sanitizer-safe; no `<style>` block).
     The token→color map comes from the **theme's palette**, so each identity highlights in its own
     colors (terminal's segment hues are a natural token palette). Guardrail: the property-allowlist
     test already covers it, and the escaping round-trip must still hold through the added spans.
     Pygments would be a new dependency; confirm it's Canvas-safe first.
  2. **The mapping made explicit.** The `terminal` identity already does this at the page level —
     section `role` → segment-chip hue is exactly "token type → color". Worth naming as a design
     principle: color is reserved for *semantic/pedagogic signal*, never decoration (which is also
     taste-skill's anti-slop rule and CLT signaling). The role→color system and code→color system
     should share one palette per theme.

### Generalize quiz generation beyond coding

✅ **CORE DONE 2026-07-24** (branch `quiz-generalization`). The quiz half of "generalize beyond
coding": de-biased `prompts/quiz/task.md` (removed the hard-coded "c5 = code-completion"; subject-
neutral default) and `system.md`; the **domain profile** carries subject specifics (coding →
code-completion where code exists; art → visual analysis), same mechanism as pages. Counts are now
`quiz.yaml` `questions` (default 5) + `variants` (default 4), templated into both prompts; the
position rule generalizes to M. The original hard failure (couldn't complete the coding 5th question
on the photo course) is fixed. Tests in test_context.py + test_pipeline.py; docs in
configuration.md.

**Still deferred (enhancements, not built):**
- **Analysis-suggested question count** — a pass over the week's material proposes how many concepts
  it can fairly assess (instead of a fixed default).
- **Class-size-driven variants** — derive `variants` from student count (more students → more
  variants to reduce overlap) rather than a manual `quiz.yaml` value.

### Page design + summarisation (2026-07-24, from real art-course output — coursekit-test)

Surfaced running pages on real art decks (Still Lives wk6, History Landscape wk7). Confirmed against
the generated `page.json`.

1. **Prior-week review needs a distinct graphic treatment (all 4 themes).** The page already emits a
   `role=review` opener that recaps the previous week (confirmed: wk7 opened "Review: The Constructed
   Image" recapping wk6's still-life themes). A look-back should *read* as a different topic — its own
   graphic quality (a "previously / recap" band), distinct from current-week content. Build on the
   existing heading `role` system in the renderer + each theme. NOTE: the recap is currently
   **emergent** (the model does it from the prompt's "recap earlier weeks" line), not a real
   cross-week mechanism — the generator never sees the prior week. A *reliable* spaced-learning
   feature (deliberately feeding prior-week concepts into the next week's generation) is a separate,
   bigger item.
2. **Variable summary length / detail level.** Introduce a `detail` control with ~3 settings: (1) one
   paragraph of key concepts, (2) today's medium outline, (3) near-complete detail. A generation knob
   — `page.yaml` `detail: brief|medium|full` (or a CLI flag) selecting a different task instruction.
3. **Key-terms / glossary needs clear demarcation (all 4 themes).** The glossary rendered directly
   under the last concept heading ("Landscape and Violence") with no separation, so the terms
   (Picturesque, French Formal Garden, Ha-ha, Sublime, New Topographics) misread as part of that
   section. Give the glossary its own labeled frame ("Key Terms"), visually distinct, regardless of
   where the model places it. Design-system fix.
4. **Extract images for later inclusion.** `python-pptx` gives embedded images via `shape.image.blob`;
   because image + caption + theme share a slide, extract them together (the richer structure-aware
   variant). The renderer already has an instructor-figures path to wire into. **Copyright gate:**
   these are artworks — instructor's own deck = instructor-sourced (within the boundary), but
   auto-embedding into distributed Canvas pages is a deliberate decision. Extract-to-files is safe now;
   embedding is the later step. Ties to "structure-aware PPTX" and the "vision captioning" items above.

### Next Items

- **Document ingest — known limitations / future iterations** (shipped 2026-07-24 as
  `coursekit/ingest/`; supports PDF · docx · odt · pptx incl. speaker notes · txt/md, offline,
  `--ingest [--raw]`). Deferred to later iterations, roughly in value order:
  - **Visual content is dropped.** Images, diagrams, charts, and photos in slides/PDFs are ignored —
    a real gap for image-led courses. A vision-description pass (local vision model, like the
    transcriber's `vt_describe`) would caption them into the week doc. This is the heavy/vision axis.
  - **OCR for scanned PDFs.** A scanned page (image of text) extracts empty. Needs an OCR step
    (offline: tesseract/`ocrmypdf`, an external binary — weigh against the pydantic+stdlib footprint).
  - **Direct Google Slides / Docs import** (parked here 2026-07-24, user's courses are Slides-based):
    export-to-file works today (Download → PDF/PPTX/DOCX → `--ingest`); *live* import is the
    online/OAuth axis, a reversal of the offline-first decision — its own project with an auth +
    copyright surface.
  - **`.doc`** (legacy binary Word) — no clean pure-Python reader; convert to `.docx`/PDF.
  - **Layout/table fidelity.** Multi-column PDFs and tables extract as interleaved linear text; the
    shaping pass mitigates but does not reconstruct structure. Table-aware extraction is a maybe.
  - **PPTX depth.** Chart data, SmartArt, and embedded objects are not read (slide text + notes are).
  - **Structure-aware PPTX** (surfaced 2026-07-24 on real art decks, `coursekit-test/source/`). The
    extractor is flat; the decks carry structure it ignores: a TITLE-layout agenda slide, a small
    per-slide text box repeating the section theme (the grouping — there are no PowerPoint sections),
    a caption placeholder (artist/title/year), the image, and occasional notes. A structure-aware
    mode could use the title slide as the page title, the repeated theme label as a section heading,
    and role the shapes (caption vs section vs notes) → a real outline instead of a flat list with the
    theme word repeated 8×. Somewhat tailored to this author's convention, but consistent enough to
    detect. **Biggest gap for image-led courses:** text extraction yields captions + theme tags but
    not the works themselves — a vision-captioning pass (item above) is what actually makes an art
    course work.

- **Non-video ingestion for the transcriber** (confirmed needed 2026-07-20): ART102/ART103 (photo,
  digital literacy) have Canvas exports but no transcripts. NOTE: coursekit's own `--ingest` now
  covers readings/PDFs/slides directly (2026-07-24), so this transcriber-side work is largely
  superseded for the document case; it remains relevant only if video-specific ingestion is wanted.

- Module Placement
  - Deferred once already. Needs the full-course cartridge format, whose empty `assessment_qti.xml`
    stub is exactly what imported empty twice (see `docs/canvasQuizStructure.md` → "The trap").
    Expect several Canvas test rounds.

### Restructure: quizbot → coursekit (planned, not yet done)

**Why.** The repo name now fights the architecture. `coursekit/` — the shared spine — lives
_inside_ quizbot, which is backwards, and the README has to open its layout section by
explaining that "quizbot is a generator sitting on a shared spine." Generator #2 (a page
generator) has no sane home: it isn't quizbot, and its own repo would recreate the copy-paste
problem that produced `hardware.py` in the first place.

**Target shape — two projects, not one, not three.**

```
coursekit/                     ← what quizbot becomes
  coursekit/                     core: providers · prompts · courseconfig · hardware
  generate/quiz/                 bank.py tools.py context.py  (today's quizbot)
  generate/page/                 next generator
  emit/{qti,gift}/               qti.py gift.py
  discover.py  app.py            input resolution, CLI

videotranscriber/              ← stays its own project
  depends on coursekit for providers/prompts; keeps mlx-whisper to itself
```

Dependency flows one way: `videotranscriber → coursekit`. No cycle.

**Why not merge the transcriber.** It pulls `mlx-whisper` — heavy and Apple-Silicon-specific.
Quizbot's whole runtime is pydantic/dotenv/rich/openai + stdlib. Merging would force a video
stack on a colleague who only wants to generate pages from a syllabus, which is hostile to the
institutional direction. It's also 6,542 working lines doing a genuinely distinct job:
_media → text_, versus _text → artifacts_.

**Why not three repos** (core / ingest / generators): cross-repo version skew is real overhead
for a project with one maintainer. Split core out later only if the dependency shape bites.

**When — the trigger is generator #2, not a date.**

- Do it _before_ starting the page generator. At that point it's a `git mv` plus import fixes
  while there is still only one generator.
- Do _not_ do it mid-feature. The rename should be one clean isolated commit, not entangled
  with new work.
- Spine work (prompts, hardware) is identical either way, so it proceeds in place. ✅ `hardware`
  is done — it now lives in `coursekit/` and is reached via `Provider.check_fit()`. ✅ `prompts`
  is done — `coursekit/prompts.py` + `prompts/quiz/{system,task}.md`, overridable per course at
  `<course>/.vtconfig/prompts/quiz/*.md`. Verified byte-identical against the old inline strings.

✅ **Structural diagram done** — see `agent/architecture.md` (mermaid source, tracked). It turned up
two things: the per-course prompt override is **unreachable from the CLI** (`run_unit` never passes
`project_root`, though `Unit.course_root` holds it), and `config.yaml` — which already names prompts
per course — is read by nobody. Both argue `courseconfig` belongs _below_ `discover.py`.

### Housekeeping

- `docs/` is in `.gitignore`, so `docs/canvasQuizStructure.md` — the Canvas format reference, and the
  most expensive knowledge in this project — is **not in version control**. Nor are the Canvas sample
  exports that were the ground truth for it. Either un-ignore the markdown and samples, or move the
  reference next to `agent/GIFT_format_compact.md`, which is already tracked.
- `agent/agents.md` is a stale plan doc for the output-persistence feature that shipped long ago.
  Delete it or mark it historical.
