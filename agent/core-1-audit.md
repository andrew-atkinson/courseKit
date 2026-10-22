# CORE-1 audit — fallbacks, defaults, and what each feature silently depends on

A read-only audit for `CORE-1` (see [structure-review.md](structure-review.md) §3.5 and the roadmap).
Snapshot of `main` at `413a581`, 2026-10-21 — `file:line` references drift as code changes; the labels and the feature table are the durable part.
Method: an AST inventory of every broad exception handler (`except Exception` / bare), every `getattr(x, name, default)`, every function whose docstring promises "never raises" / "best-effort" / "degrade", every config-key read, and every `SystemExit` / library `print()`; then each site read in context.

## What the audit found

The problem is narrower than the review estimated, and sharper.
Most `getattr` defaults are harmless; the damage concentrates in five kinds of silence:

1. **Present-but-broken collapses to absent.**
   Every config loader checks whether a file exists, then returns the same empty value for "missing" and "unreadable or malformed".
   A YAML typo in `quiz.yaml`, `page.yaml`, `style.yaml`, a supplements file, or the structure overlay silently turns off everything that file declared.
2. **A switched-on feature runs without its input.**
   `eu_question: true` has three silent exits; `--function overview` / `recap` ship a near-empty page marked finished when the concept map is missing.
3. **A malformed declared value is coerced to a wrong one.**
   `weight: 20%` in `grading:` silently becomes `0` — wrong Canvas weights, the most consequential finding.
4. **A failed measurement reads as a result.**
   Only the facticity critics record a failed call as `ERROR`; pedagogy, groundedness, and concept delivery turn a failed call into a low score, a smaller denominator, or a different concept list.
5. **A failed step leaves stale output with no notice.**
   `fix` re-renders HTML best-effort and swallows the failure, so `page.json` and its HTML can disagree.

**Already right — the patterns to copy:**

- Facticity critics return an explicit `ERROR` verdict (`generate/quiz/evaluate.py`, `generate/page/evaluate.py`).
- A missing named prompt raises `PromptNotFound`, listing every path tried (`prompts.load`); `prompts.require` refuses a prompt missing `{transcript}`.
- The decomposed page generator refuses to run without a concept map (`decompose.py`), and its passes tally errors instead of hiding them.
- Tool-dispatch errors go back to the model as `ERROR:` strings — steering, by design.

**The refined rule.**
"Absent" covers four different situations, and only the first may default silently:

| Situation | Example | Correct behaviour |
|---|---|---|
| Not configured | no `style.yaml` | default, silently |
| Present but unreadable or malformed | YAML typo in `quiz.yaml` | error naming the file and the parse problem |
| Present but an invalid value | `weight: 20%`, `theme: bauhuas`, a rule with `scope: weekly` | error naming the key, the value, and what's allowed |
| Switched on, input missing | `eu_question: true`, no enduring understanding for the unit | error (or recorded skip) naming the feature and how to supply the input |

## Opt-in features and their silent dependencies

| Feature (how it's switched on) | Needs | Today, when the input is missing or broken | Should be |
|---|---|---|---|
| EU question (`eu_question: true` in `quiz.yaml`) | the unit's concept map with an enduring understanding; a unit number | silent skip if no map, no EU text, or no unit number (targeted quizzes never have one — ASMT-19); `generate_eu_question` swallows every exception, including model-load errors, and its `False` is ignored | error / recorded skip naming the unit and "run `analyze`"; model errors propagate |
| Overview / recap page (`--function overview` / `recap`) | the concept map | writes a page with only the intro paragraph and reports it finished | refuse, like `decompose` does |
| Decomposed teaching page (auto-routed or forced) | the concept map; segmentation materials (optional) | refuses when the map is absent ✅ — but an *unreadable* map gets the same "run `analyze` first" advice; unreadable materials silently fall back to the whole unit | distinguish unreadable from absent; record the materials fallback |
| Tool settings (`quiz.yaml`, `page.yaml`, `evaluate.yaml`) | a parseable file | a parse error silently means "all defaults" | error naming the file |
| Declared structure (`structure.coursekit.yaml`: units, `grading:`, `expect:`) | a parseable file with valid values | a parse error silently discards all of it and inference takes over; `weight: 20%` → `0`; nameless groups and invalid rules silently dropped | error naming the file / key / value |
| Theme (`style.yaml`) | a parseable file; a known theme name | a parse error or an unknown name (`bauhuas`) silently gives the default theme | error listing the available themes |
| Supplements (`.vtconfig/pages/*.yaml`) | a parseable file | a parse error silently drops the instructor's links and embeds | error naming the file |
| Domain / voice profile (`domain.md`, `voice.md`) | a readable file | an unreadable file silently turns the profile off (rare — encoding errors) | error naming the file |
| Pedagogy critic (`evaluate`) | a successful critic call | failed call → every criterion `-1`, shown as `?`, but the total skips them — an all-failed page reads `0/15` | an explicit `ERROR` result, excluded from totals with a count |
| Groundedness critics, pages and quizzes (`evaluate`) | a successful call per block / question | a failed call contributes nothing, so coverage is computed over whatever succeeded | count failed calls; report coverage over the attempted set |
| Concept-delivery critic (`evaluate`) | the unit's concept map as the fixed list | an unreadable map silently switches to concepts the critic picks itself | error, or record the switch in the report |
| `fix` (pages) | a successful HTML re-render | a render failure is swallowed — `page.json` fixed, HTML stale | record it; the run says the HTML is out of date |
| Census | readable artifact files | an unreadable `bank.json` / `page.json` is counted as present with empty contents (so `quiz:eu` goes undetected) | count it as present-but-unreadable |
| Targeted quiz (`generate --source`) | a unit number for the source | the unit is built without one, so every unit-keyed lookup (concept map, EU) silently misses — ASMT-19 | build the unit from the declared structure (CORE-2), and fail loudly meanwhile |

## Every site, labelled

Labels: **ok** (optional, or by design) · **recorded** (degrades, but prints a message — becomes an outcome-report entry in step 2) · **silent-broken** (present-but-broken treated as absent) · **silent-required** (a switched-on feature's input silently missing) · **misleading** (a failure that reads as a result) · **dead** (defensive code for a case that can't happen).

### Broad exception handlers

| Site | Label | Note |
|---|---|---|
| `census.py:128` `_load_json` | silent-broken | unreadable artifact counted as present, empty |
| `cli.py:114` `_review_quizzes` | recorded | review skipped, printed |
| `cli.py:142` `_review_pages` | recorded | review skipped, printed |
| `cli.py:363` `_cmd_analyze` | recorded | segmentation skipped, printed |
| `cli.py:389` `_review_targeted_quiz` | recorded | review skipped, printed |
| `console.py:14` `show` | ok | rendering fallback to plain print |
| `courseconfig.py:104` `CourseConfig.domain` | silent-broken | unreadable `domain.md` → `""` |
| `courseconfig.py:124` `CourseConfig.voice` | silent-broken | unreadable `voice.md` → `""` |
| `courseconfig.py:263` `_read_yaml` | silent-broken | every tool config and the overlay |
| `evalstore.py:26` `coursekit_commit` | ok | `"unknown"` is honest |
| `generate/assignment/build.py:56` `_build` | ok | error string back to the model |
| `generate/dispatch.py:46` `dispatch_one` | ok | error string back to the model |
| `generate/overview.py:127` `frame` | recorded-to-be | model framing failure → default intro; optional, but should be recorded |
| `generate/page/concept_delivery.py:73` `evaluate_page_concepts` | misleading | failed call → "(no concepts parsed)" |
| `generate/page/concept_delivery.py:117` `evaluate_course_concepts` | misleading | unreadable map → critic picks its own concepts |
| `generate/page/concept_map.py:221` `load_for_unit` | silent-required | absent and unreadable both `None`; consumers can't tell |
| `generate/page/decompose.py:134` `_run_pass` | recorded | printed and tallied — a good pattern |
| `generate/page/decompose.py:291` `_render` | recorded | render skipped, printed |
| `generate/page/evaluate.py:79` `_one_read` | ok | explicit `ERROR` verdict |
| `generate/page/fix.py:59` `fix_one_block` | ok | aborts on model error, else gives up on that item |
| `generate/page/fix.py:130` `_rerender` | silent-broken | stale HTML after a fix |
| `generate/page/groundedness.py:107` | misleading | failed block drops out of coverage |
| `generate/page/pedagogy.py:79` | misleading | `-1` scores excluded from the total |
| `generate/page/renderer.py:404` `load_supplements` | silent-broken | links and embeds dropped |
| `generate/page/segment.py:55` `parse_boundaries` | ok | robust parse of a model reply |
| `generate/page/segment.py:124` `load_materials` | silent-broken | corrupt materials → whole-unit fallback |
| `generate/page/style.py:127` `_check_hex` | ok | records a problem |
| `generate/page/style.py:204` `_read_yaml` | silent-broken | default theme |
| `generate/quiz/eu.py:49` `generate_eu_question` | silent-required | swallows everything, model-load errors included |
| `generate/quiz/evaluate.py:100` `_one_read` | ok | explicit `ERROR` verdict |
| `generate/quiz/fix.py:84` `fix_one` | ok | aborts on model error, else gives up on that item |
| `generate/quiz/groundedness.py:98` | misleading | failed question drops out of coverage |
| `generate/quiz/tools.py:39` `show` | ok | rendering fallback |
| `generate/quiz/tools.py:576` `_dispatch_one` | ok | error string back to the model |
| `ingest/propose_expectations.py:32` `_load_cm` | silent-broken | unreadable map → its rules silently not proposed |
| `ingest/propose_model.py:70` `_peek` | recorded-to-be | unreadable file → no content peek; optional, should be recorded |
| `pipeline.py:102` `loop` | ok | classifies model-load vs timeout vs other |

### Silent sites that aren't exception handlers

| Site | Label | Note |
|---|---|---|
| `coursestructure.py` `_parse_grading` | silent-broken | `weight: 20%` → `0.0`; nameless groups dropped |
| `coursestructure.py` `_parse_expect` | silent-broken | rules with an unknown scope or non-integer count dropped |
| `coursestructure.py` `_read_overlay` | silent-broken | via `courseconfig._read_yaml` — the whole overlay |
| `generate/page/style.py` `load_style` | silent-broken | unknown theme name → default theme |
| `generate/quiz/generator.py` `postprocess` | silent-required | `if not eu: return`, and the EU pass's `False` is ignored |
| `generate/quiz/targeted.py` `generate_targeted_quiz` | silent-required | unit built without a unit number (ASMT-19) |
| `generate/overview.py` `build_week_overview` / `build_week_recap` | silent-required | `cm is None` → intro-only page, reported finished |
| `pipeline.py` `run_course` | dead (risky) | `getattr(generator, "artifacts_subdir", "quizzes")` — the protocol requires the attribute, and the default would misfile a new generator's output |
| `courseconfig._read_yaml`, `concept_map.py`, `prompts.py` | dead | "no pyyaml" guards — pyyaml is a declared dependency |

### `getattr` defaults

All ~30 were read; none is a silent-required input.
They fall into three harmless groups: argparse namespaces shared between subcommands (`cli.py`), polymorphic block and variant types whose kinds genuinely differ (`evaluate.py`, `renderer.py`, `gift.py`, `qti.py`), and optional protocol methods (`pipeline.py` — `postprocess`, `auto_finalize`).
A few guard attributes that always exist (`unit.course_root` in `load_for_unit` / `load_materials_for_unit`, `cm.concepts` on a non-`None` map) — **dead** but harmless.
The one risky default is `artifacts_subdir`, above.

## Sizing for step 2 (`core-1-outcomes`)

- `raise SystemExit` outside `cli.py`: ~19 sites in 9 modules (`targeted`, the three `propose*` writers, `overview`, `decompose`, `glossary`, `eu`, `prompts`).
  Several sit in per-module `main()` script entry points, which may stay exits.
- Library `print()`: ~37 sites, concentrated in `decompose.py`, `glossary.py`, `eu.py`, and `overview.py` — many in those same `main()`s.

## The mechanism for configuration — guard both doors (user, 2026-10-22)

The model never writes YAML.
Its output always enters through a validated channel — tool calls checked by pydantic, `propose --model` paths checked against the real file list, `analyze`'s JSON checked by the `ConceptMap` schema — and code serialises it.
So every silent configuration failure above comes through one door: **a person editing a text file, read back without a schema.**

| File | Written by | Read back by |
|---|---|---|
| `structure.coursekit.yaml` (units, `grading:`, `expect:`) | the `propose` commands, then hand-edited | hand-written coercion — the silent cases |
| `.vtconfig/concepts/*.yaml` | `analyze`, then hand-editable | a strict schema whose error `load_for_unit` swallows |
| `quiz.yaml`, `page.yaml`, `evaluate.yaml`, `style.yaml`, supplements | by hand only | bare `dict.get` |
| `context.yaml` | the transcriber | bare `dict.get` |

YAML adds its own traps for hand-editing (`20%` is a string, `no`/`off` read as `false`, `3.10` reads as `3.1`, tabs are an error), but changing format would not fix the missing schema.
The fix guards both doors.

**The read door — schemas and `coursekit check`.**
One pydantic schema per coursekit-owned file (`QuizSettings`, `PageSettings`, `EvaluateSettings`, `StyleSettings`, `Supplements`, `StructureOverlay` with `GradingGroup` / `ExpectationRule`), validated on load — pydantic is already the guard for every IR and the concept map.
Errors name the file, the key path, the value, and what is allowed (`grading.groups[0].weight: '20%' is not a number`); where intent is unambiguous the schema may accept it (`20%` → `20`).
`coursekit check` validates every `.vtconfig` file at once, so a mistake surfaces before a long model run rather than halfway through it.

**The write door — a settings API, so faculty stop editing the files directly.**
Direct editing is a stop-gap until the app exists; the fragile files should be written by code that validates first.
A `coursekit/settings.py` module owns every write to a coursekit-owned file:

- **Operations, not file edits:** `get(course, path)`, `set(course, path, value)`, `unset(course, path)`, `check(course)`, plus keyed list operations for the list-shaped settings (`add` / `remove` a grading group or expectation rule by name).
- **Every write is load → apply → validate the whole file → atomic replace** (the OPS-11 `os.replace` pattern) → return the new value and an outcome.
  An invalid value raises a CORE-1 error and leaves the file byte-identical.
- **One write path:** the `propose` commands write through it, so whatever they draft is guaranteed to pass `check`.
- **Scope:** coursekit's own files only.
  `context.yaml` belongs to the transcriber and stays read-only here (one writer per file).
- **The CLI now:** `coursekit config show | get | set | unset | check`, addressing settings by dotted path — e.g. `coursekit config set quiz.eu_question true`, `coursekit config set grading.groups.Projects.weight 20`.
- **The GUI later:** forms generated from the same schemas (`model_json_schema()` supplies each field's type, allowed values, and description), calling the same functions.
  The settings API is the first concrete piece of the operations layer (`CORE-7`), and `init` (`UX-2`) becomes a thin use of it.
- **Comments:** PyYAML drops comments on rewrite — today `propose --force` discards a faculty member's notes along with their edits.
  Once writes go through the API, anything worth keeping moves into data: field help into the schema's descriptions (what `show` prints and a form displays), proposer rationale into a field beside the value (ties `CORE-6`, authority as data).
- **Hand-editing still works** — the files stay plain text — but it becomes the fallback, with `check` catching mistakes.

**Done when:** every coursekit-owned file has a schema; `check` reports file + key + value + allowed values for each case this audit found (`weight: 20%`, `theme: bauhuas`, `scope: weekly`, `count: two`, a YAML syntax error); `set` refuses an invalid value and leaves the file byte-identical; the `propose` commands' output passes `check`; the CLI covers `show` / `get` / `set` / `unset` / `check`.

## Fix order for step 3 (`core-1-required-inputs`), by harm

1. **Grading values** — `weight: 20%` → `0` and dropped groups ship wrong grade weights to Canvas.
   Fixed by the `StructureOverlay` schema (above).
2. **The EU path** — the three silent exits, including ASMT-19 layer 1.
3. **Overview / recap pages** — refuse without a concept map.
4. **Broken config files** — fixed by the schemas and `coursekit check` (above): one shared "present but unreadable" error in place of `courseconfig._read_yaml`, `style._read_yaml`, `load_supplements`, and the overlay reader; unknown theme names rejected with the list of available themes.
5. **Critic failures** — explicit `ERROR` results for pedagogy, groundedness, and concept delivery, like facticity.
6. **`fix` re-render** and **census unreadable artifacts** — record them.
7. **Unreadable vs absent concept map** — so `decompose` stops advising `analyze` for a corrupt file.
8. **Dead code** — the pyyaml guards and the `artifacts_subdir` default.

Each fix gets the feature-on test: switched on, it produces its artifact or fails loudly — never a no-op.
