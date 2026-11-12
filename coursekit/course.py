"""The course model (CORE-2) — the course loaded once, by the only folder walker.

`Course.load(path)` reads the declared structure (`context.yaml` composed with coursekit's overlay) and
indexes every generated artifact. It is read-only: anything that changes the course — a setting, the
structure, an artifact's unit — goes through `coursekit/settings.py` and the course is loaded again.
That is what lets a GUI manage the files later on exactly the code the CLI uses (see
agent/core-2-design.md §4a), so nothing a GUI would change is inferred here:

- a unit's `order` is its position in the declared structure, never computed from its id;
- an artifact's unit is its own `week_ref` when it has one, so moving it is one field, not a rename.

A unit is the course's teaching block — a week is only one cadence. `id` is stable ("3" for a
week-numbered unit, the declared key otherwise); `label` is for display and never parsed.
"""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from coursekit import courseconfig, coursestructure, outcomes
from coursekit.coursestructure import Source
from coursekit.outcomes import CoursekitError

ArtifactKind = Literal["quiz", "page", "assignment", "concept_map", "overview"]

# Where each generated IR lives: <root>/<dir>/<slug>/<file> — the one layout (agent/core-2-design.md §4).
_IR = {"quiz": ("quizzes", "bank.json"), "page": ("pages", "page.json"),
       "assignment": ("assignments", "assignment.json")}


@dataclass(frozen=True)
class Unit:
    id: str
    order: int
    label: str
    module: str | None = None
    calendar: str | None = None          # reserved (CORE-5 / CRSE-5): no reader or writer yet
    doc: Path | None = None              # the consolidated text generation reads, when it exists
    sources: tuple[Source, ...] = ()


@dataclass(frozen=True)
class Artifact:
    kind: ArtifactKind
    unit: str | None                     # Unit.id, or None for course/module scope
    slug: str
    path: Path

    @property
    def record(self) -> tuple[Path, str]:
        """Where its record sits (CORE-4): `record.json` in its folder, or `<stem>.record.json` beside a
        single-file artifact (a concept map, an overview)."""
        from coursekit import records
        return self.path.parent, records.RECORD if self.kind in _IR else records.name_for(self.path)


@dataclass
class Course:
    root: Path
    title: str | None
    units: list[Unit]
    artifacts: list[Artifact]
    strays: list[Path] = field(default_factory=list)       # IR files outside the layout — recorded, not used
    undeclared_docs: dict[str, Path] = field(default_factory=dict)   # unit docs for units nobody declared
    unreadable: list[Path] = field(default_factory=list)   # IR files whose unit field couldn't be read
    duplicate_docs: dict[str, list[Path]] = field(default_factory=dict)   # unit id → every doc found for it

    def unit(self, id: str) -> Unit:
        for u in self.units:
            if u.id == str(id):
                return u
        raise CoursekitError(f"no unit {id!r} in this course (units: {', '.join(u.id for u in self.units)})",
                             code="unit.unknown", details={"unit": str(id)})

    def target_unit(self, id: str) -> Unit:
        """The unit `id`, or — for an id no unit declares (a reading filed under an undeclared unit 5, a
        loose `lecture-notes.md`) — a plain one with no doc, so a run over it still knows its unit."""
        for u in self.units:
            if u.id == str(id):
                return u
        num = courseconfig.week_key(str(id))
        return Unit(id=str(id), order=len(self.units), label=f"Week {num}" if num else str(id))

    def run_target(self, unit: Unit, *, subdir: str = "quizzes", output_root=None):
        """One generation run over `unit` — a `discover.Unit`, built here and only here. Artifacts go to
        `<root>/<subdir>/<slug>` (or `<output_root>/<course>/<slug>`); the slug keeps today's on-disk names."""
        from coursekit import discover
        num = courseconfig.week_key(unit.id)
        slug = _run_slug(unit.id)
        course_slug = discover.slugify(self.title or self.root.name)
        out = Path(output_root) / course_slug / slug if output_root else self.root / subdir / slug
        has_root = (self.root / courseconfig.VTCONFIG_DIR_NAME).is_dir()
        return discover.Unit(transcript_path=unit.doc, week_slug=slug, output_dir=out, course_slug=course_slug,
                             week_label=unit.label, week_num=num, course_title=self.title, module=unit.module,
                             course_root=self.root if has_root else None,
                             config=courseconfig.load(unit.doc or self.root, config_name="quiz.yaml"))

    @property
    def undeclared_units(self) -> list[str]:
        """Unit ids that only artifacts refer to (e.g. a quiz in `quizzes/week-5-essay/` when no unit 5
        is declared or has a doc) — surfaced, never silently dropped or silently invented as units."""
        known = {u.id for u in self.units}
        refs = {a.unit for a in self.artifacts if a.unit} | set(self.undeclared_docs)
        return sorted((u for u in refs if u not in known), key=coursestructure._week_sort)

    def artifacts_for(self, *, kind: str | None = None, unit: str | None = ...) -> list[Artifact]:
        """Artifacts filtered by kind and/or unit (`unit=None` selects course/module-scope ones)."""
        return [a for a in self.artifacts
                if (kind is None or a.kind == kind) and (unit is ... or a.unit == unit)]

    @classmethod
    def load(cls, path) -> "Course":
        start = Path(path).expanduser().resolve()
        root = courseconfig.find_root(start) or start
        struct = coursestructure.CourseStructure.load(start)
        units, undeclared_docs, duplicate_docs = _units(root, struct)
        ids = {u.id for u in units}
        artifacts, unreadable = _artifacts(root, ids)
        strays = _strays(root, {a.path for a in artifacts})
        for p in strays:
            outcomes.warn("course.stray_artifact", f"  {p}: an artifact outside the course layout "
                          f"(<kind>/<slug>/<file>) — not used; move it or delete it.", path=str(p))
        return cls(root=root, title=struct.course_title, units=units, artifacts=artifacts,
                   strays=strays, unreadable=unreadable, undeclared_docs=undeclared_docs,
                   duplicate_docs=duplicate_docs)


def ir_files(path, kind: str) -> list[Path]:
    """The `kind` IR files an emit command given `path` packages: one file, or every indexed artifact
    under a course or any folder in it. Emitters filter the index; they never walk the folder."""
    p = Path(path).expanduser().resolve()
    name = _IR[kind][1]
    if p.is_file():
        return [p] if p.name == name else []
    with outcomes.capture(sink=lambda n: None):            # warn only about the strays this emit skips,
        course = Course.load(p)                            # once each, not once per cartridge source
    for s in course.strays:
        if s.name == name and s.is_relative_to(p):
            outcomes.warn("course.stray_artifact", f"  {s}: outside the course layout (<kind>/<slug>/{name})"
                          f" — not packaged; move it or delete it.", path=str(s))
    found = [a.path for a in course.artifacts_for(kind=kind) if a.path.is_relative_to(p)]
    _warn_stale(found)
    return found


def _warn_stale(paths: list[Path]) -> None:
    """An export of an artifact its course has moved on from says so, and packages it anyway; an edited one
    is normal (instructors edit), and one made before records can't be checked, so neither is mentioned."""
    from coursekit import records
    for path in paths:
        st = records.status(path.parent)
        if st.state == "stale":
            outcomes.warn("artifact.stale", f"  {path.parent.name}: stale — {'; '.join(st.reasons)}. Packaged as it "
                          f"is; regenerate it to bring it up to date.", path=str(path))


def review_items(path, kind: str, weeks=None) -> list[tuple]:
    """What evaluate and fix read for `kind` ("quiz" or "page"): (label, IR file, material, run), where
    run is the `discover.Unit` it belongs to. Each unit the path selects (as `find_units` does, narrowed
    by `weeks`) brings the artifacts the index owns to it, its own folder first, read against its doc;
    a quiz in any other folder is a targeted quiz, read against its own `source.md` (none: skipped).
    Targeted quizzes of units the path does not select come too (run None): they carry their own
    material, so they need no unit doc. Reviews filter the index; they never walk the folder."""
    from coursekit import discover
    from coursekit.pipeline import _week_matches
    p = Path(path).expanduser().resolve()
    with outcomes.capture(sink=lambda n: None):            # strays are the emitters' to warn about
        course = Course.load(p if p.is_dir() else p.parent)
    runs = discover.find_units(p, subdir=_IR[kind][0])
    if weeks:
        runs = [r for r in runs if any(_week_matches(w, r) for w in weeks)]
    ids = {_run_slug(u.id): u.id for u in course.units}
    out, seen = [], set()
    for run in runs:
        uid = ids.get(run.week_slug, run.week_num or run.week_slug)
        for a in sorted(course.artifacts_for(kind=kind, unit=uid), key=lambda a: (a.slug != run.week_slug, a.slug)):
            source = a.path.parent / "source.md"
            material = run.transcript_path if kind == "page" or a.slug == run.week_slug else (
                source if source.exists() else None)
            if material is not None:
                out.append((a.slug, a.path, material, run))
                seen.add(a.path)
    if kind == "quiz":
        want = {courseconfig.week_key(w) for w in weeks} if weeks else None
        for a in course.artifacts_for(kind="quiz"):
            source = a.path.parent / "source.md"
            if a.path not in seen and source.exists() and (want is None or a.unit in want):
                out.append((a.slug, a.path, source, None))
    return out


def _run_slug(unit_id: str) -> str:
    """The folder a unit's artifacts live in: `week-3` for a numbered unit, else its slugified id."""
    from coursekit import discover
    num = courseconfig.week_key(unit_id)
    return f"week-{num}" if num else discover.slugify(unit_id)


# --------------------------------------------------------------- units
def _units(root: Path, struct) -> tuple[list[Unit], dict[str, Path], dict[str, list[Path]]]:
    """Every unit, in order. With a declared structure (units naming a `doc`/`sources`) it is
    authoritative, as discovery has always treated it; otherwise unit docs found on disk (`week-*.md`)
    join the declared ones. ORDER is stored data once coursekit's overlay declares units (the file a
    GUI reorders); until then nothing chose an order, so units sort by number, as they always have."""
    units: list[Unit] = []
    for key, entry in struct.iter_declared():
        num = courseconfig.week_key(key)
        uid = num or key
        if num:
            label, module = struct.week_label(num), struct.week_module(num)
            doc, sources = struct.week_doc(num), struct.sources_for(num)
        else:                                              # a unit with no number: its key is its id
            label, module = entry.get("title") or key, entry.get("module")
            doc = Path(str(entry["doc"])) if entry.get("doc") else None
            doc = (root / doc) if doc is not None and not doc.is_absolute() else doc
            sources = tuple(s for s in (coursestructure._as_source(r) for r in entry.get("sources") or [])
                            if s is not None)
        units.append(Unit(id=uid, order=len(units), label=label, module=module,
                          doc=doc.resolve() if doc is not None and doc.is_file() else None,
                          sources=tuple(sources)))
    # The one scan for unit docs: `output/week-N.md` (ingest) and `output/<folder>/week-N.md` (transcriber).
    base = root / "output" if (root / "output").is_dir() else root
    found: dict[str, Path] = {}
    dupes: dict[str, list[Path]] = {}                      # two docs for one unit: kept, never silently dropped
    for p in sorted(base.glob("**/week-*.md")):
        uid, rp = courseconfig.week_key(p.stem) or p.stem, p.resolve()
        if found.setdefault(uid, rp) != rp:
            dupes.setdefault(uid, [found[uid]]).append(rp)
    for i, u in enumerate(units):                          # a declared unit without its own doc gets the found one
        if u.doc is None and u.id in found:
            units[i] = replace(u, doc=found[u.id])
    known = {u.id for u in units}
    if struct.has_declared_structure():                    # authoritative: other docs are reported, not units
        undeclared = {uid: p for uid, p in found.items() if uid not in known}
        return (units if struct.declares_order() else _numbered(units)), undeclared, dupes
    extra = sorted((uid for uid in found if uid not in known), key=coursestructure._week_sort)
    for uid in extra:
        num = courseconfig.week_key(uid)
        units.append(Unit(id=uid, order=len(units), label=struct.week_label(num) if num else uid,
                          module=struct.week_module(num) if num else None, doc=found[uid]))
    return (units if struct.declares_order() else _numbered(units)), {}, dupes


def _numbered(units: list[Unit]) -> list[Unit]:
    """Units sorted by their number (non-numeric ids after, in their existing order), `order` renumbered."""
    ranked = sorted(units, key=lambda u: coursestructure._week_sort(u.id))
    return [Unit(**{**u.__dict__, "order": i}) for i, u in enumerate(ranked)]


# --------------------------------------------------------------- artifacts
def owner(ref, slug: str, ids: set[str]) -> str | None:
    """THE rule for which unit an artifact belongs to: its own reference (`week_ref`) first, then its
    folder name's leading unit (`week-3-essay` → "3"); a declared non-numeric unit id matches itself.
    None means course or module scope."""
    for candidate in (ref, slug):
        if not candidate:
            continue
        c = str(candidate)
        if c in ids:
            return c
        num = courseconfig.week_key(c)
        if num:
            return num
    return None


def _ref(path: Path, unreadable: list[Path]):
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("week_ref")
    except (OSError, ValueError, AttributeError):
        unreadable.append(path)
        return None


def _artifacts(root: Path, ids: set[str]) -> tuple[list[Artifact], list[Path]]:
    out: list[Artifact] = []
    unreadable: list[Path] = []
    for kind, (folder, name) in _IR.items():
        for p in sorted(root.glob(f"{folder}/*/{name}")):
            ref = _ref(p, unreadable) if kind != "quiz" else None   # a bank is owned by its folder
            out.append(Artifact(kind=kind, unit=owner(ref, p.parent.name, ids), slug=p.parent.name, path=p))
    for p in sorted(root.glob(".vtconfig/concepts/week-*.yaml")):
        out.append(Artifact(kind="concept_map", unit=owner(None, p.stem, ids), slug=p.stem, path=p))
    for p in sorted(root.glob("overview/*.json")):
        if p.name.endswith(".record.json"):                 # an overview's record, beside it — not an overview
            continue
        out.append(Artifact(kind="overview", unit=owner(_ref(p, unreadable), p.stem, ids), slug=p.stem, path=p))
    return out, unreadable


def _strays(root: Path, indexed: set[Path]) -> list[Path]:
    """Generated IR files anywhere else under the course (an unexpected depth or folder)."""
    names = {name for _, name in _IR.values()}
    return sorted(p for name in names for p in root.rglob(name)
                  if p not in indexed and not any(part.startswith(".") for part in p.relative_to(root).parts))
