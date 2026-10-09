"""Course census (FLOW-9 Phase 1) — a deterministic, offline inventory of a whole course: what
materials are declared, what artifacts have been generated, and where the PRESENCE gaps are.

It answers "has an artifact been generated for X?", never "is X any good?" — quality/adequacy is a
judgment that needs the model (CRSE-6). So every number here is a set-difference, computed from files
on disk, no model. Two gap senses in this phase:

  (1) declared-vs-generated — a declared week (with material) that produced nothing; a declared STRC-2
      grading group that no item is placed in.
  (3) modal-consistency — a week off the course's OWN pattern (most weeks have a quiz; this one doesn't).

The `Census` is a canonical IR (`census.json`); `render_report` is a thin Markdown emitter over it — the
same IR→emitter split as bank.json→gift/qti. The IR also feeds run-to-run diffing and, later, CRSE-6 and
the dashboard (RICH-6).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from coursekit import courseconfig, coursestructure

_ARTIFACT_LABELS = ("page", "quiz", "assignment", "concept map")


class Material(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    title: str


class WeekCensus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    week: str                                   # the bare week number, e.g. "3"
    label: str
    materials: list[Material] = Field(default_factory=list)
    pages: int = 0
    quizzes: int = 0
    assignments: int = 0
    concept_map: bool = False
    actual: dict = Field(default_factory=dict)      # artifact[:subtype] -> count (coarse + subtypes) — Layer B
    gaps: list[str] = Field(default_factory=list)   # human-readable presence gaps for this week

    def has_any_artifact(self) -> bool:
        return bool(self.pages or self.quizzes or self.assignments or self.concept_map)

    def is_real(self) -> bool:
        """A week worth reporting: it has declared material or at least one artifact."""
        return bool(self.materials) or self.has_any_artifact()


class Census(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_title: str | None = None
    weeks: list[WeekCensus] = Field(default_factory=list)
    grading_groups: list[str] = Field(default_factory=list)   # declared group names (STRC-2)
    gaps: list[str] = Field(default_factory=list)             # course-level gaps (grading, etc.)

    @property
    def totals(self) -> dict:
        return {"weeks": sum(1 for w in self.weeks if w.is_real()),
                "pages": sum(w.pages for w in self.weeks),
                "quizzes": sum(w.quizzes for w in self.weeks),
                "assignments": sum(w.assignments for w in self.weeks)}

    @property
    def coverage(self) -> dict:
        """How many of the REAL weeks carry each artifact type — the distribution, over which 'gaps'
        stays silent. Surfaces a sparse type (assignments 1/8) that is neither declared-missing nor off
        the modal norm, so 'no gaps' is never mistaken for 'complete'. `weeks` is the denominator."""
        real = [w for w in self.weeks if w.is_real()]
        return {"weeks": len(real),
                "pages": sum(1 for w in real if w.pages),
                "quizzes": sum(1 for w in real if w.quizzes),
                "assignments": sum(1 for w in real if w.assignments),
                "concept maps": sum(1 for w in real if w.concept_map)}


def _load_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _bump(w: "WeekCensus", artifact: str) -> None:
    w.actual[artifact] = w.actual.get(artifact, 0) + 1


def build_census(course_path) -> Census:
    """Walk the course once and assemble the Census. Inputs come from the declared structure
    (`CourseStructure`); outputs from a light scan of the generated IR files (no rendering)."""
    root = courseconfig.find_root(Path(course_path)) or Path(course_path).expanduser().resolve()
    struct = coursestructure.CourseStructure.load(course_path)

    weeks: dict[str, WeekCensus] = {}
    placed: list[tuple[str, str]] = []   # (kind, slug) per graded item — for grading-group resolution

    def wk(num: str) -> WeekCensus:
        if num not in weeks:
            weeks[num] = WeekCensus(week=num, label=struct.week_label(num))
        return weeks[num]

    # declared inputs
    for num, _entry in struct.iter_weeks():
        w = wk(num)
        for s in struct.sources_for(num):
            w.materials.append(Material(kind=s.kind, title=s.title))

    # generated outputs — a cheap scan of each IR file for its week (no rendering). `actual` also records
    # SUBTYPES (Layer B): a page's `page_type`, and `quiz:eu` when a bank carries an open-response group.
    # The grading `slug` mirrors how the emitter resolves a group: a quiz by its DIR name, assignment by `slug`.
    _PAGE_SUBTYPE = {"glossary": "page:glossary", "week_recap": "page:recap", "week_intro": "page:teaching",
                     "week_overview": "page:overview", "module_overview": "page:overview"}
    for pj in sorted(root.glob("pages/*/page.json")):
        d = _load_json(pj)
        num = courseconfig.week_key(d.get("week_ref") or pj.parent.name)
        if num:
            w = wk(num); w.pages += 1; _bump(w, "page")
            sub = _PAGE_SUBTYPE.get(d.get("page_type"))
            if sub:
                _bump(w, sub)
    for bj in sorted(root.glob("quizzes/*/bank.json")):      # quizzes key off the dir (targeted dirs included)
        num = courseconfig.week_key(bj.parent.name)
        if num:
            w = wk(num); w.quizzes += 1; _bump(w, "quiz")
            groups = _load_json(bj).get("groups") or {}
            if any(isinstance(g, dict) and g.get("question_type") == "open_response" for g in groups.values()):
                _bump(w, "quiz:eu")                          # the EU performance question (ASMT-3)
            placed.append(("quiz", bj.parent.name))
    for aj in sorted(root.glob("assignments/*/assignment.json")):
        d = _load_json(aj)
        num = courseconfig.week_key(d.get("week_ref") or aj.parent.name)
        if num:
            w = wk(num); w.assignments += 1; _bump(w, "assignment")
            placed.append(("assignment", d.get("slug") or aj.parent.name))
    for cm in sorted(root.glob(".vtconfig/concepts/week-*.yaml")):
        num = courseconfig.week_key(cm.stem)
        if num:
            w = wk(num); w.concept_map = True; _bump(w, "concept-map")
    # the consolidated week doc is the SOURCE text generation reads — the key input material. Glob the
    # real layouts: `output/week-N.md` (ingest) and `output/<folder>/week-N.md` (transcriber).
    for md in sorted(root.glob("output/**/week-*.md")):
        num = courseconfig.week_key(md.stem)
        if num:
            w = wk(num)
            if not any(m.kind == "week doc" for m in w.materials):
                w.materials.insert(0, Material(kind="week doc", title=md.name))

    census = Census(course_title=struct.course_title or root.name,   # fall back to the folder name
                    weeks=sorted((w for w in weeks.values()), key=lambda w: _wsort(w.week)))
    _compute_gaps(census, struct, placed)
    return census


def _wsort(num: str):
    return (0, int(num)) if num.isdigit() else (1, num)


def _compute_gaps(census: Census, struct, placed: list[tuple[str, str]]) -> None:
    # A DECLARED expectation (Layer B) supersedes the induced modal sense: when the course says what it
    # SHOULD contain, measure against that; otherwise fall back to the course's own pattern.
    exp = struct.expectations()
    if exp.has_scheme():
        _expectation_gaps(census, struct, exp)
    else:
        _modal_gaps(census)
    _grading_gaps(census, struct, placed)


def _modal_gaps(census: Census) -> None:
    """Phase-1 presence gaps when no expectation is declared: sense 1 (declared-but-nothing-generated)
    + sense 3 (off the course's own modal pattern)."""
    real = [w for w in census.weeks if w.is_real()]
    for w in real:
        if w.materials and not w.has_any_artifact():
            w.gaps.append("has material but nothing generated yet")

    generating = [w for w in real if w.has_any_artifact()]
    n = len(generating)
    have = {"page": [w for w in generating if w.pages], "quiz": [w for w in generating if w.quizzes],
            "assignment": [w for w in generating if w.assignments],
            "concept map": [w for w in generating if w.concept_map]}
    for typ, present in have.items():
        if len(present) * 2 > n:
            present_weeks = {w.week for w in present}
            for w in generating:
                if w.week not in present_weeks:
                    w.gaps.append(f"no {typ} (but {len(present)}/{n} weeks have one)")


def _expectation_gaps(census: Census, struct, exp) -> None:
    """Layer B — declared `expected − actual`, per scope. WEEK rules are checked on every known week
    (incl. a declared-but-empty one — the denominator widens, so it becomes a real gap); MODULE rules are
    satisfied by ≥1 matching artifact in ANY week of the module; COURSE rules over the whole course."""
    for w in census.weeks:
        for art, need in exp.for_week(w.week).items():
            have = w.actual.get(art, 0)
            if have < need:
                w.gaps.append(f"expected {need} {art}, has {have}")

    if exp.module or exp.module_overrides:
        mods: dict = {}
        for w in census.weeks:
            m = struct.week_module(w.week)
            if m:
                mods.setdefault(m, []).append(w)
        for mod, members in mods.items():
            for art, need in exp.for_module(mod).items():
                have = sum(x.actual.get(art, 0) for x in members)
                if have < need:
                    census.gaps.append(f'module "{mod}": expected {need} {art}, has {have}')

    for art, need in exp.course.items():
        have = sum(w.actual.get(art, 0) for w in census.weeks)
        if have < need:
            census.gaps.append(f"course: expected {need} {art}, has {have}")


def _grading_gaps(census: Census, struct, placed: list[tuple[str, str]]) -> None:
    """A declared grading group (STRC-2) that no item is placed in. Resolve each item's group the way
    the emitter does — slug override → kind default — so the gap reflects the real placement."""
    scheme = struct.grading()
    census.grading_groups = [name for name, _ in scheme.group_list()]
    if scheme.has_scheme():
        used = {scheme.group_for(kind, slug=slug) for kind, slug in placed}
        for name in census.grading_groups:
            if name not in used:
                census.gaps.append(f'grading group "{name}" declared but no items are placed in it')


# --------------------------------------------------------------------- report (thin emitter on the IR)

def _cell(n: int) -> str:
    return f"✓ {n}" if n else "—"


def render_report(census: Census) -> str:
    """A human-readable Markdown report over the Census IR: a per-week grid + a gaps list."""
    t = census.totals
    cov = census.coverage
    n = cov["weeks"]
    lines = [f"# Course census — {census.course_title or 'course'}", "",
             f"{t['weeks']} weeks · {t['pages']} pages · {t['quizzes']} quizzes · "
             f"{t['assignments']} assignments", "",
             f"Coverage (weeks with each type): pages {cov['pages']}/{n} · quizzes {cov['quizzes']}/{n} · "
             f"assignments {cov['assignments']}/{n} · concept maps {cov['concept maps']}/{n}", "",
             "| Week | Materials | Pages | Quizzes | Assignments | Concept map |",
             "|------|-----------|-------|---------|-------------|-------------|"]
    for w in census.weeks:
        if not w.is_real():
            continue
        cm = "✓" if w.concept_map else "—"
        lines.append(f"| {w.label} | {len(w.materials) or '—'} | {_cell(w.pages)} | "
                     f"{_cell(w.quizzes)} | {_cell(w.assignments)} | {cm} |")

    gaps = [(w.label, g) for w in census.weeks for g in w.gaps]
    lines += ["", "## Gaps", ""]
    if not gaps and not census.gaps:
        lines.append("No gaps found.")
    else:
        for label, g in gaps:
            lines.append(f"- **{label}** — {g}")
        for g in census.gaps:                            # course-level: grading + module/course expectations
            lines.append(f"- {g}")
    return "\n".join(lines) + "\n"


def write_census(course_path, *, out_dir=None) -> tuple[Census, Path, Path]:
    """Build the census and write `census.json` (IR) + `census.md` (report) at the course root (or
    `out_dir`). Returns (census, json_path, md_path)."""
    root = courseconfig.find_root(Path(course_path)) or Path(course_path).expanduser().resolve()
    base = Path(out_dir) if out_dir else root
    census = build_census(course_path)
    base.mkdir(parents=True, exist_ok=True)
    jp, mp = base / "census.json", base / "census.md"
    jp.write_text(census.model_dump_json(indent=2), encoding="utf-8")
    mp.write_text(render_report(census), encoding="utf-8")
    return census, jp, mp
