import json
import pytest
from coursekit.providers import OpenAICompatProvider
from coursekit.discover import find_units
from coursekit.pipeline import run_course, run_unit


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


class _ScriptedRaw:
    """A scripted OpenAI-shaped endpoint. A new conversation is detected by the message list
    being back to just system+user, so it works across multiple run_unit calls."""

    def __init__(self, script=SCRIPT):
        self._script = script
        self._i = 0
        self.chat = self
        self.completions = self
        self.calls = 0
        self.first_messages = None   # the prompts as actually sent

    def create(self, **kwargs):
        self.calls += 1
        if self.first_messages is None:
            self.first_messages = kwargs["messages"]
        if len(kwargs["messages"]) == 2:  # fresh conversation
            self._i = 0
        turn = self._script[self._i]
        self._i += 1
        tcs = [_ToolCall(n, a) for n, a in turn]
        return _Response(_Choice(_Message(content=None, tool_calls=tcs), "tool_calls"))


def FakeClient(script=SCRIPT):
    """A real coursekit Provider over a scripted endpoint — so tests exercise the actual
    provider code, not a stand-in for it."""
    raw = _ScriptedRaw(script)
    p = OpenAICompatProvider(client=raw, name="fake")
    p.calls = raw.calls  # placeholder; see _calls() helper
    p._raw = raw
    return p


def _calls(provider):
    return provider._raw.calls


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

    results = run_course(tmp_path, provider=FakeClient(), model="fake")

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
    results = run_course(tmp_path, provider=client, model="fake", dry_run=True)

    assert len(results) == 2
    assert _calls(client) == 0
    assert all(not r.finalized for r in results)
    for r in results:
        assert not r.output_dir.exists()  # nothing written


# ---------------------------------------------------------- weeks filter

def test_weeks_filter_selects_matching_units(tmp_path):
    for n in (3, 4, 5):
        (tmp_path / f"week {n}").mkdir()
        (tmp_path / f"week {n}" / f"week-{n}.md").write_text(f"t{n}", encoding="utf-8")

    results = run_course(tmp_path, weeks=["4"], provider=FakeClient(script=[]),
                         model="fake", dry_run=True)
    assert [r.unit.week_slug for r in results] == ["week-4"]


@pytest.mark.parametrize("ref", ["3", "week-3", "week 3", 3])
def test_week_filter_accepts_various_references(tmp_path, ref):
    (tmp_path / "week 3").mkdir()
    (tmp_path / "week 3" / "week-3.md").write_text("t3", encoding="utf-8")
    results = run_course(tmp_path, weeks=[ref], provider=FakeClient(script=[]),
                         model="fake", dry_run=True)
    assert len(results) == 1


# ------------------------------------------------- loop hardening

from coursekit.generate.quiz import bank as bankmod
from coursekit.generate.quiz import tools as toolsmod
from coursekit.pipeline import loop


class _ScriptedRawResponses:
    """Yields canned responses in order. With repeat_last, the final response repeats
    forever — for simulating a model that never recovers."""

    def __init__(self, responses, repeat_last=False):
        self._responses = list(responses)
        self._repeat_last = repeat_last
        self._last = None
        self.chat = self
        self.completions = self
        self.calls = 0

    def create(self, **kwargs):
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


def ScriptedClient(responses, repeat_last=False):
    """The scripted endpoint behind a real Provider."""
    raw = _ScriptedRawResponses(responses, repeat_last)
    p = OpenAICompatProvider(client=raw, name="scripted")
    p._raw = raw
    return p


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
    assert _calls(client) == 2
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
    assert _calls(client) < 80  # bailed early, did not grind to the cap


def test_gives_up_when_model_never_calls_tools(fresh_bank):
    # Week 10 mode: model just stops, repeatedly. Must terminate within the nudge budget.
    client = ScriptedClient([("stop", "nope")], repeat_last=True)
    messages = _msgs()
    loop(messages, client, "m", max_iters=80, max_nudges=3, stall_limit=4)
    assert not bankmod.is_finalized()
    assert _calls(client) <= 5  # initial + 3 nudges + the terminating check


def test_nudge_reports_real_bank_state(fresh_bank):
    # After building one group then stopping, the nudge should quote the true counts.
    client = ScriptedClient([("tools", BUILD), ("stop", "done?"), ("tools", FINALIZE)])
    messages = _msgs()
    loop(messages, client, "m")
    nudges = _nudged(messages)
    assert nudges
    assert "1 group(s), 1 variant(s)" in nudges[0]["content"]


# ------------------------------------------------- model-load errors

from coursekit.pipeline import ModelLoadError, _looks_like_model_error


class _RaisingRaw:
    def __init__(self, exc):
        self._exc = exc
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        raise self._exc


def RaisingClient(exc):
    return OpenAICompatProvider(client=_RaisingRaw(exc), name="raising")


def test_looks_like_model_error_matches_lmstudio_message():
    exc = Exception('Failed to load model "x". Error: insufficient system resources')
    assert _looks_like_model_error(exc)


def test_looks_like_model_error_ignores_unrelated():
    assert not _looks_like_model_error(ValueError("something else entirely"))


def test_loop_translates_model_load_failure(fresh_bank, monkeypatch):
    exc = Exception('Failed to load model "big". Error: insufficient system resources')
    client = RaisingClient(exc)
    # Stub the provider's own fit check so the message build doesn't shell out to `lms`.
    monkeypatch.setattr(client, "check_fit", lambda m: (False, "won't fit"))
    with pytest.raises(ModelLoadError) as ei:
        loop(_msgs(), client, "big")
    text = str(ei.value)
    assert "Could not use model 'big'" in text
    assert "won't fit" in text          # the fit advisory is folded into the error
    assert "Fix:" in text


def test_loop_reraises_non_model_errors(fresh_bank):
    client = RaisingClient(ValueError("bad json in a tool, unrelated"))
    with pytest.raises(ValueError):
        loop(_msgs(), client, "m")


def test_looks_like_timeout_matches_timeouts_only():
    from coursekit.pipeline import _looks_like_timeout
    assert _looks_like_timeout(TimeoutError("Request timed out."))
    assert _looks_like_timeout(Exception("httpx.ReadTimeout: timed out"))
    assert not _looks_like_timeout(ValueError("bad json, unrelated"))
    assert not _looks_like_timeout(Exception("Failed to load model"))   # a LOAD error, not a timeout


def test_loop_ends_cleanly_on_a_timeout(fresh_bank):
    # A request timeout is transient + per-unit: the loop ends cleanly (no raw traceback), leaving the
    # artifact unfinalized — so a batch / --source loop moves on. The generate-side of OPS-6/7.
    from coursekit.generate.quiz import bank as bankmod
    client = RaisingClient(TimeoutError("Request timed out."))
    out = loop(_msgs(), client, "m")
    assert out == "" and not bankmod.is_finalized()


class _APIConnectionError(Exception):
    """Mimics openai.APIConnectionError by name — a DOWN endpoint, not a slow one."""


def test_looks_like_unreachable_matches_down_endpoints_not_slow_ones():
    from coursekit.pipeline import _looks_like_timeout, _looks_like_unreachable
    assert _looks_like_unreachable(_APIConnectionError("Connection error."))
    assert _looks_like_unreachable(ConnectionRefusedError("[Errno 61] Connection refused"))
    assert not _looks_like_unreachable(TimeoutError("Request timed out."))   # slow, not down
    # a bare 'Connection error.' is a down server now, NOT a per-unit timeout (reclassified so a
    # dead endpoint aborts the batch instead of marking every unit INCOMPLETE)
    assert not _looks_like_timeout(_APIConnectionError("Connection error."))


def test_loop_aborts_the_batch_on_an_unreachable_endpoint(fresh_bank):
    # A down endpoint fails every unit identically → abort with a clear message, not N misleading
    # per-unit 'timed out's. ModelLoadError propagates out of run_course → the CLI exits 2.
    client = RaisingClient(_APIConnectionError("Connection error."))
    with pytest.raises(ModelLoadError) as ei:
        loop(_msgs(), client, "m")
    assert "Could not reach the model endpoint" in str(ei.value)


def test_stop_turn_is_reappended_as_a_plain_dict_not_the_native_message(fresh_bank):
    """Pins a subtle, easily-'cleaned-up' decision in loop().

    On the stop-then-nudge path the loop deliberately builds a fresh Reply *without*
    raw_message, so the provider synthesises a plain assistant dict. Passing the original
    reply instead would re-append the native message — which carries tool_calls=None and is
    rejected by some servers. Simplifying that line would silently reintroduce the bug.
    """
    client = ScriptedClient([("stop", "<tool_call|>"),
                             ("tools", BUILD),
                             ("tools", FINALIZE)])
    messages = _msgs()
    loop(messages, client, "m")

    assistants = [m for m in messages if isinstance(m, dict) and m.get("role") == "assistant"]
    assert assistants, "the stopped turn must stay in context"
    for m in assistants:
        assert set(m) == {"role", "content"}      # a plain dict…
        assert isinstance(m["content"], str)       # …never a null content
        assert "tool_calls" not in m


def test_nudge_is_appended_as_content_not_a_nested_message(fresh_bank):
    """_nudge() returns text; the provider wraps it. Returning a dict would nest a message
    inside a message — the bug this refactor actually introduced once."""
    client = ScriptedClient([("stop", "stopped"), ("tools", BUILD), ("tools", FINALIZE)])
    messages = _msgs()
    loop(messages, client, "m")

    for m in _nudged(messages):
        assert isinstance(m["content"], str)


# ------------------------------------------- per-course prompt overrides

def _course_with_transcript(tmp_path, *, override=None, quiz_yaml=None, override_name="task"):
    """A course tree with a .vtconfig marker, so discover sets course_root.

    override      body of a prompt file dropped at .vtconfig/prompts/quiz/<override_name>.md
    quiz_yaml     raw text for .vtconfig/quiz.yaml (quizbot's own config)
    """
    root = tmp_path / "a course"
    (root / ".vtconfig").mkdir(parents=True)
    f = root / "output" / "week-3.md"
    f.parent.mkdir(parents=True)
    f.write_text("a transcript", encoding="utf-8")
    if override:
        d = root / ".vtconfig" / "prompts" / "quiz"
        d.mkdir(parents=True)
        (d / f"{override_name}.md").write_text(override, encoding="utf-8")
    if quiz_yaml:
        (root / ".vtconfig" / "quiz.yaml").write_text(quiz_yaml, encoding="utf-8")
    return find_units(f)[0]


def test_run_unit_honours_a_courses_prompt_override(tmp_path):
    """Regression: run_unit built messages without project_root, so the override mechanism
    existed but nothing in the CLI could reach it."""
    unit = _course_with_transcript(tmp_path, override="ONLY-TRUE-FALSE-BRIEF")
    provider = FakeClient()

    run_unit(unit, provider, "fake-model")

    sent = provider._raw.first_messages
    assert "ONLY-TRUE-FALSE-BRIEF" in sent[1]["content"]


def test_run_unit_uses_shipped_prompts_when_a_course_overrides_nothing(tmp_path):
    unit = _course_with_transcript(tmp_path)
    provider = FakeClient()

    run_unit(unit, provider, "fake-model")

    sent = provider._raw.first_messages
    assert "Start by calling create_checklist." in sent[1]["content"]
    assert "THE ONLY WAY TO RECORD A QUESTION IS A TOOL CALL." in sent[0]["content"]


# ----------------------------- quiz.yaml selects a named prompt (step 3)

def test_quiz_yaml_selects_a_named_task_prompt(tmp_path):
    """The capability courseconfig exists to deliver: a course names its brief in quiz.yaml,
    with no CLI flag and no code edit."""
    unit = _course_with_transcript(
        tmp_path,
        quiz_yaml="task_prompt: exam\n",
        override="EXAM-STYLE BRIEF", override_name="exam",
    )
    provider = FakeClient()

    run_unit(unit, provider, "fake-model")

    sent = provider._raw.first_messages
    assert "EXAM-STYLE BRIEF" in sent[1]["content"]


def test_quiz_yaml_absent_falls_back_to_shipped_prompts(tmp_path):
    # No quiz.yaml: system_prompt/task_prompt resolve to the shipped system.md/task.md,
    # NOT to a nonexistent default.md.
    unit = _course_with_transcript(tmp_path)  # marker, no quiz.yaml
    provider = FakeClient()

    run_unit(unit, provider, "fake-model")  # would raise PromptNotFound on the default.md bug

    sent = provider._raw.first_messages
    assert "Start by calling create_checklist." in sent[1]["content"]


# --------------------------- week filter: non-numeric refs match by slug

def _filter(path, week, tmp):
    return run_course(path, weeks=[week], provider=FakeClient(script=[]),
                      model="fake", dry_run=True)


def test_non_numeric_week_filter_matches_by_slug_not_by_none(tmp_path):
    # A single-file input yields a non-numeric slug. week_key returns None for it, so the
    # matcher must compare slugs literally — not let None == None match anything numeric-less.
    f = tmp_path / "intro.md"
    f.write_text("body", encoding="utf-8")

    assert len(_filter(f, "intro", tmp_path)) == 1       # slug matches
    assert len(_filter(f, "syllabus", tmp_path)) == 0     # different slug: no match
    assert len(_filter(f, "3", tmp_path)) == 0            # numeric ref vs non-numeric unit: no match


# ------------------------------- the driver is generator-agnostic (the seam)

class _FakeGenerator:
    """A generator with nothing to do with quizzes — proves the driver drives the protocol,
    not the quiz modules. Finalizes after a single tool turn."""
    category = "fake"

    def __init__(self):
        self._final = False
        self.reset_called = False

    def reset(self, unit, out_dir):
        self.reset_called = True
        self._final = False

    def tool_specs(self):
        return [{"type": "function", "function": {"name": "commit", "parameters": {}}}]

    def run_tool_calls(self, calls):
        self._final = True
        return [(c.id, "OK committed") for c in calls]

    def build_messages(self, unit, transcript, cfg):
        return [{"role": "user", "content": "go"}]

    def is_finalized(self):
        return self._final

    def nudge(self, *, stalled):
        return "keep going"

    def result(self, unit, out_dir, reply):
        from coursekit.generate.base import RunResult
        return RunResult(unit=unit, finalized=self._final, output_dir=out_dir,
                         counts={"blocks": 3}, reply=reply)


def test_run_unit_drives_an_arbitrary_generator(tmp_path):
    f = tmp_path / "week-3.md"
    f.write_text("a transcript", encoding="utf-8")
    unit = find_units(f)[0]
    gen = _FakeGenerator()
    client = ScriptedClient([("tools", [("commit", {})])])

    res = run_unit(unit, client, "m", gen)

    assert gen.reset_called                       # the driver reset per-unit state
    assert res.finalized                          # …drove tools to the generator's finalized
    assert res.counts == {"blocks": 3}            # …and reported the generator's own counts
    assert (unit.output_dir / "reply.txt").exists()  # generic artifact write, no quiz code


def test_default_generator_is_quiz(tmp_path):
    # Omitting the generator must keep driving quizzes (back-compat for every existing caller).
    f = tmp_path / "week-3.md"
    f.write_text("a transcript", encoding="utf-8")
    unit = find_units(f)[0]
    res = run_unit(unit, FakeClient(), "fake-model")   # no generator passed
    assert res.n_groups == 1 and res.n_variants == 1
