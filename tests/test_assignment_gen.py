"""Assignment generation tools + state (ASMT-4) — offline, no model. The tools commit content; the
program assembles the canonical Assignment."""

import pytest

from coursekit.generate.assignment import build as ab
from coursekit.generate.assignment.assignment import Assignment


def _tools(out_dir=None, *, id="c", slug="a", week_ref="w", points=10):
    return ab.AssignmentTools(ab.AssignmentDraft(assignment_id=id, slug=slug, week_ref=week_ref,
                                                 default_points=points, out_dir=out_dir))


@pytest.fixture
def s(tmp_path):
    return _tools(tmp_path, id="c-w3", slug="week-3-assignment", week_ref="week-3")


def test_tools_build_a_valid_assignment_with_a_rubric(tmp_path):
    s = _tools(tmp_path, id="c-w3", slug="week-3-assignment", week_ref="week-3", points=30)
    assert s.set_assignment("Apply loops", "Make a grid of shapes using loops and map().",
                             overview="Connects the week to practice.",
                             deliverable="a p5.js sketch").startswith("OK")
    s.add_rubric_criterion("Technique", [{"description": "Strong", "points": 20},
                                          {"description": "Weak", "points": 5}])
    s.add_rubric_criterion("Creativity", [{"description": "High", "points": 10},
                                           {"description": "Low", "points": 2}])
    assert s.finalize_assignment().startswith("OK finalized") and s.draft.is_finalized()

    a = s.draft.assignment
    assert isinstance(a, Assignment) and a.rubric is not None
    # the total is the DETERMINISTIC configured 30, split by the model's implied weights (20:10 = 2:1)
    assert a.effective_points == 30.0
    assert a.rubric.resolved_points() == [20.0, 10.0]
    assert (tmp_path / "assignment.json").exists()


def test_total_is_deterministic_not_the_models_level_sum(tmp_path):
    """The bug fix: the configured total wins; the model's level numbers only set the split."""
    s = _tools(tmp_path, points=100)
    s.set_assignment("T", "Apply the idea to a new case and explain your reasoning.")
    s.add_rubric_criterion("A", [{"description": "hi", "points": 999}, {"description": "lo", "points": 0}])
    s.add_rubric_criterion("B", [{"description": "hi", "points": 999}, {"description": "lo", "points": 0}])
    assert s.finalize_assignment().startswith("OK")
    a = s.draft.assignment
    assert a.effective_points == 100.0                       # not 999+999
    assert a.rubric.resolved_points() == [50.0, 50.0]        # equal implied weights → even split


def test_faculty_weight_overrides_the_split(tmp_path):
    s = _tools(tmp_path, points=100)
    s.set_assignment("T", "Apply the idea to a new case and explain your reasoning.")
    s.add_rubric_criterion("A", [{"description": "hi", "points": 4}], weight=3)
    s.add_rubric_criterion("B", [{"description": "hi", "points": 4}], weight=1)
    s.finalize_assignment()
    a = s.draft.assignment
    assert a.rubric.resolved_points() == [75.0, 25.0]        # weights 3:1 of 100, exact


def test_a_bad_level_becomes_a_correctable_error_through_the_dispatcher(s):
    import json
    import types
    tc = types.SimpleNamespace(id="x", name="add_rubric_criterion",
                               arguments=json.dumps({"description": "T", "levels": [{"description": "S"}]}))
    (_id, out), = s.run_tool_calls([tc])       # missing points → an ERROR string, not a crash
    assert out.startswith("ERROR")


def test_finalize_needs_a_brief_and_at_least_one_criterion(s):
    assert s.finalize_assignment().startswith("ERROR")          # no brief yet
    s.set_assignment("T", "Do the task thoroughly and explain your choices.")
    assert s.finalize_assignment().startswith("ERROR")          # brief but no rubric
    assert not s.draft.is_finalized()


def test_run_tool_calls_dispatches_and_stops_after_finalize(s):
    import types

    def _tc(name, args):
        return types.SimpleNamespace(id=name, name=name, arguments=__import__("json").dumps(args))

    results = s.run_tool_calls([
        _tc("set_assignment", {"title": "T", "task": "Apply the idea to a new case."}),
        _tc("add_rubric_criterion", {"description": "Depth",
                                     "levels": [{"description": "Good", "points": 10}]}),
        _tc("finalize_assignment", {}),
        _tc("set_assignment", {"title": "late", "task": "ignored after finalize"}),
    ])
    assert s.draft.is_finalized()
    assert results[-1][1].startswith("(ignored")                 # nothing after finalize takes effect


def test_assignment_dispatch_shares_the_quiz_and_page_contract(tmp_path):
    """One dispatcher for every generator: a calls.jsonl beside the output (replayable without a
    model), and a non-object argument refused with the shared, actionable message (the old
    assignment-only dispatcher answered with Python's "argument after ** must be a mapping")."""
    import json
    import types

    s = _tools(tmp_path, id="a", week_ref="week-1")
    calls = [types.SimpleNamespace(id="1", name="set_assignment", arguments="[1, 2]"),
             types.SimpleNamespace(id="2", name="set_assignment",
                                   arguments=json.dumps({"title": "T", "task": "Apply the idea."}))]
    (_, bad), (_, ok) = s.run_tool_calls(calls)
    assert bad == "ERROR: arguments for 'set_assignment' must be a JSON object, got list."
    assert ok.startswith("OK brief set")
    log = tmp_path / "calls.jsonl"
    assert [json.loads(line)["name"] for line in log.read_text().splitlines()] == ["set_assignment"] * 2
    assert _tools(id="a", week_ref="week-1").replay(log)[1].startswith("OK brief set")


def test_two_assignments_built_at_once_do_not_touch_each_other(tmp_path):
    """CORE-3: each run owns its draft, so one starting mid-way through another changes nothing."""
    level = [{"description": "Good", "points": 4}]
    a, b = _tools(tmp_path / "a", id="a", points=10), _tools(tmp_path / "b", id="b", points=20)
    (tmp_path / "a").mkdir(), (tmp_path / "b").mkdir()
    a.set_assignment("First", "The first task, in full.")
    b.set_assignment("Second", "The second task, in full.")
    a.add_rubric_criterion("Only A", level)
    b.add_rubric_criterion("Only B", level)
    a.finalize_assignment()
    assert a.draft.is_finalized() and not b.draft.is_finalized()
    b.finalize_assignment()
    assert (a.draft.assignment.title, a.draft.assignment.effective_points) == ("First", 10.0)
    assert (b.draft.assignment.title, b.draft.assignment.effective_points) == ("Second", 20.0)
    assert [c.description for c in a.draft.assignment.rubric.criteria] == ["Only A"]
    assert Assignment.model_validate_json((tmp_path / "b" / "assignment.json").read_text()).title == "Second"


def test_a_wrong_argument_error_names_the_tool_not_our_class(s):
    """The model reads this text. Methods must not add our class name to what it was always sent."""
    import types
    tc = types.SimpleNamespace(id="x", name="set_assignment", arguments='{"title": "T"}')
    assert s.run_tool_calls([tc])[0][1] == ("ERROR: wrong arguments for 'set_assignment': "
                                            "set_assignment() missing 1 required positional argument: 'task'")
