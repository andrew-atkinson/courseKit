"""The assignment IR (ASMT-4) — a canonical, platform-neutral assignment.

An assignment is a brief the student acts on: some framing, a task, what to hand in, and how it's
judged, plus the Canvas settings that make it a real graded item (submission type, points). Like
`bank.json`/`page.json`, this is the neutral form every emitter reads — the Canvas Assignment emitter
is the first (`coursekit/emit/assignment.py`).

`rubric_criteria` is a FLAT list for v1 (rendered into the instructions, as the open-response quiz
question does). The STRUCTURED Canvas rubric object — criteria × levels × points — is ASMT-7, gated on
a real rubric-bearing export to ground its CC format (this repo has an assignment export, but with no
rubric attached).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The submission types coursekit emits; matches Canvas's `submission_types` values. `online_text_entry`
# is the default (and what the grounding export uses) — a written response, gradable by hand.
SubmissionType = Literal["online_text_entry", "online_upload", "on_paper", "none"]


class RubricRating(BaseModel):
    """One performance LEVEL of a criterion — e.g. 'Excellent analysis' worth 35 points."""
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1)
    points: float = Field(ge=0)


class RubricCriterion(BaseModel):
    """One row of the rubric — what's judged, and the levels it can score."""
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1)              # the criterion, e.g. "Written analysis"
    long_description: str = ""
    weight: float | None = Field(default=None, gt=0)   # relative importance; None ⇒ use the top level
    ratings: list[RubricRating] = Field(min_length=1)  # levels, highest → lowest

    @property
    def points(self) -> float:
        return max(r.points for r in self.ratings)     # the top level (the model's authored/relative value)

    @property
    def effective_weight(self) -> float:
        """Faculty-declared weight, else the model's top level as its implied weight (STRC-3)."""
        return self.weight if self.weight is not None else self.points


class Rubric(BaseModel):
    """A structured Canvas rubric — criteria × levels × points (grounded from the ARGS260 export).

    Point VALUES are user-guided with model-derived defaults (STRC-3): when `points_total` is set the
    total is deterministic (faculty-declared, not the model's invented sum) and each criterion's points
    are DERIVED = total × weight / Σweights, so editing a `weight` or the total and re-emitting re-derives
    with no model. `points_total=None` is the legacy path — each criterion's top level is its points.
    """
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    points_total: float | None = Field(default=None, gt=0)   # authoritative total; None ⇒ legacy (sum of tops)
    criteria: list[RubricCriterion] = Field(min_length=1)

    def resolved_points(self) -> list[float]:
        """Absolute points per criterion. Deterministic from (points_total, weights); the rounding
        remainder goes to the largest criterion so the criteria sum EXACTLY to the total."""
        if self.points_total is None:
            return [c.points for c in self.criteria]             # legacy: top level is the value
        ws = [c.effective_weight for c in self.criteria]
        tot = sum(ws) or 1.0
        raw = [self.points_total * w / tot for w in ws]
        pts = [round(x, 1) for x in raw]
        diff = round(self.points_total - sum(pts), 1)
        if diff:
            i = max(range(len(raw)), key=raw.__getitem__)        # remainder → the heaviest criterion
            pts[i] = round(pts[i] + diff, 1)
        return pts

    def resolved(self) -> list[tuple[float, list[tuple[str, float]]]]:
        """(criterion_points, [(level_desc, level_points)]) fully scaled to absolute — the emitter reads
        this. A criterion's levels keep the model's SHAPE (top→bottom ratios), scaled to its points."""
        out = []
        for c, P in zip(self.criteria, self.resolved_points()):
            top = c.points or 1.0
            out.append((P, [(r.description, P if r.points == top else round(P * r.points / top, 1))
                            for r in c.ratings]))
        return out

    @property
    def points_possible(self) -> float:
        return self.points_total if self.points_total is not None else sum(self.resolved_points())


class Assignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    week_ref: str | None = None
    slug: str = "assignment"
    submission_type: SubmissionType = "online_text_entry"
    points: float = Field(default=10.0, ge=0)          # used only when no structured rubric is attached
    overview: str = ""                                 # why it matters / context (optional)
    task: str = Field(min_length=1)                    # what the student does (intro prose)
    steps: list[str] = Field(default_factory=list)     # the task's requirements, as a numbered list
    deliverable: str = ""                              # what to hand in (optional)
    rubric_criteria: list[str] = Field(default_factory=list)   # flat, in the instructions (no rubric)
    rubric: Rubric | None = None                       # structured Canvas rubric (ASMT-7); overrides points

    @property
    def group_title(self) -> str:
        """The Canvas assignment group this lands in. One neutral group for now."""
        return "Assignments"

    @property
    def effective_points(self) -> float:
        """A structured rubric sets the total (Canvas ties them); else the plain `points`."""
        return self.rubric.points_possible if self.rubric else self.points


# Instructions are RENDERED in emit/assignment.py: the fields become a Page of typed blocks and go
# through the page renderer (themed, inline-Markdown, Canvas-safe) — the same design system as a page.
# The IR stays pure data; nothing here renders HTML.
