"""One cold-read critic call, shared by the pedagogy, concept-delivery, and groundedness critics.

A failed call is never a result. `ask` returns the critic's reply, or None when the call failed: a
model that won't load aborts the run (`ModelLoadError`, as in generation), and any other failure is
recorded as a `critic.call_failed` notice. The caller must report a None as NOT JUDGED — never parse
it into a score, a smaller denominator, or a different concept list (CORE-1.5).
"""

from coursekit import outcomes


def ask(provider, model: str, messages: list[dict], *, temperature: float, item: str) -> str | None:
    try:
        return provider.chat(model=model, messages=messages, temperature=temperature)
    except Exception as e:
        from coursekit.pipeline import abort_if_model_error
        abort_if_model_error(provider, model, e)
        outcomes.warn("critic.call_failed", f"  {item}: critic call failed ({type(e).__name__}: {e}) — not judged.",
                      item=item, error_type=type(e).__name__)
        return None
