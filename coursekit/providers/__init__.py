"""Provider selection.

Kept deliberately thin: a name plus config in, a Provider out. Institutional policy may dictate
which endpoint is allowed (on-prem only, a specific vendor), so that choice belongs in config
rather than in any generator's code.
"""

from .base import Provider, Reply, ToolCall
from .openai_compat import OpenAICompatProvider

# name -> (base_url default, api_key default, is_local)
_PRESETS = {
    "lm_studio": ("http://localhost:1234/v1/", "lmstudio", True),
    "ollama": ("http://localhost:11434/v1/", "ollama", True),
    "openai": (None, None, False),
}


def provider_names() -> list[str]:
    return list(_PRESETS)


def get_provider(name: str = "lm_studio", *, base_url: str | None = None,
                 api_key: str | None = None, client=None) -> Provider:
    """Build a provider by name. Explicit base_url/api_key override the preset."""
    if name not in _PRESETS:
        raise ValueError(f"unknown provider {name!r}. Options: {', '.join(_PRESETS)}")
    preset_url, preset_key, is_local = _PRESETS[name]

    key = api_key or preset_key
    if key is None:
        import os
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError(f"provider {name!r} needs an API key (set OPENAI_API_KEY)")

    return OpenAICompatProvider(base_url=base_url or preset_url, api_key=key,
                                name=name, is_local=is_local, client=client)


__all__ = ["Provider", "Reply", "ToolCall", "OpenAICompatProvider",
           "get_provider", "provider_names"]
