"""Assignment generation (ASMT-4) — the model drafts the CONTENT; the program owns the rest.

Same discipline as the EU pass: that there IS an assignment (with a rubric) is a decision, not a
model judgment. The model only writes the brief (overview / task / deliverable) and the rubric
(criteria × levels), committed through tools rather than free text, and the program assembles the
canonical `Assignment` + `assignment.json` the emitter reads.

Scope: v1 defaults to the WEEK's material, but `build_assignment` takes the material + a short scope
description as parameters — the SCOPE axis (PAGE-13) is a caller concern, so an assignment spanning
several weeks or drawing on earlier work is a matter of what material/scope the caller passes, not a
change here.
"""

from pathlib import Path

from coursekit import prompts
from coursekit.generate import dispatch
from coursekit.generate.assignment.assignment import (Assignment, Rubric, RubricCriterion,
                                                      RubricRating)

# --------------------------------------------------------------- the draft
class AssignmentDraft:
    """An assignment being built, and where it saves."""

    def __init__(self, *, assignment_id: str, slug: str, week_ref, default_points: float, out_dir=None):
        self.assignment_id, self.slug, self.week_ref = assignment_id, slug, week_ref
        self.default_points = default_points
        self.out_dir = Path(out_dir) if out_dir else None
        self.brief: dict | None = None
        self.criteria: list[dict] = []
        self.finalized = False

    def is_finalized(self) -> bool:
        return self.finalized

    def _build(self) -> Assignment | str:
        b = self.brief
        if not b:
            return "ERROR: call set_assignment first (title + task)."
        criteria = [RubricCriterion(description=c["description"], long_description=c.get("long_description", ""),
                                    weight=c.get("weight"),
                                    ratings=[RubricRating(**lv) for lv in c["levels"]])
                    for c in self.criteria]
        # points_total is the DETERMINISTIC, faculty-set grade total (STRC-3) — not the model's level sum
        rubric = (Rubric(title=f"{b['title']} — Rubric", points_total=self.default_points,
                         criteria=criteria) if criteria else None)
        try:
            return Assignment(assignment_id=self.assignment_id, title=b["title"], slug=self.slug,
                              week_ref=self.week_ref, submission_type=b["submission_type"],
                              points=self.default_points, overview=b.get("overview", ""),
                              task=b["task"], steps=b.get("steps", []),
                              deliverable=b.get("deliverable", ""), rubric=rubric)
        except Exception as e:
            return f"ERROR: {e}"

    @property
    def assignment(self) -> Assignment | None:
        a = self._build()
        return a if isinstance(a, Assignment) else None

    def set_brief(self, title: str, task: str, overview: str, deliverable: str, steps: list | None,
                  submission_type: str) -> str:
        self.brief = {"title": title, "task": task, "overview": overview, "deliverable": deliverable,
                      "steps": steps or [], "submission_type": submission_type}
        return f"OK brief set: {title!r} ({submission_type}). Now add rubric criteria."

    def add_criterion(self, description: str, levels: list, long_description: str, weight: float | None) -> str:
        # validate now so a bad criterion is a correctable error, not a finalize-time surprise
        RubricCriterion(description=description, long_description=long_description, weight=weight,
                        ratings=[RubricRating(**lv) for lv in levels])
        self.criteria.append({"description": description, "long_description": long_description,
                              "weight": weight, "levels": levels})
        return f"OK criterion {len(self.criteria)}: {description!r} ({len(levels)} levels)."

    def finalize(self) -> str:
        a = self._build()
        if isinstance(a, str):
            return a
        if not a.rubric:
            return "ERROR: add at least one rubric criterion (add_rubric_criterion) before finalizing."
        self.finalized = True
        if self.out_dir is not None:
            (self.out_dir / "assignment.json").write_text(a.model_dump_json(indent=2), encoding="utf-8")
        return f"OK finalized: {a.title!r}, {len(a.rubric.criteria)} criteria, {a.effective_points:.0f} pts."


# --------------------------------------------------------------- tools
_LEVEL_ITEM = {"type": "object", "properties": {
    "description": {"type": "string", "description": "the level, e.g. 'Excellent'"},
    "points": {"type": "number", "description": "points for this level"}},
    "required": ["description", "points"], "additionalProperties": False}

TOOL_SPECS = [
    {"name": "set_assignment",
     "description": "Set the assignment brief. Call once before the rubric.",
     "parameters": {"type": "object", "properties": {
         "title": {"type": "string", "description": "a short assignment title"},
         "task": {"type": "string", "description": "what the student does — the core prompt (intro prose)"},
         "overview": {"type": "string", "description": "1-2 sentences of why it matters / context"},
         "steps": {"type": "array", "items": {"type": "string"},
                   "description": ("the task's requirements as a numbered list, ONE per item — do NOT "
                                   "write them as '1. 2. 3.' inside `task`. Inline `code` and **bold** "
                                   "are fine and render.")},
         "deliverable": {"type": "string", "description": "what to hand in"},
         "submission_type": {"type": "string",
                             "enum": ["online_text_entry", "online_upload", "on_paper"],
                             "description": "how students submit"}},
         "required": ["title", "task"], "additionalProperties": False}},
    {"name": "add_rubric_criterion",
     "description": ("Add ONE rubric row: what's judged + its performance levels (highest first). You do "
                     "NOT set the grade total — the instructor sets that; you set each criterion's "
                     "relative IMPORTANCE and its levels."),
     "parameters": {"type": "object", "properties": {
         "description": {"type": "string", "description": "the criterion, e.g. 'Analysis'"},
         "long_description": {"type": "string", "description": "a fuller sentence (optional)"},
         "weight": {"type": "number",
                    "description": ("this criterion's relative importance vs the others (e.g. 2 = twice "
                                    "as important). Optional — omit and the top level's value is used.")},
         "levels": {"type": "array", "items": _LEVEL_ITEM,
                    "description": ("3-5 levels high→low. The numbers are RELATIVE (the shape of partial "
                                    "credit), e.g. [{description:'Excellent',points:4},{...'Good',points:3},"
                                    "{...'Missing',points:0}] — they are rescaled to the instructor's total.")}},
         "required": ["description", "levels"], "additionalProperties": False}},
    {"name": "finalize_assignment",
     "description": "Write the assignment out. Call last, after the brief and 3-4 criteria.",
     "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
]


class AssignmentTools(dispatch.ToolSession):
    """The tools the model calls for one assignment — the same contract as quizzes and pages: never
    raise, actionable ERROR strings, stop after finalize, and a calls.jsonl beside the output for replay."""

    SCHEMAS = {spec["name"]: spec for spec in TOOL_SPECS}
    TERMINAL = frozenset({"finalize_assignment"})

    def __init__(self, draft: AssignmentDraft):
        super().__init__(draft.out_dir / "calls.jsonl" if draft.out_dir else None)
        self.draft = draft

    def set_assignment(self, title: str, task: str, overview: str = "", deliverable: str = "",
                       steps: list | None = None, submission_type: str = "online_text_entry") -> str:
        return self.draft.set_brief(title, task, overview, deliverable, steps, submission_type)

    def add_rubric_criterion(self, description: str, levels: list, long_description: str = "",
                             weight: float | None = None) -> str:
        return self.draft.add_criterion(description, levels, long_description, weight)

    def finalize_assignment(self) -> str:
        return self.draft.finalize()


class _AssignmentGenerator:
    """One-artifact generator for the shared loop: a small tool set, finalized when the model
    commits a valid assignment."""

    def __init__(self, tools: AssignmentTools):
        self.tools = tools

    def tool_specs(self):
        return TOOL_SPECS

    def run_tool_calls(self, calls):
        return self.tools.run_tool_calls(calls)

    def is_finalized(self):
        return self.tools.draft.is_finalized()

    def nudge(self, *, stalled: bool) -> str:
        have_brief = bool(self.tools.draft.brief)
        n = len(self.tools.draft.criteria)
        return (f"Keep going with tool calls only. Brief set: {have_brief}; criteria: {n}. "
                "Call set_assignment (if not yet), then add_rubric_criterion 3-4 times, then "
                "finalize_assignment. No prose.")


# --------------------------------------------------------------- driver
def build_assignment(unit, provider, model, out_dir, *, material: str | None = None,
                     scope: str = "this week", project_root=None):
    """Draft one assignment for `unit` from `material` (defaults to the week's transcript). `scope`
    names what the assignment covers, woven into the brief. Returns (Assignment|None, problems)."""
    from coursekit.pipeline import loop

    project_root = project_root or unit.course_root
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    material = material if material is not None else Path(unit.transcript_path).read_text(
        encoding="utf-8", errors="replace")

    from coursekit import courseconfig
    cfg = courseconfig.load(unit.transcript_path, config_name="assignment.yaml")
    points = float(cfg.value("assignment_points") or 10)
    base = (unit.week_slug or "assignment")
    draft = AssignmentDraft(assignment_id=f"{unit.course_slug}-{base}", slug=f"{base}-assignment",
                            week_ref=unit.week_slug, default_points=points, out_dir=out_dir)

    system = (courseconfig.domain_preface(cfg.domain) + courseconfig.voice_preface(cfg.voice)
              + prompts.load("assignment", "default", project_root=project_root).body)
    user = (f"Scope: {scope}.\n\nThe material to base the assignment on:\n<material>\n{material}\n"
            f"</material>\n\nDraft the assignment now.")
    loop([{"role": "system", "content": system}, {"role": "user", "content": user}],
         provider, model, _AssignmentGenerator(AssignmentTools(draft)), max_iters=12)

    a = draft.assignment
    problems = [] if (a and draft.is_finalized()) else ["assignment did not finalize"]
    return a, problems
