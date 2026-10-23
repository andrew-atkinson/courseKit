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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from coursekit import courseconfig, coursestructure, outcomes

_ARTIFACT_LABELS = ("page", "quiz", "assignment", "concept map")


class Material(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    title: str


class Shortfall(BaseModel):
    """One unmet expectation: the scope `has` fewer of an artifact than it `expects`."""
    model_config = ConfigDict(extra="forbid")
    has: int
    expects: int


def _shortfalls(actual: dict, expected: dict) -> dict:
    return {a: Shortfall(has=actual.get(a, 0), expects=n)
            for a, n in expected.items() if actual.get(a, 0) < n}


class WeekCensus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    week: str                                   # the bare week number, e.g. "3"
    label: str
    materials: list[Material] = Field(default_factory=list)
    pages: int = 0
    quizzes: int = 0
    assignments: int = 0
    concept_map: bool = False
    actual: dict[str, int] = Field(default_factory=dict)     # artifact[:subtype] -> count present
    expected: dict[str, int] = Field(default_factory=dict)   # artifact[:subtype] -> count this week should have
    gaps: dict[str, Shortfall] = Field(default_factory=dict)  # shortfalls only: artifact -> {has, expects}

    def has_any_artifact(self) -> bool:
        return bool(self.pages or self.quizzes or self.assignments or self.concept_map)

    def is_real(self) -> bool:
        """A week worth reporting: it has declared material or at least one artifact."""
        return bool(self.materials) or self.has_any_artifact()

    @property
    def nothing_generated(self) -> bool:
        """Material is present but no artifact was generated from it (Phase-1 sense 1)."""
        return bool(self.materials) and not self.has_any_artifact()


class ScopeCensus(BaseModel):
    """A module or the whole course measured against a declared module/course rule (Layer B)."""
    model_config = ConfigDict(extra="forbid")
    name: str
    actual: dict[str, int] = Field(default_factory=dict)
    expected: dict[str, int] = Field(default_factory=dict)
    gaps: dict[str, Shortfall] = Field(default_factory=dict)


class Census(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_title: str | None = None
    weeks: list[WeekCensus] = Field(default_factory=list)
    # where each week's `expected` came from: a DECLARED `expect:` block, or the course's own MODAL pattern
    expectation_basis: Literal["declared", "modal"] = "modal"
    modal_norm: dict[str, int] = Field(default_factory=dict)  # modal basis: artifact -> generating weeks with it
    generating_weeks: int = 0                                  # modal basis: the norm's denominator
    modules: list[ScopeCensus] = Field(default_factory=list)  # declared module rules, one entry per module
    course: ScopeCensus | None = None                          # declared course rules
    grading_groups: list[str] = Field(default_factory=list)          # declared group names (STRC-2)
    unused_grading_groups: list[str] = Field(default_factory=list)   # declared groups with no items placed
    unreadable: list[str] = Field(default_factory=list)   # artifact files present but unreadable (counted, flagged)

    @property
    def gap_count(self) -> int:
        """Every unmet expectation, plus each modal-basis week that has material but produced nothing
        and carries no per-type shortfall (an empty norm can't name what's missing)."""
        weeks = sum(len(w.gaps) or (1 if self.expectation_basis == "modal" and w.nothing_generated else 0)
                    for w in self.weeks)
        scopes = sum(len(m.gaps) for m in self.modules) + (len(self.course.gaps) if self.course else 0)
        return weeks + scopes + len(self.unused_grading_groups)

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


def _load_json(p: Path, unreadable: list[str]) -> dict:
    """An artifact's JSON. One that is present but unreadable still COUNTS (the census is presence),
    but is listed in `unreadable` and warned about — never silently read as empty."""
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        unreadable.append(str(p))
        outcomes.warn("census.unreadable_artifact", f"  {p}: unreadable ({type(e).__name__}) — counted, "
                      f"but its contents couldn't be read.", path=str(p))
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
    unreadable: list[str] = []

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
        d = _load_json(pj, unreadable)
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
            groups = _load_json(bj, unreadable).get("groups") or {}
            if any(isinstance(g, dict) and g.get("question_type") == "open_response" for g in groups.values()):
                _bump(w, "quiz:eu")                          # the EU performance question (ASMT-3)
            placed.append(("quiz", bj.parent.name))
    for aj in sorted(root.glob("assignments/*/assignment.json")):
        d = _load_json(aj, unreadable)
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
                    weeks=sorted((w for w in weeks.values()), key=lambda w: _wsort(w.week)),
                    unreadable=[str(Path(u).relative_to(root)) if Path(u).is_relative_to(root) else u
                                for u in unreadable])
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


_COARSE = ("page", "quiz", "assignment", "concept-map")


def _modal_gaps(census: Census) -> None:
    """Phase-1 presence gaps when no expectation is declared: each REAL week is expected to carry the
    course's own MODAL types — those a strict majority of GENERATING weeks have (the denominator excludes
    nothing-generated weeks so a 2-of-3 norm reads correctly). The norm is stored as data."""
    census.expectation_basis = "modal"
    real = [w for w in census.weeks if w.is_real()]
    generating = [w for w in real if w.has_any_artifact()]
    n = len(generating)
    counts = {a: sum(1 for w in generating if w.actual.get(a)) for a in _COARSE}
    census.generating_weeks = n
    census.modal_norm = {a: c for a, c in counts.items() if c * 2 > n}
    for w in real:
        w.expected = {a: 1 for a in census.modal_norm}
        w.gaps = _shortfalls(w.actual, w.expected)


def _expectation_gaps(census: Census, struct, exp) -> None:
    """Layer B — declared `expected − actual`, per scope. WEEK rules apply to every known week (incl. a
    declared-but-empty one — the denominator widens, so it becomes a real gap); MODULE rules are met by
    matching artifacts in ANY week of the module; COURSE rules over the whole course."""
    census.expectation_basis = "declared"
    for w in census.weeks:
        w.expected = exp.for_week(w.week)
        w.gaps = _shortfalls(w.actual, w.expected)

    if exp.module or exp.module_overrides:
        mods: dict = {}
        for w in census.weeks:
            m = struct.week_module(w.week)
            if m:
                mods.setdefault(m, []).append(w)
        for mod, members in mods.items():
            actual = _sum_actual(members)
            expected = exp.for_module(mod)
            census.modules.append(ScopeCensus(name=mod, actual=actual, expected=expected,
                                              gaps=_shortfalls(actual, expected)))

    if exp.course:
        actual = _sum_actual(census.weeks)
        census.course = ScopeCensus(name="course", actual=actual, expected=dict(exp.course),
                                    gaps=_shortfalls(actual, exp.course))


def _sum_actual(weeks) -> dict:
    out: dict = {}
    for w in weeks:
        for a, c in w.actual.items():
            out[a] = out.get(a, 0) + c
    return out


def _grading_gaps(census: Census, struct, placed: list[tuple[str, str]]) -> None:
    """A declared grading group (STRC-2) that no item is placed in. Resolve each item's group the way
    the emitter does — slug override → kind default — so the gap reflects the real placement."""
    scheme = struct.grading()
    census.grading_groups = [name for name, _ in scheme.group_list()]
    if scheme.has_scheme():
        used = {scheme.group_for(kind, slug=slug) for kind, slug in placed}
        census.unused_grading_groups = [n for n in census.grading_groups if n not in used]


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

    lines += ["", "## Gaps", ""] + (_gap_lines(census) or ["No gaps found."])
    if census.unreadable:
        lines += ["", "## Unreadable artifacts", "",
                  "Present (so counted above) but their contents couldn't be read — regenerate or repair them:", ""]
        lines += [f"- `{u}`" for u in census.unreadable]
    return "\n".join(lines) + "\n"


_LABEL = {"concept-map": "concept map"}   # display wording only — the data key stays `concept-map`


def _gap_lines(census: Census) -> list[str]:
    """The human-readable gap list, rendered from the structured gap data (never stored as prose)."""
    out = []
    modal = census.expectation_basis == "modal"
    for w in census.weeks:
        if modal and w.nothing_generated:
            out.append(f"- **{w.label}** — has material but nothing generated yet")
            continue
        for art, s in w.gaps.items():
            if modal:
                out.append(f"- **{w.label}** — no {_LABEL.get(art, art)} (but {census.modal_norm[art]}/"
                           f"{census.generating_weeks} weeks have one)")
            else:
                out.append(f"- **{w.label}** — {_LABEL.get(art, art)}: has {s.has}, expects {s.expects}")
    for m in census.modules:
        for art, s in m.gaps.items():
            out.append(f'- **Module "{m.name}"** — {_LABEL.get(art, art)}: has {s.has}, expects {s.expects}')
    if census.course:
        for art, s in census.course.gaps.items():
            out.append(f"- **Course** — {_LABEL.get(art, art)}: has {s.has}, expects {s.expects}")
    for name in census.unused_grading_groups:
        out.append(f'- **Grading** — group "{name}" declared but no items are placed in it')
    return out


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
