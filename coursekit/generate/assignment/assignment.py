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

import html
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
    ratings: list[RubricRating] = Field(min_length=1)  # levels, highest → lowest

    @property
    def points(self) -> float:
        return max(r.points for r in self.ratings)     # the criterion's max = its top level


class Rubric(BaseModel):
    """A structured Canvas rubric — criteria × levels × points (grounded from the ARGS260 export)."""
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    criteria: list[RubricCriterion] = Field(min_length=1)

    @property
    def points_possible(self) -> float:
        return sum(c.points for c in self.criteria)


class Assignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    week_ref: str | None = None
    slug: str = "assignment"
    submission_type: SubmissionType = "online_text_entry"
    points: float = Field(default=10.0, ge=0)          # used only when no structured rubric is attached
    overview: str = ""                                 # why it matters / context (optional)
    task: str = Field(min_length=1)                    # what the student does
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


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def render_instructions(a: Assignment) -> str:
    """The assignment's instructions as Canvas-safe HTML (h3/p/ul — all sanitizer-allowed). The flat
    rubric criteria render as a 'How you'll be assessed' list until the structured rubric (ASMT-7)."""
    parts = []
    if a.overview.strip():
        parts.append(f"<p>{_esc(a.overview.strip())}</p>")
    parts.append("<h3>Your task</h3>")
    parts.append(f"<p>{_esc(a.task.strip())}</p>")
    if a.deliverable.strip():
        parts.append("<h3>What to submit</h3>")
        parts.append(f"<p>{_esc(a.deliverable.strip())}</p>")
    if a.rubric_criteria:
        parts.append("<h3>How you'll be assessed</h3>")
        parts.append("<ul>" + "".join(f"<li>{_esc(c)}</li>" for c in a.rubric_criteria) + "</ul>")
    return "\n".join(parts)
