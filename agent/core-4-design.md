# CORE-4 design — artifact records (2026-11-07)

The fourth step of [structure-review.md](structure-review.md): beside each generated artifact, a small record of what it was made from and how, so coursekit can tell when an artifact no longer matches its course.
All five steps are built (2026-11-07 to 2026-11-12); `CORE-4.6` (`analyze` overwriting a hand-edited concept map) is parked. The user settled decisions 1, 4, and 5 on 2026-11-07 and added the atomic writes to step 2; the others stand as recommended.
Facts below were read from `main` at `2a0b346` and from both real courses (read only); counts are snapshots.

## 1. What exists today

**Provenance is scattered, and none of it says what an artifact was made from.**

| What | Where | What it records |
| --- | --- | --- |
| The run's tool calls and last reply | `calls.jsonl`, `reply.txt` in a quiz or page folder | what the model did, not what it was given |
| Finished or not | `finalized` in `bank.json` / `page.json`; a `*.partial.json` while a run is going | status, for those two kinds |
| An evaluation run | `<course>/evals/<ts>/summary.json` + `evals/log.jsonl` (`evalstore.py`) | the coursekit commit, the model, counts — per run, not per artifact |
| The latest review | `quizzes/quiz-review.md`, `pages/page-review.md`, … | overwritten each run; nothing ties a finding to the version it judged |
| Who chose the question order | `quiz.json` `order_from` (ASMT-21) | one decision, for one kind |

No artifact records its inputs, the model that wrote it, or the prompt.
So nothing can notice that `week-7.md` was re-transcribed after the quiz was made, that an intro still describes an order the instructor has since changed, or that `bank.json` was edited by hand and a regenerate would overwrite it.
The export finds a broken pairing only at the last moment: CC101's real week 7 `quiz.json` names groups its `bank.json` no longer has, from an interrupted run, and `emit` skips it.

**Who writes artifacts.**

| Kind | Writer | Atomic? |
| --- | --- | --- |
| quiz | `BankDraft` — `_autosave`, `finalize` (also `quiz.json`, both `.gift`), `set_order` | `bank.json` and `set_order` yes; `finalize`'s `quiz.json` and `.gift` no |
| page | `PageDraft._autosave`; `page/build._write_page` for the model-free overview/recap pages | the draft yes; `_write_page` no |
| assignment | `AssignmentDraft.finalize` | no |
| overview | `overview._render_overview` → `overview/<slug>.json` | no |
| concept map | `concept_map.save_concept_map` → `.vtconfig/concepts/week-N.yaml` (from `analyze`) | no |

**What a generation reads.** Every input reaches the model through a few loaders: the unit's text (read in `pipeline.run_unit`), `courseconfig.load` (`context.yaml`, the tool's `*.yaml`, `domain.md`, `voice.md`), `prompts.load` (built-in or a course override), the concept map and materials loaders, and for pages the style and supplements.
What the model is shown is exactly the messages a generator builds, and every builder is offline and cheap: `QuizGenerator.build_messages(unit, transcript, cfg)`, the EU pass, the intro's `unit_facts`.

**The real courses.** CC101 indexes 8 quizzes, 10 pages, 1 assignment, 8 concept maps, and 13 overview files; PH101, 4 quizzes.
None has a record, so whatever ships must say "made before records" honestly for all of them.

## 2. Goals and non-goals

**Goals.**

1. Every artifact coursekit writes gets a record of how it was made: each step (generate, the EU pass, the intro, a fix, a reorder), the model, the coursekit commit, and what it was made from.
2. Its status is worked out on demand, never stored: current, stale (and why), edited by hand, or unknown.
3. An evaluation is tied to the exact version it judged.
4. Nothing an emitter reads changes: every export stays byte-identical.

**Non-goals.**

- **Acting on staleness.** Nothing regenerates by itself; regenerating is a model run and the instructor's call.
- **History and rollback** (UX-5). A record keeps the steps, not copies of old versions.
- **Watching the folder.** A check happens when a command asks.
- **The census as a pipeline stage** (FLOW-9 Phase 2). It will read these records; this step only makes them.
- **Moving `order_from`.** `quiz.json` keeps it, because finalize reads it there; the record logs the reorder as a step.

## 3. The shape

**A record sits beside its artifact** — `quizzes/week-7/record.json`, `pages/week-7/record.json`, `assignments/<slug>/record.json`, `overview/<slug>.record.json`, `.vtconfig/concepts/week-7.record.json` — and is written by the same code that writes the artifact, right after it.

```json
{
  "record": 1,
  "kind": "quiz",
  "unit": "7",
  "steps": [
    {"step": "generate", "at": "2026-11-07T10:02:11", "by": "model",
     "coursekit": "2a0b346", "model": "gemma-3-27b", "options": {},
     "brief": "sha256:5b1e…",
     "read": {"output/week-7.md": "sha256:3f9a…", ".vtconfig/concepts/week-7.yaml": "sha256:b21c…",
              ".vtconfig/voice.md": "sha256:77d0…", ".vtconfig/quiz.yaml": "sha256:0c44…",
              ".vtconfig/context.yaml": "sha256:91aa…", "coursekit:prompts/quiz/system.md": "sha256:e5a1…"}},
    {"step": "eu", "...": "..."},
    {"step": "intro", "by": "model", "brief": "sha256:a7d2…", "read": {"...": "..."}},
    {"step": "reorder", "by": "instructor", "at": "2026-11-07T11:40:03"}
  ],
  "output": {"bank.json": "sha256:9c4e…", "quiz.json": "sha256:17f0…"},
  "evaluations": [
    {"critic": "facticity", "at": "…", "model": "…", "judged": "sha256:9c4e…",
     "flagged": 2, "reviewed": 32, "review": "quizzes/quiz-review.md"}
  ]
}
```

**Two fingerprints per step, for two jobs.**

- `brief` is the hash of exactly what the model was shown: the messages that step built. It decides the verdict.
  It is precise in both directions: re-transcribing `week-7.md` changes the quiz's brief, but adding week 11 to `context.yaml` does not, and neither does fixing a typo in a question (which changes the intro's input only if it changes a topic title).
- `read` lists every file the step's loaders opened, with its hash. It explains the verdict ("`week-7.md` changed"), and it may over-include, because it never decides anything on its own.

A step the program takes alone (a reorder, a model-free overview page) has no brief; its record says who and when, and a model-free page's check is simply rebuilding it and comparing.
A `fix` step's brief depends on the critic's findings, which can't be recomputed offline, so a fix is provenance only.

**How a check works.** `records.status(artifact)` rebuilds each recorded step's brief from today's files, with the step's own builder and its recorded `options`, and compares:

| Finding | Meaning | Shown as |
| --- | --- | --- |
| every brief matches, and `output` matches the files | made from what's there now | current |
| a brief differs, and a course file in `read` changed | the course's material moved on | **stale** — "`week-7.md` changed since this quiz was made" |
| a brief differs, but only coursekit's own prompts or commit changed | a newer coursekit would brief the model differently | outdated (informational, never stale) |
| `output` doesn't match the files | someone edited the artifact | **edited** — a regenerate would overwrite it |
| an input is itself an artifact whose record is stale | e.g. the concept map is stale, so the quiz built from it is too | upstream stale |
| no record | made before records | unknown |

The flags combine: an artifact can be edited and stale at once.
A check reads files and formats strings — milliseconds per artifact — and an unchanged size and modification time can skip a hash.

**When a record is written.** Only when an artifact is finished or changed by coursekit: finalize, a fix, the EU or intro pass, a reorder, a rebuild.
An in-progress run writes none; "in progress" stays what it is today, a `*.partial.json` beside the artifact.
A fresh generate starts a new record; any later step adds to it.
If coursekit adopts an artifact whose `output` hash doesn't match (it was edited by hand), the new step is preceded by an `edited` step, so the record remembers.

**One module.** `coursekit/records.py` owns the record schema, `write_step`, `add_evaluation`, `status`, and the read recorder: a `ContextVar`-scoped log, like `outcomes.capture`, that the loaders note each file into, so the writer can save what the step read without any generator listing its inputs.
Each generator gains one method, `brief(...)`, that returns the messages it would send — the same function it already calls, factored so the check can call it too.

## 4. The rules that keep it this way

- **A record is written only by the code that writes its artifact**, right after it, through `records.write_step`. Nothing else writes `record.json`.
- **Status is derived, never stored.** A record holds facts about the past; "stale" is always worked out from today's files.
- **One builder per brief.** The check calls the generator's own `brief`, never a second copy of how messages are put together.
- **Records never reach an emitter.** Exports read the IR alone, as before.

## 5. Increments — one branch each, each with a pass criterion

Every step keeps these **goldens** identical to `main`, captured once before step 1:

- **G0, exports.** Every package `emit` writes for copies of both real courses: every byte.
- **G1, generation.** Scripted fake-provider runs (quiz with the EU pass and intro, page monolithic and decompose, assignment, overview, analyze): every artifact file, ignoring only the new `record.json`.

1. **`CORE-4.1-quiz-records` — the pattern, on quizzes.**
   `records.py`, the read recorder in the loaders, `QuizGenerator.brief`, the EU and intro briefs, and records written by finalize, fix, the EU and intro passes, and `set_order`.
   *Pass:* G0 and G1 identical; a scripted run's record lists the unit text, concept map, voice, domain, `quiz.yaml`, and prompts, and is current straight after the run; editing `week-7.md` makes it stale and names the file; adding a unit to `context.yaml` does not; moving the open question makes the intro step stale and nothing else; a hand edit to `bank.json` reads as edited; a changed built-in prompt reads as outdated, not stale; mutation checks on each.
   **Done 2026-11-07.** G0: all 125 export files from copies of both real courses identical to `main`. G1: a scripted run (EU and intro, a document quiz, a reorder, a fix) writes the same 20 files as `main`, plus the two `record.json`; about 30 ms more per run.
   Each step's brief is checked against the messages the fake model actually received, so a rebuild that drifts from the run fails a test, not just a status.
   The EU and intro briefs became `eu.eu_brief` and `intro.intro_brief`, and `targeted.prepare` works out a document quiz's unit and text without writing, so the run and the check share one builder each; a document quiz rebuilds from its document, not from its `source.md` copy.
   A later step on an artifact with no record writes nothing, so a quiz made before records stays unknown rather than "current" on the strength of a reorder.
   Two things mutation checks found: the EU rebuild's whitespace only mattered once the test file ended in a newline, as real files do; and the intro's explanation had listed the unit's text, which it is never shown, because finding the unit noted it — finding the unit is now kept out of the intro's `read`.
   To see it: `python -m coursekit.records PATH` since step 2 (step 4 puts status in the census).
2. **`CORE-4.2-records-everywhere` — pages, assignments, overviews, concept maps, and atomic writes.**
   Their briefs (decompose records one per section, from the cached materials), their writers, and upstream staleness (a quiz whose concept map is stale).
   **Every artifact write becomes atomic (user, 2026-11-07).** §1's table lists the writers that aren't: `finalize`'s `quiz.json` and both `.gift` files, `AssignmentDraft.finalize`, `overview._render_overview`, `concept_map.save_concept_map`, and `page/build._write_page`, plus the rendered HTML they write beside it.
   One helper does it (write a temporary file in the same folder, then `os.replace`), and `settings.write`, `set_order`, the drafts' autosave, and `records.write_step` move onto it, so there is one copy of the rule instead of four.
   A record is written only after its artifact is in place, so it never describes a file that isn't there.
   *Pass:* G0 and G1 identical; the step 1 checks for each kind; re-transcribing a unit makes its concept map stale and its quiz and page upstream stale; for each writer, a write made to fail partway leaves the previous file whole and no temporary file behind; a guard test (like `tests/test_outcomes.py`) fails if code under `coursekit/` writes an artifact, a record, or a setting any other way; mutation checks on the helper and the guard.
   **Done 2026-11-08.** G0: every file inside the 25 export packages from copies of both real courses identical to `main` (a zip's own bytes carry the time it was written, so members are compared). G1: a scripted run of every generator (analyze, a quiz with the EU question and intro, monolithic, decomposed, glossary, overview and recap pages, an assignment, framed course overviews) writes the same 40 files as `main`, plus 11 records, every one current; about 20 ms more per run.
   The guard is wider than designed: every file write under `coursekit/` goes through `atomic.write` or `atomic.replacing` (reviews, the census, eval snapshots, and the export zips too), so the rule needs no list of which files count; appending a log line is the one exception.
   Each writer is made to fail at each of its writes in turn, and every file it touches is then whole: old or new, never half.
   Each kind's brief has one builder the run and the check share: `consolidate.analyze_brief` and `segment.brief` (the map), `decompose.plan` (one step per section), `glossary.passes`, `assignment.build.brief`, `overview.plan`; a model-free page's brief is the page it assembles.
   Upstream staleness follows the step that wrote the file read: a record's steps can say which outputs they wrote (`wrote`), so a page built from the concept map isn't upstream stale when only the map's material split is.
   `analyze`'s per-unit work moved from the CLI into `consolidate.analyze_unit`, so the code that writes the map writes its record.
   An assignment drafted from material a caller passes in (no caller does yet) can't be checked later, so its old record goes and it reads unknown.
   `python -m coursekit.records PATH` lists every record's status (it replaces the quiz-only command).
3. **`CORE-4.3-evaluations` — evaluations tied to versions.**
   `evaluate` adds each artifact's result to its record with the hash it judged; `evalstore`'s snapshots stay as they are.
   *Pass:* after an evaluation the artifact reads as evaluated; a later edit makes that evaluation visibly older than the artifact; the review files are byte-identical to `main`.
   **Done 2026-11-09.** `records.add_evaluation` notes, on the record of each artifact a critic judged, the critic, model, coursekit commit, review file, its result (counts or a score), and `judged`: the hash of the exact bytes the critic read.
   All six critics do it from their one course loop (`evaluate_course*`), which `evaluate` and `generate --review` share, right after the review file is written, so a record never names a review that isn't there.
   A check marks an evaluation current while its judged file is unchanged; a fix or a hand edit makes it "of an earlier version", while a reorder (which leaves `bank.json` alone) doesn't.
   Each critic keeps its latest entry (the history stays in `evals/`); a regenerate starts a fresh record, so its evaluations go with it.
   As with every later step, an artifact with no record gets none from an evaluation, so it stays unknown; a pedagogy or concept-delivery call that failed judged nothing and isn't recorded, while a facticity read that failed counts as an error.
   A single-document quiz's own `generate --review` is recorded the same way (with no review file when nothing is flagged, since it writes none); facticity's counts come from one function, `quiz.evaluate.result`.
   `fix`'s own check (when it isn't given a review to work from) is recorded too, as of the version it read before fixing, so it reads "of an earlier version" once a fix changes the artifact, and current when it found nothing to fix.
   Not recorded: the decompose prototype's `--review`.
   A gap from step 2, found here: a page `fix` rewrote `page.json` without a step, so a page coursekit had fixed read as edited by hand (and step 4 would have refused to regenerate it). `fix --pages` and the decompose prototype's `--fix` now record a `fix` step (`page.record.write_fix`), noting a hand edit found before the fix, as a quiz's `fix` does.
   Golden: all six critics, with a scripted critic, over copies of both real courses and a small course with records, under `main`'s code and this branch's; all 46 review files byte-identical, no file added to either real course, and the two records differ from `main`'s only in `evaluations`.
4. **`CORE-4.4-surfacing` — showing it, and protecting hand edits.**
   The census report gains each artifact's status; `emit` warns on a stale artifact (not on an edited one, which is normal); `generate` refuses to overwrite an edited artifact without `--force`, as `propose` refuses to clobber a draft.
   *Pass:* each shown on copies of both real courses, with all of today's artifacts reading "unknown", never "current"; the refusal is mutation-checked.
   **Done 2026-11-11.** The census IR gains `artifacts`, each one's path, kind, unit, state, edited, and reasons, and `census.md` a Status section: a count of each state, then each stale, outdated, or edited artifact with why; one made before records is only counted.
   `emit` warns from `course.ir_files`, the one place every emitter gets its files, so each command warns once per stale artifact and packages it anyway.
   `generate` checks every target before the model is reached (`records.refuse_edited`, from `run_course`, a document quiz, and assignments) and names every edited one at once; `--force` overrides. A deleted file isn't an edit, since there's nothing to lose, and an artifact with no record regenerates as before.
   A page's folder depends on its function (`page_dir`, which `build_page_unit` now shares), so a glossary or overview page is checked where it's written.
   Not covered: `analyze` re-running over a hand-edited concept map, and the overview script (`python -m coursekit.generate.overview`); neither is `generate`. Parked as `CORE-4.6` (2026-11-12).
   A gap from step 2, found here: the course index read an overview's `<slug>.record.json` as another overview; it's skipped now.
   On copies of both real courses: CC101's 40 artifacts all read unknown. PH101's 4 older quizzes read unknown, and its one quiz made since records reads stale, because the PDF it was made from (`…-ocr.pdf`) is no longer in the course. `emit` warns about that one quiz only. Every member of the 16 export packages is byte-identical to `main`'s.
   21 mutations, all caught.
5. **Docs** — `docs/architecture.md` (what each command reads and writes), `agent/architecture.md`, `docs/architecture-diagram.html` (a new output beside each artifact), `CLAUDE.md`'s rules, and the roadmap's Shipped line.
   **Done 2026-11-12.** `CLAUDE.md` has two new rules (every write through `atomic.py`; whatever writes an artifact writes its record, with one brief builder shared by the run and the check, status never stored, no emitter reading it), and "the faculty decides" now covers a hand edit; `docs/architecture.md` adds the record to "what each command runs" and a paragraph on who writes and reads it; the diagram page gives `record.json` its own node.

## 6. Decisions

1. **The verdict comes from the brief, not from file hashes. Accepted by the user, 2026-11-07.**
   File hashes alone are simpler to explain but wrong in both directions here: `context.yaml` and `quiz.yaml` cover every unit, so editing one unit's entry would mark every artifact stale, while a value that reaches the model from somewhere unrecorded would never make anything stale.
   The brief is exactly what the model saw, so it is complete and precise by construction; the file hashes stay, as the explanation.
   What it costs: each generator's message building is factored into a `brief` method the check can call, and pages carry one brief per section.
2. **A newer coursekit is "outdated", never "stale". Recommended.**
   A changed built-in prompt changes every brief, but the course didn't change; calling every artifact stale after an upgrade would teach people to ignore the word.
3. **Records beside the artifact, written right after it. Recommended.**
   Inside the IR would make the pair truly atomic, but it would put metadata in the file every emitter reads (the waist), and a quiz is two files (`bank.json` and `quiz.json`).
   One course-wide file would have many writers.
   Beside the artifact, a record moves and is deleted with its folder; the cost is that a crash between the two writes reads once as "edited" (§7).
4. **No backfill for existing artifacts, and no baseline command. Accepted by the user, 2026-11-07.**
   Hashing today's files into a record for an artifact made months ago would claim it was made from them, which nobody knows.
   So existing artifacts read "unknown" until regenerated.
   A `baseline` command (the instructor asserting "these are good as they are") was proposed and declined: today's artifacts are tests and experiments, so "unknown" is the honest answer. It can come back if a real course needs it.
5. **`generate` refuses to overwrite a hand-edited artifact without `--force`. Accepted by the user, 2026-11-07; in step 4.**
   Proposers already refuse to clobber a draft the faculty owns; a hand-edited quiz is the same case.
   It is the one behaviour change in CORE-4, so it comes last, after the records have proved themselves.
6. **Evaluations: a summary and the judged hash in the record; the review files stay where they are. Recommended.**
   The reviews are what people read and `fix` parses; the record only needs enough to say which version was judged and how it did.
7. **Scope: quizzes, pages, assignments, overviews, concept maps. Recommended.**
   Not the census (it is always rebuilt from the course), and not the unit text `ingest` writes: its hash in each artifact's `read` already catches a re-transcription.

## 7. Risks, and how each is tested

| Risk | Test |
| --- | --- |
| A brief isn't deterministic (an unordered set, a timestamp), so everything reads stale | Step 1: build every brief twice from the same files and compare; straight after a run, the record reads current |
| A check rebuilds the brief differently from the run (a CLI option it doesn't know) | The step records its `options`; G1 runs pass non-default options and must read current |
| A generator reads an input without going through a loader | Only explanation is lost, never the verdict (the brief still changes); a test lists the files a scripted run opened against the record's `read` |
| A crash between writing the artifact and its record reads as "edited" | Accepted: rare, visible, and harmless (it only asks before a regenerate); each write is atomic (step 2), and a test pins the order (artifact first) |
| A writer added later skips the atomic helper | Step 2's guard test |
| Records slow a run | One hash per input per step, at finalize only; measured on the scripted runs |
| `coursekit` commit is unknown outside a git checkout | Recorded as `unknown`, as `evalstore` already does; "outdated" then rests on the prompt hashes alone |
