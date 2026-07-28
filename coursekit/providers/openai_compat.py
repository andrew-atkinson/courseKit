"""LM Studio, Ollama and OpenAI — one implementation.

All three speak the same tool-calling wire format, so they differ only in base URL, credentials
and whether they run locally. Anthropic does not (its `tool_use` blocks need translation) and
gets its own implementation when needed; the contract in base.py is what makes that possible
without touching callers.
"""

from .base import Provider, Reply, ToolCall


class OpenAICompatProvider(Provider):
    """Any endpoint speaking the OpenAI chat-completions tool format."""

    def __init__(self, base_url: str | None = None, api_key: str = "not-needed",
                 name: str = "openai-compatible", is_local: bool = True, client=None):
        # `client` is injectable so tests never need a live endpoint.
        if client is None:
            from openai import OpenAI
            client = OpenAI(base_url=base_url, api_key=api_key)
        self._client = client
        self.name = name
        self.is_local = is_local

    @staticmethod
    def _wire(spec: dict) -> dict:
        """Neutral {name, description, parameters} -> OpenAI's function envelope.

        Accepts an already-wrapped spec unchanged, so a caller mid-migration can pass either.
        """
        return spec if spec.get("type") == "function" else {"type": "function", "function": spec}

    def chat_with_tools(self, *, model, messages, tools, temperature=None, max_tokens=None):
        kwargs = {"model": model, "messages": messages,
                  "tools": [self._wire(t) for t in tools]}
        # Only send what was asked for: an unrequested temperature would change model behaviour
        # and break the byte-identical check a migration relies on.
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        choice = self._client.chat.completions.create(**kwargs).choices[0]
        calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or "")
            for tc in (choice.message.tool_calls or [])
        ]
        return Reply(finish_reason=choice.finish_reason, content=choice.message.content,
                     tool_calls=calls, raw_message=choice.message)

    def chat(self, *, model, messages, temperature=None, max_tokens=None, seed=None):
        kwargs = {"model": model, "messages": messages}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if seed is not None:
            kwargs["seed"] = seed
        return self._client.chat.completions.create(**kwargs).choices[0].message.content or ""

    def append_assistant(self, messages, reply):
        # Prefer the provider-native object: it carries the tool_calls the following tool
        # messages refer to by id. Fall back to a plain dict when there is no raw message
        # (a synthesised turn), coercing empty content — some servers reject a null.
        if reply.raw_message is not None:
            messages.append(reply.raw_message)
        else:
            messages.append({"role": "assistant", "content": (reply.content or "").strip() or "(stopped)"})

    def append_tool_results(self, messages, results):
        for call_id, content in results:
            messages.append({"role": "tool", "tool_call_id": call_id, "content": content})

    def check_fit(self, model):
        """Local endpoints get a RAM pre-flight; hosted ones have no local budget to check,
        so asking would produce a nonsense warning about the caller's own machine."""
        if not self.is_local:
            return None, ""
        from ..hardware import check_fit
        return check_fit(model)
