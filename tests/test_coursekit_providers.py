import pytest

from coursekit.providers import (OpenAICompatProvider, Reply, ToolCall, get_provider,
                                 provider_names)


# ------------------------------------------------------------- fake endpoint

class _Fn:
    def __init__(self, name, arguments):
        self.name, self.arguments = name, arguments


class _RawToolCall:
    def __init__(self, name, arguments, id="call_1"):
        self.function, self.id = _Fn(name, arguments), id


class _RawMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content, self.tool_calls = content, tool_calls


class _Choice:
    def __init__(self, message, finish_reason):
        self.message, self.finish_reason = message, finish_reason


class _Response:
    def __init__(self, choice):
        self.choices = [choice]


class FakeClient:
    """Records the kwargs it was called with, so we can assert on the wire request."""

    def __init__(self, message=None, finish_reason="tool_calls"):
        self._message = message or _RawMessage(tool_calls=[_RawToolCall("do_thing", '{"a":1}')])
        self._finish = finish_reason
        self.last_kwargs = None
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _Response(_Choice(self._message, self._finish))


SPEC = {"name": "do_thing", "description": "does a thing",
        "parameters": {"type": "object", "properties": {}, "required": []}}


def _provider(client):
    return OpenAICompatProvider(client=client, name="fake")


# ------------------------------------------------------------- tool specs

def test_neutral_tool_spec_is_wrapped_for_the_wire():
    c = FakeClient()
    _provider(c).chat_with_tools(model="m", messages=[], tools=[SPEC])
    assert c.last_kwargs["tools"] == [{"type": "function", "function": SPEC}]


def test_already_wrapped_spec_passes_through():
    # A caller mid-migration may still hold OpenAI-shaped specs.
    c = FakeClient()
    wrapped = {"type": "function", "function": SPEC}
    _provider(c).chat_with_tools(model="m", messages=[], tools=[wrapped])
    assert c.last_kwargs["tools"] == [wrapped]


# ------------------------------------------------- request stays minimal

def test_temperature_and_max_tokens_omitted_unless_asked():
    # Sending an unrequested temperature would change model behaviour and break the
    # byte-identical check the quizbot migration depends on.
    c = FakeClient()
    _provider(c).chat_with_tools(model="m", messages=[], tools=[SPEC])
    assert "temperature" not in c.last_kwargs
    assert "max_tokens" not in c.last_kwargs


def test_temperature_and_max_tokens_sent_when_given():
    c = FakeClient()
    _provider(c).chat_with_tools(model="m", messages=[], tools=[SPEC],
                                 temperature=0.2, max_tokens=100)
    assert c.last_kwargs["temperature"] == 0.2
    assert c.last_kwargs["max_tokens"] == 100


# ------------------------------------------------------------- Reply

def test_tool_calls_are_normalised():
    c = FakeClient(_RawMessage(tool_calls=[_RawToolCall("add", '{"x":1}', id="abc")]))
    reply = _provider(c).chat_with_tools(model="m", messages=[], tools=[SPEC])
    assert reply.wants_tools
    assert reply.tool_calls == [ToolCall(id="abc", name="add", arguments='{"x":1}')]


def test_malformed_arguments_are_passed_through_not_parsed():
    # Parsing here would turn the model's mistake into the provider's exception; the caller
    # needs the raw string so it can report it back as an actionable message.
    c = FakeClient(_RawMessage(tool_calls=[_RawToolCall("add", "{not json,,}")]))
    reply = _provider(c).chat_with_tools(model="m", messages=[], tools=[SPEC])
    assert reply.tool_calls[0].arguments == "{not json,,}"


def test_empty_arguments_normalise_to_empty_string():
    # LM Studio sends arguments=None for zero-arg tools; downstream expects a string.
    c = FakeClient(_RawMessage(tool_calls=[_RawToolCall("report", None)]))
    reply = _provider(c).chat_with_tools(model="m", messages=[], tools=[SPEC])
    assert reply.tool_calls[0].arguments == ""


def test_stop_turn_carries_content_and_no_calls():
    c = FakeClient(_RawMessage(content="all done"), finish_reason="stop")
    reply = _provider(c).chat_with_tools(model="m", messages=[], tools=[SPEC])
    assert not reply.wants_tools
    assert reply.content == "all done"
    assert reply.tool_calls == []


# -------------------------------------------------- conversation shaping

def test_assistant_turn_appends_the_native_message():
    # Must be the native object: the tool messages that follow refer to its tool_call ids.
    c = FakeClient()
    p = _provider(c)
    reply = p.chat_with_tools(model="m", messages=[], tools=[SPEC])
    msgs = []
    p.append_assistant(msgs, reply)
    assert msgs == [reply.raw_message]


def test_assistant_turn_without_a_native_message_is_synthesised():
    p = _provider(FakeClient())
    msgs = []
    p.append_assistant(msgs, Reply(finish_reason="stop", content="  "))
    assert msgs == [{"role": "assistant", "content": "(stopped)"}]  # never a null content


def test_tool_results_are_keyed_by_call_id():
    p = _provider(FakeClient())
    msgs = []
    p.append_tool_results(msgs, [("id1", "OK one"), ("id2", "ERROR two")])
    assert msgs == [
        {"role": "tool", "tool_call_id": "id1", "content": "OK one"},
        {"role": "tool", "tool_call_id": "id2", "content": "ERROR two"},
    ]


def test_user_turn_is_plain():
    p = _provider(FakeClient())
    msgs = []
    p.append_user(msgs, "keep going")
    assert msgs == [{"role": "user", "content": "keep going"}]


def test_a_full_turn_round_trips_into_the_conversation():
    # The exact sequence pipeline.loop performs.
    c = FakeClient()
    p = _provider(c)
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]

    reply = p.chat_with_tools(model="m", messages=messages, tools=[SPEC])
    p.append_assistant(messages, reply)
    p.append_tool_results(messages, [(tc.id, "OK") for tc in reply.tool_calls])

    assert len(messages) == 4
    assert messages[-1]["role"] == "tool"
    assert messages[-1]["tool_call_id"] == reply.tool_calls[0].id


# ------------------------------------------------------------- factory

def test_known_providers():
    assert set(provider_names()) == {"lm_studio", "ollama", "openai"}


def test_factory_builds_local_providers_without_credentials():
    p = get_provider("lm_studio", client=FakeClient())
    assert p.is_local and p.name == "lm_studio"


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError, match="unknown provider"):
        get_provider("telepathy")


def test_openai_requires_a_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="needs an API key"):
        get_provider("openai")


def test_explicit_base_url_overrides_the_preset():
    p = get_provider("lm_studio", base_url="http://elsewhere:9/v1/", client=FakeClient())
    assert isinstance(p, OpenAICompatProvider)
