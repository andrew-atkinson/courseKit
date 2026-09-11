"""Assignment generation tools + state (ASMT-4) — offline, no model. The tools commit content; the
program assembles the canonical Assignment."""

import pytest

from coursekit.generate.assignment import build as ab
from coursekit.generate.assignment.assignment import Assignment


@pytest.fixture(autouse=True)
def _fresh(tmp_path):
    ab.reset(assignment_id="c-w3", slug="week-3-assignment", week_ref="week-3",
             default_points=10, out_dir=tmp_path)


def test_tools_build_a_valid_assignment_with_a_rubric(tmp_path):
    ab.reset(assignment_id="c-w3", slug="week-3-assignment", week_ref="week-3",
             default_points=30, out_dir=tmp_path)
    assert ab.set_assignment("Apply loops", "Make a grid of shapes using loops and map().",
                             overview="Connects the week to practice.",
                             deliverable="a p5.js sketch").startswith("OK")
    ab.add_rubric_criterion("Technique", [{"description": "Strong", "points": 20},
                                          {"description": "Weak", "points": 5}])
    ab.add_rubric_criterion("Creativity", [{"description": "High", "points": 10},
                                           {"description": "Low", "points": 2}])
    assert ab.finalize_assignment().startswith("OK finalized") and ab.is_finalized()

    a = ab.get()
    assert isinstance(a, Assignment) and a.rubric is not None
    # the total is the DETERMINISTIC configured 30, split by the model's implied weights (20:10 = 2:1)
    assert a.effective_points == 30.0
    assert a.rubric.resolved_points() == [20.0, 10.0]
    assert (tmp_path / "assignment.json").exists()


def test_total_is_deterministic_not_the_models_level_sum(tmp_path):
    """The bug fix: the configured total wins; the model's level numbers only set the split."""
    ab.reset(assignment_id="c", slug="a", week_ref="w", default_points=100, out_dir=tmp_path)
    ab.set_assignment("T", "Apply the idea to a new case and explain your reasoning.")
    ab.add_rubric_criterion("A", [{"description": "hi", "points": 999}, {"description": "lo", "points": 0}])
    ab.add_rubric_criterion("B", [{"description": "hi", "points": 999}, {"description": "lo", "points": 0}])
    assert ab.finalize_assignment().startswith("OK")
    a = ab.get()
    assert a.effective_points == 100.0                       # not 999+999
    assert a.rubric.resolved_points() == [50.0, 50.0]        # equal implied weights → even split


def test_faculty_weight_overrides_the_split(tmp_path):
    ab.reset(assignment_id="c", slug="a", week_ref="w", default_points=100, out_dir=tmp_path)
    ab.set_assignment("T", "Apply the idea to a new case and explain your reasoning.")
    ab.add_rubric_criterion("A", [{"description": "hi", "points": 4}], weight=3)
    ab.add_rubric_criterion("B", [{"description": "hi", "points": 4}], weight=1)
    ab.finalize_assignment()
    a = ab.get()
    assert a.rubric.resolved_points() == [75.0, 25.0]        # weights 3:1 of 100, exact


def test_a_bad_level_becomes_a_correctable_error_through_the_dispatcher():
    import json
    import types
    tc = types.SimpleNamespace(id="x", name="add_rubric_criterion",
                               arguments=json.dumps({"description": "T", "levels": [{"description": "S"}]}))
    (_id, out), = ab.run_tool_calls([tc])       # missing points → an ERROR string, not a crash
    assert out.startswith("ERROR")


def test_finalize_needs_a_brief_and_at_least_one_criterion():
    assert ab.finalize_assignment().startswith("ERROR")          # no brief yet
    ab.set_assignment("T", "Do the task thoroughly and explain your choices.")
    assert ab.finalize_assignment().startswith("ERROR")          # brief but no rubric
    assert not ab.is_finalized()


def test_run_tool_calls_dispatches_and_stops_after_finalize():
    import types

    def _tc(name, args):
        return types.SimpleNamespace(id=name, name=name, arguments=__import__("json").dumps(args))

    results = ab.run_tool_calls([
        _tc("set_assignment", {"title": "T", "task": "Apply the idea to a new case."}),
        _tc("add_rubric_criterion", {"description": "Depth",
                                     "levels": [{"description": "Good", "points": 10}]}),
        _tc("finalize_assignment", {}),
        _tc("set_assignment", {"title": "late", "task": "ignored after finalize"}),
    ])
    assert ab.is_finalized()
    assert results[-1][1].startswith("(ignored")                 # nothing after finalize takes effect
