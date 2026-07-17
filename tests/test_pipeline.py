import json

import pytest

from discover import find_units
from pipeline import run_course, run_unit


# ------------------------------------------------------------- fake client

class _Fn:
    def __init__(self, name, arguments):
        self.name, self.arguments = name, arguments


class _ToolCall:
    def __init__(self, name, arguments, id="call"):
        self.function, self.id = _Fn(name, json.dumps(arguments)), id


class _Message:
    def __init__(self, content=None, tool_calls=None):
        self.content, self.tool_calls = content, tool_calls


class _Choice:
    def __init__(self, message, finish_reason):
        self.message, self.finish_reason = message, finish_reason


class _Response:
    def __init__(self, choice):
        self.choices = [choice]


# A canned conversation that builds one valid MC group and finalizes.
SCRIPT = [
    [("create_question_group",
      {"group_id": "c1", "concept_title": "A test concept", "question_type": "multiple_choice"}),
     ("add_multiple_choice_variant",
      {"group_id": "c1", "variant_label": "A", "question_text": "Which is right in the test?",
       "variant_summary": "Angle A", "options": ["a", "b", "c", "d"], "correct_index": 0})],
    [("finalize_bank", {})],
]


class FakeClient:
    """Replays SCRIPT once per conversation. A new conversation is detected by the message
    list being back to just system+user, so it works across multiple run_unit calls."""

    def __init__(self, script=SCRIPT):
        self._script = script
        self._i = 0
        self.chat = self
        self.completions = self
        self.calls = 0

    def create(self, *, model, messages, tools):
        self.calls += 1
        if len(messages) == 2:  # fresh conversation
            self._i = 0
        turn = self._script[self._i]
        self._i += 1
        tcs = [_ToolCall(n, a) for n, a in turn]
        return _Response(_Choice(_Message(content=None, tool_calls=tcs), "tool_calls"))


# ------------------------------------------------------------- run_unit

def test_run_unit_finalizes_and_writes_all_artifacts(tmp_path):
    f = tmp_path / "week-3.md"
    f.write_text("a transcript", encoding="utf-8")
    unit = find_units(f)[0]

    res = run_unit(unit, FakeClient(), "fake-model")

    assert res.finalized
    assert res.n_groups == 1
    assert res.n_variants == 1
    for name in ["bank.json", "quiz.json", "bank.gift", "reply.txt", "calls.jsonl"]:
        assert (unit.output_dir / name).exists(), name


def test_run_unit_writes_under_the_units_output_dir(tmp_path):
    f = tmp_path / "week-3.md"
    f.write_text("a transcript", encoding="utf-8")
    unit = find_units(f)[0]
    run_unit(unit, FakeClient(), "fake-model")
    # Beside the input, never in the app.
    assert unit.output_dir == (tmp_path / "quizzes" / "week-3").resolve()
    saved = json.loads((unit.output_dir / "bank.json").read_text())
    assert list(saved["groups"]) == ["c1"]


# --------------------------------------------------------- no state bleed

def test_two_units_do_not_bleed(tmp_path):
    # Two weeks in one directory → two units, one shared client.
    (tmp_path / "week 3").mkdir()
    (tmp_path / "week 3" / "week-3.md").write_text("t3", encoding="utf-8")
    (tmp_path / "week 4").mkdir()
    (tmp_path / "week 4" / "week-4.md").write_text("t4", encoding="utf-8")

    results = run_course(tmp_path, client=FakeClient(), model="fake")

    assert len(results) == 2
    # Each week sees exactly its own single group — no accumulation from the previous week.
    for r in results:
        assert r.finalized
        assert r.n_groups == 1
        assert r.n_variants == 1
    # And the banks landed in separate directories.
    assert len({r.output_dir for r in results}) == 2


# --------------------------------------------------------------- dry run

def test_dry_run_does_not_touch_the_client_or_disk(tmp_path):
    (tmp_path / "week 3").mkdir()
    (tmp_path / "week 3" / "week-3.md").write_text("t3", encoding="utf-8")
    (tmp_path / "week 4").mkdir()
    (tmp_path / "week 4" / "week-4.md").write_text("t4", encoding="utf-8")

    client = FakeClient(script=[])  # would IndexError if create() were called
    results = run_course(tmp_path, client=client, model="fake", dry_run=True)

    assert len(results) == 2
    assert client.calls == 0
    assert all(not r.finalized for r in results)
    for r in results:
        assert not r.output_dir.exists()  # nothing written


# ---------------------------------------------------------- weeks filter

def test_weeks_filter_selects_matching_units(tmp_path):
    for n in (3, 4, 5):
        (tmp_path / f"week {n}").mkdir()
        (tmp_path / f"week {n}" / f"week-{n}.md").write_text(f"t{n}", encoding="utf-8")

    results = run_course(tmp_path, weeks=["4"], client=FakeClient(script=[]),
                         model="fake", dry_run=True)
    assert [r.unit.week_slug for r in results] == ["week-4"]


@pytest.mark.parametrize("ref", ["3", "week-3", "week 3", 3])
def test_week_filter_accepts_various_references(tmp_path, ref):
    (tmp_path / "week 3").mkdir()
    (tmp_path / "week 3" / "week-3.md").write_text("t3", encoding="utf-8")
    results = run_course(tmp_path, weeks=[ref], client=FakeClient(script=[]),
                         model="fake", dry_run=True)
    assert len(results) == 1


# ------------------------------------------------- loop hardening

import bank as bankmod
import tools as toolsmod
from pipeline import loop


class ScriptedClient:
    """Yields canned responses in order. With repeat_last, the final response repeats
    forever — for simulating a model that never recovers."""

    def __init__(self, responses, repeat_last=False):
        self._responses = list(responses)
        self._repeat_last = repeat_last
        self._last = None
        self.chat = self
        self.completions = self
        self.calls = 0

    def create(self, *, model, messages, tools):
        self.calls += 1
        if self._responses:
            self._last = self._responses.pop(0)
        elif not self._repeat_last:
            raise AssertionError("client called more times than scripted")
        kind, payload = self._last
        if kind == "tools":
            tcs = [_ToolCall(n, a) for n, a in payload]
            return _Response(_Choice(_Message(content=None, tool_calls=tcs), "tool_calls"))
        return _Response(_Choice(_Message(content=payload), "stop"))


# A minimal valid, finalizable bank: one MC group, one variant.
BUILD = [
    ("create_question_group",
     {"group_id": "c1", "concept_title": "A concept", "question_type": "multiple_choice"}),
    ("add_multiple_choice_variant",
     {"group_id": "c1", "variant_label": "A", "question_text": "Which is right here?",
      "variant_summary": "Angle A", "options": ["a", "b", "c", "d"], "correct_index": 0}),
]
FINALIZE = [("finalize_bank", {})]
BAD = ("tools", [("mark_complete", {"index": 9, "completion_notes": "x"})])  # always rejected


@pytest.fixture
def fresh_bank():
    bankmod.init("t", None)
    toolsmod.reset_state()
    yield
    bankmod.reset()
    toolsmod.reset_state()


def _msgs():
    return [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def _nudged(messages):
    return [m for m in messages if isinstance(m, dict)
            and m.get("role") == "user" and "Recorded so far:" in m.get("content", "")]


def test_happy_path_finalizes_with_no_nudges(fresh_bank):
    client = ScriptedClient([("tools", BUILD), ("tools", FINALIZE)])
    messages = _msgs()
    loop(messages, client, "m")
    assert bankmod.is_finalized()
    assert client.calls == 2
    assert _nudged(messages) == []


def test_recovers_from_early_stop(fresh_bank):
    # Week 3/5 mode: a stray token as prose, then it continues after the nudge.
    client = ScriptedClient([
        ("stop", "<tool_call|>"),
        ("tools", BUILD),
        ("tools", FINALIZE),
    ])
    messages = _msgs()
    loop(messages, client, "m")
    assert bankmod.is_finalized()
    assert len(_nudged(messages)) == 1  # exactly one corrective nudge


def test_recovers_from_a_rejection_streak(fresh_bank):
    # Week 4 mode, but the model takes the hint after being nudged.
    client = ScriptedClient([BAD, BAD, BAD, ("tools", BUILD), ("tools", FINALIZE)])
    messages = _msgs()
    loop(messages, client, "m", stall_limit=3)
    assert bankmod.is_finalized()
    assert len(_nudged(messages)) == 1


def test_bails_on_persistent_rejections_without_burning_max_iters(fresh_bank):
    # Week 4 mode, unrecoverable: every call fails forever.
    client = ScriptedClient([BAD], repeat_last=True)
    messages = _msgs()
    loop(messages, client, "m", max_iters=80, max_nudges=2, stall_limit=3)
    assert not bankmod.is_finalized()
    assert client.calls < 80  # bailed early, did not grind to the cap


def test_gives_up_when_model_never_calls_tools(fresh_bank):
    # Week 10 mode: model just stops, repeatedly. Must terminate within the nudge budget.
    client = ScriptedClient([("stop", "nope")], repeat_last=True)
    messages = _msgs()
    loop(messages, client, "m", max_iters=80, max_nudges=3, stall_limit=4)
    assert not bankmod.is_finalized()
    assert client.calls <= 5  # initial + 3 nudges + the terminating check


def test_nudge_reports_real_bank_state(fresh_bank):
    # After building one group then stopping, the nudge should quote the true counts.
    client = ScriptedClient([("tools", BUILD), ("stop", "done?"), ("tools", FINALIZE)])
    messages = _msgs()
    loop(messages, client, "m")
    nudges = _nudged(messages)
    assert nudges
    assert "1 group(s), 1 variant(s)" in nudges[0]["content"]


# ------------------------------------------------- model-load errors

from pipeline import ModelLoadError, _looks_like_model_error


class RaisingClient:
    def __init__(self, exc):
        self._exc = exc
        self.chat = self
        self.completions = self

    def create(self, *, model, messages, tools):
        raise self._exc


def test_looks_like_model_error_matches_lmstudio_message():
    exc = Exception('Failed to load model "x". Error: insufficient system resources')
    assert _looks_like_model_error(exc)


def test_looks_like_model_error_ignores_unrelated():
    assert not _looks_like_model_error(ValueError("something else entirely"))


def test_loop_translates_model_load_failure(fresh_bank, monkeypatch):
    # Don't shell out during the message build.
    monkeypatch.setattr("hardware.check_fit", lambda m: (False, "won't fit"))
    exc = Exception('Failed to load model "big". Error: insufficient system resources')
    client = RaisingClient(exc)
    with pytest.raises(ModelLoadError) as ei:
        loop(_msgs(), client, "big")
    text = str(ei.value)
    assert "could not use model 'big'" in text
    assert "Fix:" in text


def test_loop_reraises_non_model_errors(fresh_bank):
    client = RaisingClient(ValueError("bad json in a tool, unrelated"))
    with pytest.raises(ValueError):
        loop(_msgs(), client, "m")
