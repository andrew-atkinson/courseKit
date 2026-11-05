"""The deterministic enduring-understanding pass (ASMT-3).

`eu_question: true` is a DECISION, not a request: there IS an open-response transfer task for the
week's enduring understanding. So the PROGRAM creates that group and fixes its type to
`open_response`; the model's only job is the CONTENT (the prompt + criteria), and its tool menu here
is exactly one tool — `add_open_response_variant` — so it CANNOT reach for short_answer or any other
type. That moves the type decision out of the model's monolithic generation loop, where it slipped
(the model wrote a good prompt but recorded it as a short-answer with a rubric-description "answer").
"""

from coursekit import outcomes, prompts
from coursekit.generate.quiz import bank, tools
from coursekit.outcomes import CoursekitError

_EU_GID = "enduring_understanding"
_EU_SPEC = [s for s in tools.TOOL_SPECS if s["name"] == "add_open_response_variant"]


class _EUGenerator:
    """A one-tool generator for the EU pass — the model can ONLY add the open-response variant, so
    the question type is the program's decision, not the model's."""

    def __init__(self, session):
        self.session = session
        self.offered = session.offering(_EU_SPEC)    # the model can call only the tool it is shown

    def tool_specs(self):
        return _EU_SPEC

    def run_tool_calls(self, calls):
        return self.offered.run_tool_calls(calls)

    def is_finalized(self) -> bool:
        g = self.session.draft.bank.groups.get(_EU_GID)
        return bool(g and g.variants)

    def nudge(self, *, stalled: bool) -> str:
        return ('Record the transfer task now: call add_open_response_variant with group_id '
                f'"{_EU_GID}", label "A", a question_text, and rubric_criteria. No other tool, no prose.')


def generate_eu_question(session, provider, model, material: str, eu: str, project_root=None) -> bool:
    """Create the open-response EU group deterministically, then have the model fill ONLY its content.
    Returns True if the variant was recorded; leaves the bank exactly as it was on failure."""
    from coursekit.pipeline import loop      # local: avoid an import cycle (pipeline drives generators)
    draft = session.draft
    draft.bank.groups.pop(_EU_GID, None)     # idempotent: a re-run replaces any prior EU question
    draft.create_group(_EU_GID, "Enduring Understanding", "open_response")
    system = prompts.load("quiz", "eu_question", project_root=project_root).body
    user = (f"The enduring understanding to assess:\n{eu}\n\n"
            f"The week's material:\n<material>\n{material}\n</material>\n\nWrite the transfer task now.")
    try:
        loop([{"role": "system", "content": system}, {"role": "user", "content": user}],
             provider, model, _EUGenerator(session), max_iters=6)
    except CoursekitError:
        raise                                  # infrastructure (a model that won't load) aborts the run
    except Exception as e:                     # anything else: recorded, the finished quiz kept
        outcomes.warn("eu.pass_error", f"  EU pass failed: {type(e).__name__}: {e}", error_type=type(e).__name__)
    finally:
        g = draft.bank.groups.get(_EU_GID)
        if not (g and g.variants):             # never leave an empty EU group behind
            draft.bank.groups.pop(_EU_GID, None)
    return bool(g and g.variants)


def main() -> int:
    """Generate ONLY the enduring-understanding question and add it to a week's quiz in place —
    without regenerating the whole bank (one focused model call, not the hour-long full run).

        uv run python -m coursekit.generate.quiz.eu "/path/to/course" --week 3
    """
    import argparse
    import os
    from pathlib import Path

    from coursekit import courseconfig
    from coursekit.discover import find_units
    from coursekit.generate.page.concept_map import load_for_unit

    ap = argparse.ArgumentParser(description="Generate just the enduring-understanding open-response "
                                             "question and add it to a week's quiz (no full regen).")
    ap.add_argument("course")
    ap.add_argument("--week", required=True, help="week number (e.g. 3) or label")
    args = ap.parse_args()

    units = [u for u in find_units(args.course)
             if u.week_slug.split("-")[-1] == args.week or u.week_label == args.week]
    if not units:
        print(f"No unit for week {args.week!r} under {args.course}.")
        return 1
    unit = units[0]

    cm = load_for_unit(unit)
    eu = cm.enduring_understanding if cm is not None else ""
    if not eu:
        print(f"Week {args.week} has no enduring understanding in its concept map — run analyze first.")
        return 1

    out_dir = Path(unit.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bank_path = out_dir / "bank.json"
    if bank_path.exists():
        draft = bank.BankDraft.adopt(bank.Bank.model_validate_json(bank_path.read_text(encoding="utf-8")), out_dir)
        print(f"Adding the EU question to the existing quiz at {bank_path}")
    else:
        draft = bank.BankDraft.new(f"{unit.course_slug}-{unit.week_slug}", out_dir,
                                   title=unit.week_label, source=unit.transcript_path.name)
        print(f"No existing bank — writing an EU-only bank to {out_dir}")

    session = tools.QuizTools(draft, call_log=out_dir / "calls.jsonl")

    from coursekit.cli import _build_provider
    provider = _build_provider()
    model = os.getenv("MODEL_NAME") or courseconfig.load(
        args.course, config_name="quiz.yaml").value("model")

    transcript = Path(unit.transcript_path).read_text(encoding="utf-8", errors="replace")
    if generate_eu_question(session, provider, model, transcript, eu, unit.course_root):
        print(draft.finalize())
        return 0
    print("The EU pass produced no question (model unreachable or refused).")
    return 1


if __name__ == "__main__":
    from coursekit.console import run
    raise SystemExit(run(main))
