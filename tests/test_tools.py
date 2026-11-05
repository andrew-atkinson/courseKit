import inspect
import json
import pytest
from coursekit.generate.quiz import bank as bankmod
from coursekit.generate.quiz import tools
from coursekit.generate.dispatch import dispatch_one
from coursekit.generate.quiz.tools import _SCHEMAS


def _session(call_log=None):
    return tools.QuizTools(bankmod.BankDraft.new("test"), call_log=call_log)


TOOL_REGISTRY = _session().registry


@pytest.fixture
def s():
    return _session()


def _dispatch_one(s, name, raw_args):
    return dispatch_one(s.registry, name, raw_args)


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
    def test_unknown_tool_names_the_alternatives(self, s):
        out = _dispatch_one(s, "add_essay_variant", "{}")
        assert out.startswith("ERROR: no tool named")
        assert "add_multiple_choice_variant" in out

    def test_namespace_bleed_is_closed(self, s):
        # globals() would have resolved these to real module-level objects.
        for name in ["json", "os", "show", "tools", "bank", "Console", "checklist"]:
            assert _dispatch_one(s, name, "{}").startswith("ERROR: no tool named")

    def test_empty_arguments_string_does_not_raise(self, s):
        # Zero-arg tools commonly arrive as "" and json.loads("") raises.
        s.draft.create_group("c1", "Loops", "multiple_choice")
        assert not _dispatch_one(s, "get_bank_report", "").startswith("ERROR")
        assert not _dispatch_one(s, "get_bank_report", None).startswith("ERROR")
        assert not _dispatch_one(s, "get_bank_report", "   ").startswith("ERROR")

    def test_malformed_json_is_reported_not_raised(self, s):
        out = _dispatch_one(s, "create_question_group", '{"group_id": "c1",,}')
        assert out.startswith("ERROR: arguments")
        assert "valid JSON" in out

    def test_non_object_arguments(self, s):
        assert _dispatch_one(s, "get_bank_report", "[1,2]").startswith("ERROR: arguments")

    def test_missing_required_argument(self, s):
        out = _dispatch_one(s, "create_question_group", '{"group_id": "c1"}')
        assert out.startswith("ERROR: wrong arguments")

    def test_unexpected_argument(self, s):
        out = _dispatch_one(s, "get_bank_report", '{"nope": 1}')
        assert out.startswith("ERROR: wrong arguments")

    def test_wrong_type_is_reported_in_plain_language(self, s):
        s.draft.create_group("c1", "Loops", "multiple_choice")
        out = _dispatch_one(s, "add_multiple_choice_variant", json.dumps({
            "group_id": "c1", "variant_label": "A",
            "question_text": "Which one is correct here?",
            "variant_summary": "Basic recall",
            "options": ["a", "b", "c", "d"], "correct_index": "B",
        }))
        assert out.startswith("ERROR")
        assert "correct_index" in out
        assert "[type=" not in out  # pydantic jargon must not reach the model

    def test_a_rejected_call_leaves_the_bank_untouched(self, s):
        s.draft.create_group("c1", "Loops", "multiple_choice")
        _dispatch_one(s, "add_multiple_choice_variant", json.dumps({
            "group_id": "c1", "variant_label": "A",
            "question_text": "Which one is correct here?",
            "variant_summary": "Basic recall",
            "options": ["a", "b", "c", "d"], "correct_index": 99,
        }))
        assert s.draft.bank.groups["c1"].variants == {}


# --------------------------------------------------------- the happy path

def _add(s, label, correct):
    return _dispatch_one(s, "add_multiple_choice_variant", json.dumps({
        "group_id": "c1", "variant_label": label,
        "question_text": f"Question {label} about for loops?",
        "variant_summary": f"Angle {label}",
        "options": ["init, condition, incrementer", "start, end, step",
                    "declaration, boolean, update", "start, end, incrementer"],
        "correct_index": correct,
    }))


def test_full_group_through_the_dispatcher(s):
    assert not _dispatch_one(s, "create_question_group", json.dumps({
        "group_id": "c1", "concept_title": "Anatomy of a for loop",
        "question_type": "multiple_choice"})).startswith("ERROR")
    for i, lbl in enumerate("ABCD"):
        assert not _add(s, lbl, i).startswith("ERROR")
    assert s.draft.validate_final() == []


def test_position_collision_steers_the_model(s):
    _dispatch_one(s, "create_question_group", json.dumps({
        "group_id": "c1", "concept_title": "Loops", "question_type": "multiple_choice"}))
    _add(s, "A", 0)
    out = _add(s, "B", 0)
    assert "already" in out and "Free positions: [1, 2, 3]" in out


def test_revision_replaces_through_the_dispatcher(s):
    _dispatch_one(s, "create_question_group", json.dumps({
        "group_id": "c1", "concept_title": "Loops", "question_type": "multiple_choice"}))
    _add(s, "A", 0)
    out = _add(s, "A", 0)
    assert "replaced" in out
    assert list(s.draft.bank.groups["c1"].variants) == ["A"]


def test_matching_pairs_arrive_as_dicts(s):
    _dispatch_one(s, "create_question_group", json.dumps({
        "group_id": "c5", "concept_title": "Terms", "question_type": "matching"}))
    out = _dispatch_one(s, "add_matching_variant", json.dumps({
        "group_id": "c5", "variant_label": "A",
        "question_text": "Match each function to what it does.",
        "variant_summary": "Function purposes",
        "pairs": [{"left": "map()", "right": "rescales a value"},
                  {"left": "circle()", "right": "draws a circle"},
                  {"left": "rect()", "right": "draws a rectangle"}],
    }))
    assert not out.startswith("ERROR")
    assert len(s.draft.bank.groups["c5"].variants["A"].pairs) == 3


# ------------------------------------------------------- checklist hygiene

def test_checklist_report_to_the_model_has_no_rich_markup(s):
    # It is re-sent every turn; markup here teaches the model to emit markup.
    create = _dispatch_one(s, "create_checklist", json.dumps({"descriptions": ["one", "two"]}))
    assert "[green]" not in create and "[strike]" not in create
    marked = _dispatch_one(s, "mark_complete", json.dumps({"index": 1, "completion_notes": "done"}))
    assert "[green]" not in marked and "[strike]" not in marked
    assert "#1 [x] one" in marked


def test_mark_complete_out_of_range_does_not_raise(s):
    _dispatch_one(s, "create_checklist", json.dumps({"descriptions": ["one"]}))
    assert _dispatch_one(s, "mark_complete",
                         json.dumps({"index": 9, "completion_notes": "x"})).startswith("ERROR")


# ------------------------------------------------------------- replay

def test_replay_reconstructs_a_run_with_no_model(tmp_path):
    log = tmp_path / "calls.jsonl"
    s = _session(log)

    from coursekit.providers import ToolCall

    handled = s.run_tool_calls([
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

    s = _session()
    results = s.replay(log)
    assert len(results) == 2
    assert s.draft.bank.groups["c1"].variants["A"].correct_index == 0


def test_open_response_variant_records_with_its_criteria(s):
    # ASMT-3: the model records the EU transfer task through the dispatcher like any other variant.
    _dispatch_one(s, "create_question_group", json.dumps(
        {"group_id": "eu", "concept_title": "Enduring understanding",
         "question_type": "open_response"}))
    out = _dispatch_one(s, "add_open_response_variant", json.dumps(
        {"group_id": "eu", "variant_label": "A",
         "question_text": "Apply the idea to a new situation and justify your design.",
         "variant_summary": "EU transfer task",
         "rubric_criteria": ["applies it correctly", "justifies the choice"]}))
    assert not out.startswith("ERROR")
    v = s.draft.bank.groups["eu"].variants["A"]
    assert v.kind == "open_response"
    assert v.rubric_criteria == ["applies it correctly", "justifies the choice"]


# ---- two banks at once: each session writes only to its own draft and checklist (CORE-3) ----

def test_two_banks_built_at_once_do_not_touch_each_other(tmp_path):
    from coursekit.providers import ToolCall

    def call(name, **args):
        return ToolCall(id="c", name=name, arguments=json.dumps(args))

    def variant(group, label, correct):
        return call("add_multiple_choice_variant", group_id=group, variant_label=label,
                    question_text=f"Question {label} about {group}?", variant_summary=f"Angle {label}",
                    options=["a", "b", "c", "d"], correct_index=correct)

    a = tools.QuizTools(bankmod.BankDraft.new("a", tmp_path / "a"), call_log=tmp_path / "a" / "calls.jsonl")
    b = tools.QuizTools(bankmod.BankDraft.new("b", tmp_path / "b"), call_log=tmp_path / "b" / "calls.jsonl")
    a.run_tool_calls([call("create_checklist", descriptions=["only a"]),
                      call("create_question_group", group_id="ga", concept_title="A", question_type="multiple_choice")])
    b.run_tool_calls([call("create_question_group", group_id="gb", concept_title="B", question_type="multiple_choice")])
    a.run_tool_calls([variant("ga", "A", 0), call("finalize_bank")])
    b.run_tool_calls([variant("gb", "A", 0)])
    assert "ERROR" in b.run_tool_calls([variant("ga", "B", 1)])[0][1]    # a's group is not b's to write

    assert list(a.draft.bank.groups) == ["ga"] and a.draft.is_finalized()
    assert list(b.draft.bank.groups) == ["gb"] and not b.draft.is_finalized()
    assert a.checklist == ["only a"] and b.checklist == []
    assert json.loads((tmp_path / "a" / "bank.json").read_text())["run_id"] == "a"
    assert not (tmp_path / "b" / "bank.json").exists()
    assert len((tmp_path / "a" / "calls.jsonl").read_text().splitlines()) == 4
    assert len((tmp_path / "b" / "calls.jsonl").read_text().splitlines()) == 3


# ---- a pass may call only the tools it offers (CORE-3.1) ----

def test_a_session_offering_a_subset_refuses_the_rest_and_shares_everything_else(tmp_path):
    from coursekit.providers import ToolCall
    s = _session(tmp_path / "calls.jsonl")
    eu_only = s.offering([_SCHEMAS["add_open_response_variant"]])
    out = eu_only.run_tool_calls([ToolCall(id="1", name="create_question_group", arguments=json.dumps(
        {"group_id": "x", "concept_title": "X", "question_type": "matching"}))])
    assert out[0][1] == "ERROR: no tool named 'create_question_group'. Available: add_open_response_variant"
    assert s.draft.bank.groups == {}                                        # refused, so nothing ran
    assert eu_only.draft is s.draft and list(s.registry) == list(TOOL_REGISTRY)   # same draft; s unchanged
    assert len((tmp_path / "calls.jsonl").read_text().splitlines()) == 1    # still logged, for replay
