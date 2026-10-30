# CORE-2 design — one course model (2026-10-23)

The second step of [structure-review.md](structure-review.md): a `Course` loaded once by the only folder walker, with units as first-class objects.
This is a design for review; nothing here is built yet.
Facts below were read from `main` at `a8825b9` and from both real courses (read only); counts are snapshots.

## 1. What exists today

**Two halves of "the course", each read many ways.**

*Inputs — the units.* `discover.find_units` builds units two different ways: from the declared structure (`_units_from_manifest`) or by globbing `week-*.md` names (`_make_unit`), and the targeted quiz builds a third kind by hand (`targeted.generate_targeted_quiz`).
`CourseStructure` composes `context.yaml` with the overlay and answers per-week questions (`iter_weeks`, `week_label`, `week_module`, `week_doc`, `sources_for`).
A unit's identity is its week number throughout.

*Outputs — the artifacts.* Every consumer finds generated files its own way, and they disagree:

| Consumer | Finds artifacts by | Assigns a unit by |
|---|---|---|
| cartridge — pages | `rglob("page.json")`, any depth | `page.week_ref`, else the folder name |
| cartridge — quizzes, QTI | `glob("**/bank.json")` | the folder name |
| cartridge — assignments | `rglob("assignment.json")` | `week_ref`, else the folder name |
| census | `pages/*/page.json`, `quizzes/*/bank.json`, `assignments/*/…` (one level) | per kind, its own copy of the rules |
| quiz evaluate | `quizzes/*/bank.json` | the folder name |

That disagreement is how the census and the emitter once resolved grading groups differently.

*How widely a unit is read:* `Unit` fields are read ~160 times in the package across ~20 files (`week_slug` ~50, `course_root` ~30, `transcript_path` ~25, `week_label` ~20, `output_dir` ~15).
So CORE-2 must not rename them in one go — that is CORE-5's migration.

*The real courses:* every artifact in both sits at exactly `<kind>/<slug>/<ir>.json` (pages, quizzes, assignments), and the overview pages sit flat in `overview/`.
The cartridge's any-depth search is looser than any real layout needs.

## 2. Goals and non-goals

**Goals.**

1. One loader, `Course.load(path)`, and one folder walker behind it.
2. Units built in exactly one place, with their own identity: `id`, `order`, `label`, optional `module`, optional `calendar`, plus the unit's `doc` and typed `sources`.
3. One artifact index — every generated artifact with its kind, its unit, its slug, and its path — assigned to units by one rule.
4. The census and the cartridge sources read the index (the pair that drifted), and `find_units` and the targeted quiz get their units from the `Course`.

**Non-goals (later steps).**

- Renaming `week_*` everywhere, or new on-disk names — CORE-5.
- Artifact status and provenance (input hashes, staleness) — CORE-4; the index leaves room for them.
- Moving `evaluate`, `fix`, and `analyze` onto the model — after v1 proves itself.
- Calendar dates — the field exists, nothing reads or writes it yet.

## 3. The model

```python
@dataclass(frozen=True)
class Unit:                 # the course's teaching block — structural identity only
    id: str                 # stable key: "3" for a week-numbered course, else the declared slug
    order: int              # position in the sequence (declared order, else numeric)
    label: str              # "Week 3: Exposure" — display only, never parsed
    module: str | None
    calendar: str | None    # reserved (CORE-5 / CRSE-5); always None in v1
    doc: Path | None        # the consolidated text generation reads
    sources: tuple[Source, ...]

@dataclass(frozen=True)
class Artifact:
    kind: Literal["quiz", "page", "assignment", "concept_map", "overview"]
    unit: str | None        # Unit.id, or None for course/module scope
    slug: str               # its folder name (quizzes/<slug>/…)
    path: Path              # the IR file

class Course:
    root: Path; title: str | None
    units: list[Unit]                    # in order
    artifacts: list[Artifact]
    def unit(self, id) -> Unit
    def artifacts_for(self, *, kind=None, unit=None) -> list[Artifact]
    def run_target(self, unit, subdir) -> discover.Unit   # today's generation unit, built in one place
```

Two things are kept deliberately separate.
`Unit` is *what the course is* (structure); today's `discover.Unit` is *one generation run* over a unit (it carries `output_dir`, which depends on whether quizzes or pages are being made).
`Course.run_target` builds the latter from the former, so `discover.Unit` keeps its fields and its ~160 reads keep working; CORE-5 renames them later.

## 4. The rules that make it one model

- **Unit identity.**
  Declared structure first: each declared unit, in declared order, with `id` = its existing key normalised (`"week 3"` → `"3"`), so current courses keep their ids and on-disk names.
  No declared structure: units come from `week-*.md` docs, as today, ordered numerically.
  A unit is never identified by parsing its label.
- **Which unit an artifact belongs to — one function.**
  The IR's own reference wins (`week_ref` on pages and assignments); otherwise the slug's leading unit (`week-3-essay` → `"3"`); otherwise none (course scope).
  Today each consumer has its own copy of this rule.
- **One layout.**
  Artifacts are found at `<root>/{quizzes,pages,assignments}/<slug>/<ir>.json`, concept maps at `.vtconfig/concepts/<id>.yaml`, overviews in `overview/`.
  An emit command given a subfolder or a single file filters the index — it no longer walks the tree itself.
- **Reading an artifact is the consumer's job.**
  The index holds paths, not contents, so building a `Course` stays cheap; the census and emitters load what they need (and an unreadable file is still recorded, as CORE-1.5 does).

## 4a. Built for a GUI that will manage the files and the structure (user, 2026-10-23)

The command line is a stop-gap; a GUI will eventually create, reorder, and regroup units, assign sources, and move artifacts between units.
So nothing the GUI would change may be *inferred* — it has to be stored data a program can write:

- **Unit order is stored, not computed.**
  A declared unit's `order` is its position in the structure overlay's `weeks:` list, which the settings API preserves (YAML keeps mapping order on write).
  Reordering is rewriting that order; a unit's `id` never changes when it moves or is relabelled.
  Numeric sorting is only the fallback for an undeclared course.
- **An artifact's unit is stored, not computed.**
  The rule prefers the IR's own `week_ref` over its folder name, so moving an artifact to another unit is one field change — no folder renames, no broken links.
- **The model is read-only; every edit goes through `coursekit/settings.py`.**
  A GUI edits the structure (add, rename, reorder, regroup units; assign sources) with the same validated, atomic writes as every other setting, then reloads the `Course`.
  One writer, one validation path — the GUI runs on exactly the code the CLI does.
- **Structure-editing operations come later** (a `settings` layer for units: `add_unit`, `move_unit`, `assign_source`, …), when the GUI work starts; v1 only guarantees the data they will need is stored.

## 5. Increments — one branch each, each with a pass criterion

1. **`coursekit/course.py` — the model and its loader**, reading through `CourseStructure` and the existing globs.
   *Done when* `Course.load` on both real courses (read only) yields the same units, in the same order, with the same labels as `find_units`, and an artifact index whose per-unit counts equal the census's today.
2. **The census reads the index.**
   *Done when* `census.json` for both real courses is byte-identical before and after, and its walkers are deleted.
3. **The cartridge sources read the index** (pages, quizzes, assignments; QTI's bank loader too).
   *Done when* the `.imscc` and QTI `.zip` packages each command emits are byte-identical before and after on a fixture course and a copy of a real one — the same golden-file guard SHIP-7 needs — and the `rglob`s are gone.
4. **`find_units` and the targeted quiz get units from the `Course`.**
   *Done when* `_make_unit`/`_units_from_manifest` and the hand-built targeted unit are gone, `discover.Unit` is built only by `Course.run_target`, and the suite is green with no test changes beyond imports.
5. **`architecture.md` refreshed** to the new map (it was last verified 2026-07-31).

Increments 2 and 3 each delete a set of walkers, which is the point: the review's ~15 walkers drop toward one.

**Step 1 — done 2026-10-24** (`coursekit/course.py`, `tests/test_course.py`).
Passed on both real courses (read only): the same units, labels, and docs as `find_units`; per-unit artifact counts identical to the census; the census's units equal the model's units plus `undeclared_units`.
Found on the way, each now a rule in the model:

- **Declared order was being thrown away.**
  `CourseStructure` merged `context.yaml` and the overlay through a `set`, so no stored order could survive; the merge now keeps declared order (overlay first), and `iter_declared` exposes it.
- **Only coursekit's overlay declares an order.**
  `context.yaml`'s listing is the transcriber's scan order (one real course lists every unit but 9), so without an overlay order units sort by number — `declares_order()` tells the two apart.
- **`find_units` orders units by path text,** so `week 10` comes before `week 3`; the model's numeric order is the correct one, and step 4 retires the path order.
- **Artifacts can name units nobody declared** (quizzes from readings added after `propose` last ran); `Course.undeclared_units` lists them — the census already counts them, and the model neither drops nor invents them.

**Step 2 — done 2026-10-25** (the census reads the model).
`census.json` and `census.md` are byte-identical before and after on both real courses, and `census.py` no longer walks the folder.
To get there the model took over two things only the census's own walker did: a declared unit finds its doc in the transcriber's per-unit folder (`output/week N/week-N.md`), and a doc for a unit nobody declared is kept (`undeclared_docs`, counted in `undeclared_units`) so the census still reports it as material with nothing generated.
The census does not count overview pages yet — doing so changes its output, so it is a separate, visible change, not part of a byte-identical step.

## 6. Decisions (all four recommendations accepted, 2026-10-23)

1. **A unit with no number.**
   A declared unit keyed `intro` or `reading-week` gets that key as its `id`, and sorts by declared order.
   *Recommended* — it is what the declared structure already says.
2. **Overview pages as artifacts.**
   Index them now (kind `overview`, unit/module scope) so the census can count them, or leave them out of v1.
   *Recommended:* index them; they are generated output the census currently can't see.
3. **Stricter layout.**
   Emitters stop finding an artifact at an unexpected depth (both real courses would be unaffected).
   *Recommended:* yes — and the index can record any stray IR file it sees, so nothing disappears silently.
4. **Order of increments 2 and 3.**
   The census first (lower risk, no Canvas involved), or the cartridge first (fixes the drift at its source).
   *Recommended:* the census first.

## 7. Risks

- **The cartridge is the Canvas-verified path.**
  Increment 3 changes how its inputs are found, so it is guarded by byte-identical packages, not just tests.
- **The two `Unit` classes.**
  Until CORE-5, `course.Unit` (structure) and `discover.Unit` (a generation run) coexist; the names are close.
  Mitigation: `run_target` is the only bridge, and CORE-5 renames `discover.Unit` once its readers move.
- **`week_ref` vs folder name.**
  Where today's rules differ by kind, one rule will change some edge case.
  Increments 2 and 3's byte-identical checks are where any such change shows up; each one found gets a decision, not a silent pick.
