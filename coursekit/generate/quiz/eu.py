"""The deterministic enduring-understanding pass (ASMT-3).

`eu_question: true` is a DECISION, not a request: there IS an open-response transfer task for the
week's enduring understanding. So the PROGRAM creates that group and fixes its type to
`open_response`; the model's only job is the CONTENT (the prompt + criteria), and its tool menu here
is exactly one tool — `add_open_response_variant` — so it CANNOT reach for short_answer or any other
type. That moves the type decision out of the model's monolithic generation loop, where it slipped
(the model wrote a good prompt but recorded it as a short-answer with a rubric-description "answer").
"""

from coursekit import prompts
from coursekit.generate.quiz import bank, tools

_EU_GID = "enduring_understanding"
_EU_SPEC = [s for s in tools.TOOL_SPECS if s["name"] == "add_open_response_variant"]


class _EUGenerator:
    """A one-tool generator for the EU pass — the model can ONLY add the open-response variant, so
    the question type is the program's decision, not the model's."""

    def tool_specs(self):
        return _EU_SPEC

    def run_tool_calls(self, calls):
        return tools.run_tool_calls(calls)

    def is_finalized(self) -> bool:
        g = bank.get().groups.get(_EU_GID)
        return bool(g and g.variants)

    def nudge(self, *, stalled: bool) -> str:
        return ('Record the transfer task now: call add_open_response_variant with group_id '
                f'"{_EU_GID}", label "A", a question_text, and rubric_criteria. No other tool, no prose.')


def generate_eu_question(provider, model, material: str, eu: str, project_root=None) -> bool:
    """Create the open-response EU group deterministically, then have the model fill ONLY its content.
    Returns True if the variant was recorded; leaves the bank exactly as it was on failure."""
    from coursekit.pipeline import loop      # local: avoid an import cycle (pipeline drives generators)
    bank.create_group(_EU_GID, "Enduring Understanding", "open_response")
    system = prompts.load("quiz", "eu_question", project_root=project_root).body
    user = (f"The enduring understanding to assess:\n{eu}\n\n"
            f"The week's material:\n<material>\n{material}\n</material>\n\nWrite the transfer task now.")
    try:
        loop([{"role": "system", "content": system}, {"role": "user", "content": user}],
             provider, model, _EUGenerator(), max_iters=6)
    except Exception:
        pass
    g = bank.get().groups.get(_EU_GID)
    if g and g.variants:
        return True
    bank.get().groups.pop(_EU_GID, None)       # the pass failed — don't leave an empty group behind
    return False
