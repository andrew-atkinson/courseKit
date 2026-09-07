# coursekit — on-model test plan

A manual acceptance checklist for the things the offline suite can't judge: whether the model-driven
output is actually good, and whether the real Canvas import works.
Organized by the workflow verbs. Tick a box when a test passes; note anything that fails beside it.

**Legend** — 🤖 needs the model · ⚙️ model-free (run anytime) · 🧑 manual/human judgment.
**Fixture** — pick one course you know well, with a concept map already built, and use its path for `$C`.
Keep this file generic (`$C` placeholders, no real-course paths) — real-course specifics stay offline.

---

## 0. Preconditions ⚙️
- [ ] **T0.1** `uv run pytest -q` → all green offline (the program works before you judge its output).
- [ ] **T0.2** Model reachable: provider up, `MODEL_NAME` / endpoint set in `.env`.

## 1. `ingest` — documents → week text
- [ ] **T1.1 🤖** `coursekit ingest "$C"` on a folder-per-week course → one `output/week-N.md` per week, each source under a `## <name>` header. *(Multi-source consolidation, FLOW-2.)*
- [ ] **T1.2 ⚙️** `coursekit ingest "$C" --raw` → same weeks, extraction only, no model call.
- [ ] **T1.3 🤖** A week that is a *folder* of mixed types (pdf + pptx + docx) → consolidates to one week doc, nothing dropped. *(Kind coverage.)*

## 2. `propose` — declare structure
- [ ] **T2.1 ⚙️** `coursekit propose "$C" --dry-run` on a `week-N` course → correct weeks + typed sources, no file written.
- [ ] **T2.2 ⚙️** `coursekit propose "$C"` → writes `.vtconfig/structure.coursekit.yaml`; a re-run refuses to clobber without `--force`; unassigned files are surfaced, not dropped. *(FLOW-7 silent-drop fix.)*
- [ ] **T2.3 🤖** On a *topic-named* tree (no `week-N`): `coursekit propose "$C" --model` (add `--deep` for a content peek) → groups real files into weeks; every path it emits exists (no fabrication); uncertain files left unassigned. *(FLOW-7 Phase 4 guards.)*

## 3. `analyze` — the concept map
- [ ] **T3.1 ⚙️** `coursekit analyze "$C" --dry-run` → lists weeks + knowledge-component counts, no model.
- [ ] **T3.2 🤖** `coursekit analyze "$C" --week 3` → `.vtconfig/concepts/week-3.yaml` with concepts, knowledge components, an enduring understanding, and prerequisites.
- [ ] **T3.3 🧑** Read the map: does the enduring understanding read as a *transferable idea*, and are prereqs true dependencies (not just "what earlier weeks taught")?

## 4. `generate` — quizzes
- [ ] **T4.1 🤖** `coursekit generate "$C" --quizzes --week 3` → a `bank.json` with one group per concept, four variants each. *(Concept-map-driven, flexible count.)*
- [ ] **T4.2 🤖** *(ASMT-1)* Inspect the groups: no group is minted *for* the enduring understanding — it shapes the questions but is not its own MC group.
- [ ] **T4.3 🧑** *(ASMT-2)* After `emit qti`, read the quiz description (in the package or in Canvas): it gives a reason to take it (self-check, per-student variants), not "Auto-generated… Grading…".
- [ ] **T4.4 🤖** The six question types are reachable, and different students would draw different variants (randomization).
- [ ] **T4.5 🤖** *(ASMT-17)* À-la-carte: `coursekit generate --source "$C/.../one-reading.pdf"` → a quiz under `quizzes/<week>-<doc>/`, no whole-course run. Add `--review` to cold-read that one quiz.
- [ ] **T4.6 🤖** *(domain)* On a course with `.vtconfig/domain.md` (e.g. p5.js): questions use the pinned domain (p5.js, not Processing) even if the transcript drifts.
- [ ] **T4.7 🤖** *(EVAL-15 thin source)* Generate a `--source` quiz from a very thin document (a few lines) → later `evaluate --all` should flag low coverage ("mostly the model's knowledge").

## 5. `generate` — pages
- [ ] **T5.1 🤖** `coursekit generate "$C" --pages --week 3` → a teaching page; watch the `[route]` line choose monolithic vs decompose by length.
- [ ] **T5.2 🤖** Force each: `--generator monolithic` and `--generator decompose` → both finalize; decompose gives one clean section per concept.
- [ ] **T5.3 🧑** *(PAGE-1)* `--function glossary --week 3` → open `pages/week-3-glossary/…html`: one clean "Key Terms" box, no "Recap" wrapper, no doubled label.
- [ ] **T5.4 ⚙️** *(PAGE-3, model-free)* `--function recap --week 3` → generates instantly (no model call), skips the review; open `pages/week-3-recap/week-3-recap.html`: intro + the enduring understanding as a pullquote + a "…Recap" box of predict-then-reveal foldouts, one per concept.
- [ ] **T5.5 ⚙️** *(model-free)* `--function overview --week 3` → a "Start Here" page, also instant/model-free.
- [ ] **T5.6 🤖** *(supplements + no invented links)* Add a `references`/`examples`/embed to the week's supplements YAML, regenerate a teaching page → the links appear; the model itself never emitted a URL.
- [ ] **T5.7 🤖** *(retrieval gate)* A teaching page finalizes only with a retrieval `details` foldout; a recap/overview/glossary is exempt.

## 6. `emit` — packaging (model-free)
- [ ] **T6.1 ⚙️** `coursekit emit qti "$C"` → one Canvas quiz `.zip` per week; `--bundle` → one zip.
- [ ] **T6.2 ⚙️** `coursekit emit html "$C"` → re-renders every `page.json` (teaching **and** `-glossary`/`-overview`/`-recap` siblings). *(PAGE-2 discovery reaches all functions.)*
- [ ] **T6.3 ⚙️** `coursekit emit cc "$C"` and `emit course "$C"` → a pages `.imscc` and a whole-course `.imscc` (pages + quizzes in weekly modules).
- [ ] **T6.4 ⚙️** Re-emit twice → byte-identical package (deterministic ids ⇒ re-import updates, not duplicates).
- [ ] **T6.5 🧑** *(the real gate)* Import one `emit course` / `emit qti` package into a **real Canvas** → quizzes import as item banks drawing one variant per concept; pages land as Pages in weekly modules; a recap page's foldouts work.

## 7. `evaluate` — the critics 🤖
- [ ] **T7.1** `coursekit evaluate "$C" --week 3` → facticity cold-read of quizzes + pages → `quiz-review.md`, `page-review.md`.
- [ ] **T7.2** Plant one wrong answer + one false page claim, re-run → both flagged. *(Facticity recall.)*
- [ ] **T7.3** *(PAGE-2)* With glossary/overview/recap siblings present, `evaluate --pages` → the review names the sibling pages, not just the teaching page.
- [ ] **T7.4** *(EVAL-15)* `evaluate "$C" --all` → also writes `page-pedagogy.md`, `page-concepts.md`, `page-groundedness.md`, `quiz-groundedness.md`. In `quiz-groundedness.md` a well-sourced week ≈ high coverage; the thin-source quiz from T4.7 ≈ low coverage.
- [ ] **T7.5 🧑** *(pedagogy)* `page-pedagogy.md` scores 0–3 per dimension with specific coaching notes (not generic), and the notes are true of the page.
- [ ] **T7.6** *(domain-blind)* On a code-heavy page with framework globals (p5.js `width`), with a `domain.md` present → the critic does not false-flag them as undefined.

## 8. `fix` — repair in place 🤖
- [ ] **T8.1** After T7.2's flags: `coursekit fix "$C" --week 3` → the flagged quiz item and page block are regenerated in place; `bank.json` / `page.json` + HTML updated.
- [ ] **T8.2** *(PAGE-2)* `fix --pages` reaches a flagged glossary/overview/recap sibling and re-renders it with the week's supplements.
- [ ] **T8.3** `fix --reaudit` → cold-reads fresh instead of acting on the last review.

## 9. Cross-cutting judgment 🧑
- [ ] **T9.1** *(voice)* Generated prose reads in the course's register (if `voice.md` exists), while stems/answers stay precise.
- [ ] **T9.2** *(evaluator trust)* Spot-check 3–4 critic verdicts by hand — do you agree? *(Earn trust before relying.)*
- [ ] **T9.3** *(end-to-end)* Fresh week: `analyze → generate (quiz + teaching + recap) → evaluate --all → fix → emit course` → a coherent, importable week with no manual repair.

---

*The un-automatable core: **T4.3, T6.5**, and the judgment passes in §7/§9. The rest have offline analogues but are worth confirming against a real model and a real course.*
