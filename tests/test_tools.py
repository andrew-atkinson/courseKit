import inspect
import json
import pytest
from coursekit.generate.quiz import bank as bankmod
from coursekit.generate.quiz import tools
from coursekit.generate.quiz.tools import _SCHEMAS, TOOL_REGISTRY, _dispatch_one


@pytest.fixture(autouse=True)
def clean():
    bankmod.reset()
    tools.checklist.clear()
    tools.completed.clear()
    tools.set_call_log(None)


# ------------------------------------------------- schema / signature drift

@pytest.mark.parametrize("name", sorted(TOOL_REGISTRY))
def test_schema_matches_function_signature(name):
    """Hand-written schemas can drift from their functions. This is the whole reason
    that risk is acceptable."""
    fn = TOOL_REGISTRY[name]
    sig = inspect.signature(fn)
    params = set(sig.parameters)
    schema = _SCHEMAS[name]["parameters"]

    assert set(schema["properties"]) == params, f"{name}: schema properties != parameters"

    required = {p for p, v in sig.parameters.items() if v.default is inspect.Parameter.empty}
    assert set(schema["required"]) == required, f"{name}: schema required != params w/o defaults"


@pytest.mark.parametrize("name", sorted(TOOL_REGISTRY))
def test_schema_name_matches_registry_key(name):
    assert _SCHEMAS[name]["name"] == name


def test_every_registered_tool_is_exposed_to_the_model():
    exposed = {t["function"]["name"] for t in tools.tools}
    assert exposed == set(TOOL_REGISTRY)


def test_every_tool_returns_a_string():
    for name, fn in TOOL_REGISTRY.items():
        assert inspect.signature(fn).return_annotation is str, name


# ------------------------------------------------------------- dispatch

class TestDispatch:
    def test_unknown_tool_names_the_alternatives(self):
        out = _dispatch_one("add_essay_variant", "{}")
        assert out.startswith("ERROR: no tool named")
        assert "add_multiple_choice_variant" in out

    def test_namespace_bleed_is_closed(self):
        # globals() would have resolved these to real module-level objects.
        for name in ["json", "os", "show", "tools", "bank", "Console", "checklist"]:
            assert _dispatch_one(name, "{}").startswith("ERROR: no tool named")

    def test_empty_arguments_string_does_not_raise(self):
        # Zero-arg tools commonly arrive as "" and json.loads("") raises.
        bankmod.create_group("c1", "Loops", "multiple_choice")
        assert not _dispatch_one("get_bank_report", "").startswith("ERROR")
        assert not _dispatch_one("get_bank_report", None).startswith("ERROR")
        assert not _dispatch_one("get_bank_report", "   ").startswith("ERROR")

    def test_malformed_json_is_reported_not_raised(self):
        out = _dispatch_one("create_question_group", '{"group_id": "c1",,}')
        assert out.startswith("ERROR: arguments")
        assert "valid JSON" in out

    def test_non_object_arguments(self):
        assert _dispatch_one("get_bank_report", "[1,2]").startswith("ERROR: arguments")

    def test_missing_required_argument(self):
        out = _dispatch_one("create_question_group", '{"group_id": "c1"}')
        assert out.startswith("ERROR: wrong arguments")

    def test_unexpected_argument(self):
        out = _dispatch_one("get_bank_report", '{"nope": 1}')
        assert out.startswith("ERROR: wrong arguments")

    def test_wrong_type_is_reported_in_plain_language(self):
        bankmod.create_group("c1", "Loops", "multiple_choice")
        out = _dispatch_one("add_multiple_choice_variant", json.dumps({
            "group_id": "c1", "variant_label": "A",
            "question_text": "Which one is correct here?",
            "variant_summary": "Basic recall",
            "options": ["a", "b", "c", "d"], "correct_index": "B",
        }))
        assert out.startswith("ERROR")
        assert "correct_index" in out
        assert "[type=" not in out  # pydantic jargon must not reach the model

    def test_a_rejected_call_leaves_the_bank_untouched(self):
        bankmod.create_group("c1", "Loops", "multiple_choice")
        _dispatch_one("add_multiple_choice_variant", json.dumps({
            "group_id": "c1", "variant_label": "A",
            "question_text": "Which one is correct here?",
            "variant_summary": "Basic recall",
            "options": ["a", "b", "c", "d"], "correct_index": 99,
        }))
        assert bankmod.get().groups["c1"].variants == {}


# --------------------------------------------------------- the happy path

def _add(label, correct):
    return _dispatch_one("add_multiple_choice_variant", json.dumps({
        "group_id": "c1", "variant_label": label,
        "question_text": f"Question {label} about for loops?",
        "variant_summary": f"Angle {label}",
        "options": ["init, condition, incrementer", "start, end, step",
                    "declaration, boolean, update", "start, end, incrementer"],
        "correct_index": correct,
    }))


def test_full_group_through_the_dispatcher():
    assert not _dispatch_one("create_question_group", json.dumps({
        "group_id": "c1", "concept_title": "Anatomy of a for loop",
        "question_type": "multiple_choice"})).startswith("ERROR")
    for i, lbl in enumerate("ABCD"):
        assert not _add(lbl, i).startswith("ERROR")
    assert bankmod.validate_final() == []


def test_position_collision_steers_the_model():
    _dispatch_one("create_question_group", json.dumps({
        "group_id": "c1", "concept_title": "Loops", "question_type": "multiple_choice"}))
    _add("A", 0)
    out = _add("B", 0)
    assert "already" in out and "Free positions: [1, 2, 3]" in out


def test_revision_replaces_through_the_dispatcher():
    _dispatch_one("create_question_group", json.dumps({
        "group_id": "c1", "concept_title": "Loops", "question_type": "multiple_choice"}))
    _add("A", 0)
    out = _add("A", 0)
    assert "replaced" in out
    assert list(bankmod.get().groups["c1"].variants) == ["A"]


def test_matching_pairs_arrive_as_dicts():
    _dispatch_one("create_question_group", json.dumps({
        "group_id": "c5", "concept_title": "Terms", "question_type": "matching"}))
    out = _dispatch_one("add_matching_variant", json.dumps({
        "group_id": "c5", "variant_label": "A",
        "question_text": "Match each function to what it does.",
        "variant_summary": "Function purposes",
        "pairs": [{"left": "map()", "right": "rescales a value"},
                  {"left": "circle()", "right": "draws a circle"},
                  {"left": "rect()", "right": "draws a rectangle"}],
    }))
    assert not out.startswith("ERROR")
    assert len(bankmod.get().groups["c5"].variants["A"].pairs) == 3


# ------------------------------------------------------- checklist hygiene

def test_checklist_report_to_the_model_has_no_rich_markup():
    # It is re-sent every turn; markup here teaches the model to emit markup.
    create = _dispatch_one("create_checklist", json.dumps({"descriptions": ["one", "two"]}))
    assert "[green]" not in create and "[strike]" not in create
    marked = _dispatch_one("mark_complete", json.dumps({"index": 1, "completion_notes": "done"}))
    assert "[green]" not in marked and "[strike]" not in marked
    assert "#1 [x] one" in marked


def test_mark_complete_out_of_range_does_not_raise():
    _dispatch_one("create_checklist", json.dumps({"descriptions": ["one"]}))
    assert _dispatch_one("mark_complete",
                         json.dumps({"index": 9, "completion_notes": "x"})).startswith("ERROR")


# ------------------------------------------------------------- replay

def test_replay_reconstructs_a_run_with_no_model(tmp_path):
    log = tmp_path / "calls.jsonl"
    tools.set_call_log(log)

    from coursekit.providers import ToolCall

    handled = tools.run_tool_calls([
        ToolCall(id="call_1", name="create_question_group", arguments=json.dumps({
            "group_id": "c1", "concept_title": "Loops", "question_type": "multiple_choice"})),
        ToolCall(id="call_2", name="add_multiple_choice_variant", arguments=json.dumps({
            "group_id": "c1", "variant_label": "A",
            "question_text": "Question A about for loops?",
            "variant_summary": "Angle A",
            "options": ["a", "b", "c", "d"], "correct_index": 0})),
    ])
    # (tool_call_id, content) pairs — message shaping belongs to the provider.
    assert [call_id for call_id, _ in handled] == ["call_1", "call_2"]
    assert all(not content.startswith("ERROR") for _, content in handled)

    bankmod.reset()
    tools.set_call_log(None)
    results = tools.replay(log)
    assert len(results) == 2
    assert bankmod.get().groups["c1"].variants["A"].correct_index == 0
