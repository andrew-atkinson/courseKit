"""The provider contract for structured generation.

The videotranscriber's existing `Provider.chat()` returns a string: prompt in, prose out. That
cannot carry a generator like quizbot, where the model answers with *tool calls* and the caller
must feed the exchange back into the conversation.

The shape of that feedback differs by vendor — OpenAI-compatible APIs want a `tool` role message
keyed by `tool_call_id`; Anthropic wants `tool_result` blocks inside a user turn. So the split is:

    the provider owns conversation shaping   (how a turn is represented)
    the caller owns semantics                (what the tools do, when to stop)

which is why `append_assistant` / `append_tool_results` live here rather than in the driver loop.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation, normalised across providers.

    `arguments` stays a raw string: a local model regularly emits malformed JSON, and parsing it
    here would turn the model's mistake into the provider's exception. The caller parses it and
    reports the failure back to the model as an actionable message.
    """
    id: str
    name: str
    arguments: str


@dataclass
class Reply:
    """A normalised model turn."""
    finish_reason: str                                  # "tool_calls" | "stop" | ...
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_message: Any = None                             # provider-native, for append_assistant

    @property
    def wants_tools(self) -> bool:
        return self.finish_reason == "tool_calls"


class Provider(ABC):
    """A model endpoint that can hold a tool-calling conversation."""

    name: str = ""
    is_local: bool = False

    @abstractmethod
    def chat_with_tools(self, *, model: str, messages: list, tools: list[dict],
                        temperature: float | None = None,
                        max_tokens: int | None = None) -> Reply:
        """One turn. `tools` are neutral specs: {name, description, parameters(JSON Schema)}.

        temperature/max_tokens are omitted from the request when None, so a provider's own
        defaults apply and a migration does not silently change model behaviour.
        """

    @abstractmethod
    def append_assistant(self, messages: list, reply: Reply) -> None:
        """Append the model's turn to the conversation."""

    @abstractmethod
    def append_tool_results(self, messages: list, results: list[tuple[str, str]]) -> None:
        """Append tool output. `results` is [(tool_call_id, content), ...] in call order."""

    def append_user(self, messages: list, text: str) -> None:
        """Append a plain user turn — the same shape everywhere, so not abstract."""
        messages.append({"role": "user", "content": text})

    def chat(self, *, model: str, messages: list, temperature: float | None = None,
             max_tokens: int | None = None) -> str:
        """A plain completion: messages in, assistant text out — no tools. For prose→prose passes
        (e.g. reshaping raw extracted document text into a teaching-ready week doc). Not abstract so
        existing tool-only providers keep working; a provider that can't complete says so loudly."""
        raise NotImplementedError(f"{type(self).__name__} does not implement plain chat()")

    def check_fit(self, model: str) -> tuple[bool | None, str]:
        """Can this endpoint serve the model? -> (verdict, message).

        True/False/None, where None means "can't tell" — which is the honest answer for a
        hosted endpoint, since there is no local RAM budget to measure. Advisory only: the
        authoritative signal is the endpoint actually refusing to load.
        """
        return None, ""
