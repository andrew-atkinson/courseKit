# CORE-5 design — units, not weeks, everywhere (2026-11-13)

The fifth step of [structure-review.md](structure-review.md): a unit is identified by its own id, so a course that doesn't meet weekly works through every verb, and nothing derives meaning from a `week-N` name.
It is a migration, not a rename: every weekly course keeps working, and its files keep their names.
The user settled every decision in §6 on 2026-11-14.
Facts below were read from `main` at `b070ceb`, from both real courses (read only), and from the transcriber's source; counts are snapshots.

## 1. What exists today

**CORE-2 already gave the course model real units.**
`course.Unit` has an `id`, an `order`, a `label`, an optional `module`, a reserved `calendar`, a `doc`, and its `sources`.
A unit declared in coursekit's overlay with a non-numeric key (`intro:`) is a unit, in declared order, with its own label and module.

**Everything downstream of the model still reaches for the week number.**
868 lines in 60 files of the package mention "week".

| Where | What still keys on the week number |
| --- | --- |
| `discover.Unit` (what a run gets) | `week_slug`, `week_num` (None for a non-week unit), `week_label` — a second unit type beside `course.Unit` |
| `courseconfig.week_key` | parses `"3"` out of `week-3.md`, `Week 3: …`, `week 3`; called from 12 other files |
| concept maps | the path is `concepts/week-<num>.yaml`; `load_for_unit` returns None without a number; the index only finds `week-*.yaml`; `analyze` skips a unit with no number |
| unit docs | the one scan finds `**/week-*.md`; any other unit must declare its `doc` |
| selection | `--week N` / `--weeks A-B` on `analyze`, `generate`, `evaluate`, `fix`; `--week` on four module scripts; a non-numeric `--week` matches the slug only, never the label |
| IR | `week_ref` in `page.json`, `assignment.json`, and overviews; a quiz is owned by its folder name |
| coursekit's overlay | `structure.coursekit.yaml` declares units under `weeks:`; expectations use `scope: week` and `overrides: week:` |
| census | `WeekCensus`, `census.json` `weeks`, a "Week" column; a label is built as `Week {id}` |
| emit | each cartridge item carries a `week_key`; modules group and sort by it; a module's title falls back to `Week N` |
| page supplements | `.vtconfig/pages/week-N.yaml`, matched by `week_key` |
| prompts | 77 lines in 22 prompt files say "week" to the model |

**What a course with no week numbers gets today**, from a scratch course of two declared sessions (`intro`, `loops`, both in module "Day 1"):
units, their order, labels, and modules are right, and generation writes `quizzes/intro/` and `quizzes/loops/`.
But no concept map is ever found or written for either, so pages and the EU question run without one; the census labels them "Week intro" and "Week loops" and reports no concept map even when `concepts/intro.yaml` exists; `--week "Session 1 — Intro"` selects nothing; and the cartridge puts both quizzes in one module named after the course, since neither has a week key (read from `emit/cartridge.py` and `emit/sources/quizzes.py`).

**The real courses are both weekly.**
CC101 declares `weeks: {week 1: …}` in `context.yaml` and an `expect:` block with `scope: week` in its overlay; PH101 declares its units (with sources) under `weeks:` in coursekit's overlay.
Every artifact folder, concept map, and unit doc is named `week-N` or `week-N-<doc>`.

**The transcriber is week-numbered by design.**
`vt_context.scan_filesystem` keeps only folders matching its week pattern, `merge_sources` writes `weeks: {"week N": {title, module, folder, videos}}`, and `vt_format` names a unit's doc after its folder (`week 3` → `week-3.md`).
That is its contract; this side reads it, and changing it is that repo's decision.

## 2. Goals and non-goals

**Goals.**

1. A course with no week numbers works through every verb: `analyze`, `generate` (every kind), `evaluate`, `fix`, `census`, and `emit`.
2. One unit type: a run's unit is the course model's unit, with run fields added, not a second identity.
3. Nothing derives meaning from a `week-N` name; a weekly course's numbers are just its ids.
4. Weekly courses are untouched: every export byte-identical, every file name the same, and every record still current (no brief changes).

**Non-goals.**

- **Changing the transcriber.** coursekit keeps reading `weeks:` in `context.yaml` as units; a successor is agreed with that repo, separately.
- **Renaming files on disk.** `week-3` stays a fine id and folder name for a weekly course; no migration script, no new names for old artifacts.
- **Calendar time** (dates, sessions, durations): `Unit.calendar` stays reserved for CRSE-2/CRSE-5.
- **Module and source-document nodes** (decision 1): they arrive with their first reader, ASMT-19 layer 2 or STRC-1.
- **Grouping a cartridge by declared module.** Today a Canvas module is one unit; keeping that is what keeps the exports identical. Grouping by module is STRC-1.

## 3. The shape

**A unit's on-disk name comes from one function.**
`course.unit_slug(id)` (today's `_run_slug`): `week-3` for a numbered id, the slugified id otherwise.
The artifact folder, the concept map (`concepts/<slug>.yaml`), and the page supplements all use it, so a weekly course's names don't change and a session course gets `concepts/intro.yaml`.
The concept-map index reads `concepts/*.yaml` (not records), owned by the unit whose slug matches.

**The run's unit carries the model's unit.**
`discover.Unit` keeps its run fields (`transcript_path`, `output_dir`, `course_root`, `config`) and takes `id`, `order`, `label`, and `module` from `course.Unit`; `week_slug`, `week_num`, and `week_label` go, their readers moving to `unit.id`, `unit_slug(unit.id)`, and `unit.label`.
`week_key` stays only where a week number is genuinely what's meant: reading the transcriber's `weeks:` keys, and the legacy `--week`/`--weeks` flags.

**Old names survive at the edges, as aliases that are read, never written.**
`--week` beside `--unit`; `week_ref` read when there's no `unit_ref`; `scope: week` read as `scope: unit`; `weeks:` in coursekit's overlay read beside `units:`.
`propose` writes the new names in a new draft; an existing overlay is never rewritten to change a key.

**What the model is shown doesn't change for a weekly course** (decision 4), so no record goes outdated: a prompt's "week" becomes the course's unit noun, which is "week" unless the course says otherwise.

## 4. What it touches, by consumer

| Consumer | Change |
| --- | --- |
| `course.py` | `unit_slug`; concept maps indexed by unit; `review_items(weeks=)` → units |
| `discover.py`, `pipeline.py` | one unit; selection by id or label (`select_units`) |
| `generate/*` | read `unit.id`, `unit.label`; concept map by unit; `analyze` stops skipping |
| `coursestructure.py` | `units:` beside `weeks:` in the overlay; `scope: unit`; `unit_label(id)` from the declared title, never `Week {id}` for a non-numeric id |
| `census.py` | `UnitCensus`, `census.json` `units` (decision 5); the report's column says "Unit" |
| `emit/*` | `CartridgeItem.unit` and the unit's order; a module's title is the unit's label |
| `cli.py` | `--unit` (repeatable) on `analyze`, `generate`, `evaluate`, `fix` |
| prompts | `{unit_noun}` where they say "week" (decision 4) |

## 5. Increments — one branch each, each with a pass criterion

Every step keeps these **goldens** identical to `main`, captured once before step 1:

- **G0, exports.** Every member of every package `emit` writes for copies of both real courses.
- **G1, generation.** Scripted fake-provider runs over a weekly course (analyze, a quiz with the EU question and intro, monolithic and decomposed pages, glossary, overview and recap, an assignment): every artifact file, and every record still current.
- **G2, the session course.** The two-session course from §1, run through every verb with a fake provider; it starts as a list of what's wrong, and each step turns some of it right, pinned by a test.

1. **`CORE-5.1-one-unit` — the run's unit is the model's unit.**
   `discover.Unit` takes `id`, `order`, `label`, `module` from `course.Unit`; `week_slug`, `week_num`, `week_label` go; `unit_slug` names every unit-keyed file; concept maps are found, indexed, and written by unit, and `analyze` stops skipping.
   *Pass:* G0 and G1 identical; on G2, `analyze` writes `concepts/intro.yaml` and `concepts/loops.yaml`, a page and the EU question use them, and the census sees them; no `week_num` left in the package; mutation checks on `unit_slug` and the concept-map lookup.
   **Done 2026-11-14.** A run's `discover.Unit` now carries the model's `id`, `order`, and `label`, and `slug` (its folder's name: `unit_slug(id)`, or a document quiz's own `week-10-<reading>`); `week_slug`, `week_num`, and `week_label` are gone from every reader.
   `course.unit_slug` (today's `_run_slug`, made public) names the concept map and its materials too, so `concept_map_path` and `materials_path` take a unit id; the index reads `concepts/*.yaml`; `analyze` no longer skips a unit with no number; and a model-free overview or recap page is named from the unit's slug, not `week-<num>` (a session's was `week-None-overview`).
   A document quiz keeps its own unit's id ("10") beside its folder name, so it still finds unit 10's concept map, as ASMT-19 layer 1 needs.
   "No `week_num` left" means no reader of a unit's week number; `week_num` as a parameter name survives in `coursestructure`'s week API and two local loops, which CORE-5.3's words replace.
   Found here, not fixed (it would change G1): the overview and recap pages that `generate --pages --function overview|recap` writes are titled "Week 7: Week 7: Objects", the unit's label already saying "Week 7"; the course overviews (`overview/`) aren't. Left for CORE-5.3, which builds every label from the unit.
   G0: all 904 files and package members from copies of both real courses identical to `main`. G1: all 52 files identical (records compared without their time and commit), every record current. 14 mutations, all caught.
2. **`CORE-5.2-select-units` — choosing units by id or label.**
   `--unit` beside `--week`/`--weeks` on the four verbs and the module scripts, through one `select_units`.
   *Pass:* every existing selection test unchanged; on G2, `--unit intro` and `--unit "Session 1 — Intro"` each select one unit, and an unknown one says which units exist.
   **Done 2026-11-14.** One matcher, `pipeline.unit_matches` (today's `_week_matches`, which every selection already went through): a numbered reference matches the unit with that number, and any other matches the unit's id, its name on disk, or its title, ignoring case; it takes a run's unit or the model's.
   `--unit` (repeatable) on `analyze`, `generate`, `evaluate`, and `fix`, and on the four module scripts (`eu`, `intro`, `glossary`, `decompose`, which take `--unit` or `--week`); `--week` goes through the same matcher, so it takes titles too.
   The check is the CLI's, not the library's: `course.check_selection` stops a command whose reference names no unit, listing the course's units, while `run_course` with an unmatched reference still returns nothing, as a test pins.
   A unit counts as existing if it has a doc or owns an artifact, so a document quiz's unit with no text of its own (PH101's `week-2-<reading>` kind) can still be chosen; that quiz is now matched through its unit, so it's chosen by title too.
   The user guides' examples say `--unit`, and the command reference explains it. Every existing test unchanged; G0 and G1 identical; 13 mutations, all caught.
3. **`CORE-5.3-unit-words` — what coursekit writes says unit.**
   The overlay's `units:`, `scope: unit`, and `unit_ref` are read beside their week names and written by `propose` and the generators; the census becomes `UnitCensus` with the unit's own label.
   *Pass:* G0 identical; G1 identical but for `week_ref` → `unit_ref` in the IR and `weeks` → `units` in `census.json`; every old file still reads the same (a test per alias); on G2, the census shows "Session 1 — Intro".
   **Done 2026-11-14.** Each old name is read, never written: the overlay's `units:` or `weeks:` (one or the other; both is an error), an expectation's `scope: unit` or `scope: week` (and `overrides: unit:`/`week:`), and an artifact's `unit_ref` or `week_ref`.
   `propose` writes `units:` and a redraft with `--force` replaces an old `weeks:`, which also holds the faculty's edits and so is refused without it; `propose --expectations` writes `scope: unit`.
   The structure's lookups take a unit id (`unit_label`, `unit_module`, `unit_doc`): a numbered unit's label stays `Week 3: …`, and any other's is its declared title, never `Week intro`; `has_declared_structure` now counts a unit declared with no number. The course model builds every unit through them, numbered or not.
   The census is `UnitCensus` in `census.json` `units`, each with the course model's own label, in the course's order; the report says "Unit" and "units".
   The doubled title found in step 1 is fixed: a model-free overview or recap page is titled by the unit's label alone ("Week 7: Objects").
   Found and fixed here: `tests/test_isolation.py`'s two jobs on threads compared every file byte for byte, a record's `at` time included, so it failed whenever the two runs straddled a second (about 1 run in 15, and the unexplained failure during CORE-4.4); records are now compared without their times.
   G0: all 904 files and members identical. G1: 20 of 52 files differ, every one explained: `week_ref` → `unit_ref` in the IR, the two corrected titles, and each record's fingerprint of what it wrote (a model-free page's brief is the page, so its brief too); every record current, and no brief the model sees changed. Both real courses' `census.md` differ only in the words "units" and "Unit". 17 mutations, all caught.
   After an upgrade, a model-free page or course overview made before this step reads "outdated" (its brief is the page, now with `unit_ref`), as CORE-4 decision 2 intends; neither real course has one with a record.
4. **`CORE-5.4-emit-by-unit` — a cartridge module per unit, in the course's order.**
   *Pass:* G0 identical; on G2, two modules titled by the units' labels, in declared order.
   **Done 2026-11-14.** Each cartridge item takes its unit from the course index (`course.artifact_units`, the one ownership rule), not from a week number parsed out of its folder or `unit_ref`; `CartridgeItem.week_key` is now `unit`.
   Modules follow the course's unit order (`cartridge.unit_rank`: the course's units as it orders them, then a unit only an artifact names, then course scope), and a module's title is the unit's declared title (`CourseStructure.unit_title`), else `Week N` for a numbered unit, else its id; the pages-only cartridge orders its pages the same way.
   A title comes from the structure, `context.yaml` and coursekit's overlay composed, where it used to come from `context.yaml` alone: the same for both real courses (PH101's overlay declares no titles).
   G0: all 904 files and members identical, and both emit logs. G2: the session course's cartridge has a module per session titled "Session 2 — Loops" and "Session 1 — Intro", in the order the overlay declares (reversed on purpose), and an artifact with no unit lands in the course's own module, last. 8 mutations, all caught.
5. **`CORE-5.5-unit-noun` — what the model is shown.**
   *Pass:* G1's records all still current (every brief byte-identical for a weekly course); on G2 with `unit_noun: session`, the briefs say "session" and never "week".
   **Done 2026-11-14.** A course names its unit in coursekit's overlay, `unit_noun: session` (schema-checked; `coursekit set unit_noun session` writes it); `prompts.unit_noun(root)` reads it, "week" when absent.
   The shipped prompts say `{unit_noun}` and `{unit_nouns}` (71 places, all in prompt bodies; the frontmatter isn't shown to the model), and `prompts.load` fills both for every caller, so a course's own prompt override can use them too; the plural is English -s/-es.
   The text coursekit writes around a prompt takes the same noun: the page's "Session context —" line and concept checklist, the component palette, decompose's "Concepts this session", the glossary, EU, and `analyze` material lines, the quiz's shape directive, the assignment's default scope ("this session"; `--scope` now defaults to it), every critic's and fixer's "The session's teaching material", and the model-free overview, recap, and module pages.
   A numbered unit's label still says "Week 3: …" (step 3's rule); `docs/components.md` says "unit" where the palette says the course's noun.
   G1: every record `main` made reads current under this code, and a fresh run's files match `main`'s but for the 12 shipped prompts' own hashes in each record's files read. Every critic, fixer, `analyze`-from-text, default-scope assignment, and quiz and page shape brief for a weekly course, and every shipped prompt as loaded, is byte-identical to `main`'s (56 dumps). G0: all 904 files and members identical, and both emit logs.
   G2: with `unit_noun: session`, every recorded brief (analyze, segment, quiz, EU, intro, monolithic, decomposed, glossary, overview, recap, assignment) and every critic and fixer says "session" and never "week"; a course with transcriber weeks and `unit_noun: block` gets "This block — Objects —" and "Data spans 1 block(s)". 27 mutations, all caught.
   Not changed: the tool descriptions the model is offered (`add_glossary`'s "from this week", `add_pullquote`'s "the week's ONE key idea") are module-level schemas, not part of any brief; giving them the noun means building a run's tools per course.
6. **Docs** — `docs/architecture.md`, `agent/architecture.md`, the diagram page, the user guides' `--unit`, `CLAUDE.md`'s unit rule (its examples of surviving week names), and the roadmap.

## 6. Decisions

1. **Scope: units now; modules and source documents become levels of their own with their first reader. Accepted by the user, 2026-11-14.**
   An artifact belongs to one of four levels, each inside the one above: the course, a module (a group of units), a unit (one teaching block), or a source document (one reading, deck, or transcript inside a unit).
   A whole-unit quiz belongs to a unit, a quiz made from one reading to that reading, a module overview to its module.
   Today coursekit only knows units as things an artifact belongs to: a document quiz is filed under its unit by its folder name (`week-10-<reading>`), and a module is only a name written on each unit.
   Nothing yet needs the other two as levels of their own: ASMT-19 layer 2 (an EU question about one reading) and STRC-1 (modules) will, and each adds its level when it's built, since designing one without a reader is guessing.
   Until then a document quiz keeps its folder name and works as it does today.
2. **The IR writes `unit_ref` and reads `week_ref` too. Accepted by the user, 2026-11-14.**
   Keeping `week_ref` as a permanent on-disk name is the other option; it costs nothing now but leaves "week" in every new file.
   Either way old files read the same; the emitters never see the difference.
3. **Selection: `--unit`, repeatable, matching id or label; no new range flag. Accepted by the user, 2026-11-14.**
   For a weekly course `--unit 3` and `--week 3` select the same unit: today `--week` matches a number, or else the unit's folder name, so `--week intro` already works and only a unit's title (`"Session 1 — Intro"`) isn't matched.
   So the functional change is matching titles, which `--week` could learn as well; `--unit` adds the name, for a course whose units aren't weeks.
   The alternative was keeping only `--week` and teaching it titles; `--unit` was chosen for the name.
   `--week` and `--weeks A-B` keep working, through the same matching (titles included); a range by order (`--units intro..loops`) waits until someone needs it.
4. **The model-visible word: a course's unit noun, defaulting to "week". Accepted by the user, 2026-11-14.**
   Replacing "week" with "unit" in every prompt would change every brief, so every artifact in every course would read outdated (CORE-4 decision 2), and a weekly course's pages would start saying "this unit".
   Leaving the prompts alone means a session course's pages say "this week".
   A noun the course declares (`unit_noun: session` in coursekit's overlay) gives each course its own word and leaves weekly briefs byte-identical.
5. **`census.json` renames `weeks` to `units`. Accepted by the user, 2026-11-14.**
   Only the census report reads it today, so this is the cheapest moment; RICH-6 and the app would read it later.
6. **The transcriber's `weeks:` stays its contract. Accepted by the user, 2026-11-14.**
   Proposing a successor (for example `units:` with an optional `week`) is a conversation with that repo, recorded in its roadmap, not a change from this side.

## 7. Risks, and how each is tested

| Risk | Test |
| --- | --- |
| A weekly course's file names change (a folder, a concept map, a supplement) | G0 and G1, plus `unit_slug("3") == "week-3"` pinned |
| A changed brief makes every artifact outdated | G1's records all read current after each step |
| A reader still parses a week number from a name somewhere | step 1's "no `week_num` left" check, and G2 run through every verb |
| An alias is dropped and an old file reads differently | one test per alias (`--week`, `--weeks`, `week_ref`, `weeks:` in the overlay, `scope: week`) |
| Two units slug to the same folder (`Intro` and `intro`) | `discover`'s existing output-collision guard, extended to every unit-keyed file |
| The transcriber's folders stop matching | coursekit only reads its `weeks:`; its tests are untouched, and G1 includes a transcriber-shaped course |
