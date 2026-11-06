"""The quiz introduction (SHIP-10): a few sentences, in the instructor's voice, that tell a student what
the unit was about and why the quiz is worth taking — the opening of the Canvas quiz description.

One plain model call, no tools (the overview framing is the precedent). The model sees only the unit's
title, the topics, the big idea, and whether there is an open question — never a file name — and it
writes no numbers: the grading line under it is the program's (emit/qti.py), so the points are always
right. Optional: a failed or unusable reply leaves no intro (the export's default stands in) and a
warning, and the quiz itself is untouched.
"""

import re

from coursekit import courseconfig, outcomes, prompts

# What a student must never be pointed at: links, and the files the course is built from.
_UNUSABLE = re.compile(r"https?:|://|\b[\w-]+\.(?:md|json|ya?ml|txt|pdf|gift|zip|vtt|srt)\b", re.I)


def unit_facts(bank, eu: str) -> str:
    """The model's whole view of the quiz: what it covers and its shape, with no counts and no files."""
    topics = [g.concept_title for g in bank.groups.values() if g.question_type != "open_response"]
    open_q = any(g.question_type == "open_response" for g in bank.groups.values())
    shape = "short questions" + (", then one open question answered in writing" if open_q else "")
    return (f"Unit: {bank.title}\nTopics: {', '.join(topics) or '(not listed)'}\n"
            f"Big idea: {eu or '(none stated)'}\nThe quiz: {shape}")


def write_intro(draft, provider, model, eu: str, *, domain: str = "", voice: str = "",
                project_root=None) -> bool:
    """Ask the model for the intro and keep it on the bank. Returns True when one was kept."""
    system = (courseconfig.domain_preface(domain) + courseconfig.voice_preface(voice)
              + prompts.load("quiz", "intro", project_root=project_root).body)
    try:
        text = provider.chat(model=model, temperature=0.4, messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": unit_facts(draft.bank, eu)}]).strip()
    except Exception as e:                       # optional: the default intro stands in, but say so
        outcomes.warn("quiz.intro_failed", f"  quiz intro skipped ({type(e).__name__}: {e}) — "
                                           "the export uses its default intro.", error_type=type(e).__name__)
        return False
    if not text or _UNUSABLE.search(text):
        outcomes.warn("quiz.intro_rejected", "  quiz intro not kept (empty, or it named a link or a file) — "
                                             "the export uses its default intro.", reply=text[:200])
        return False
    draft.bank.intro = text
    return True


def main() -> int:
    """Write ONLY the introduction for a week's existing quiz, in place — no regeneration.

        uv run python -m coursekit.generate.quiz.intro "/path/to/course" --week 7
    """
    import argparse
    import os
    from pathlib import Path

    from coursekit.cli import _build_provider
    from coursekit.discover import find_units
    from coursekit.generate.page.concept_map import load_for_unit
    from coursekit.generate.quiz import bank

    ap = argparse.ArgumentParser(description="Write the student-facing introduction for a week's existing "
                                             "quiz (no regeneration).")
    ap.add_argument("course")
    ap.add_argument("--week", required=True, help="week number (e.g. 7) or label")
    args = ap.parse_args()

    units = [u for u in find_units(args.course)
             if u.week_slug.split("-")[-1] == args.week or u.week_label == args.week]
    if not units:
        print(f"No unit for week {args.week!r} under {args.course}.")
        return 1
    unit = units[0]
    bank_path = Path(unit.output_dir) / "bank.json"
    if not bank_path.exists():
        print(f"No quiz at {bank_path} — generate it first.")
        return 1

    draft = bank.BankDraft.adopt(bank.Bank.model_validate_json(bank_path.read_text(encoding="utf-8")),
                                 Path(unit.output_dir))
    cfg = courseconfig.load(unit.transcript_path, config_name="quiz.yaml")
    cm = load_for_unit(unit)
    model = os.getenv("MODEL_NAME") or cfg.value("model")
    if not write_intro(draft, _build_provider(), model, cm.enduring_understanding if cm else "",
                       domain=cfg.domain, voice=cfg.voice, project_root=unit.course_root):
        print("No introduction was written (see the warning above).")
        return 1
    print(draft.finalize())
    print(f"\n{draft.bank.intro}")
    return 0


if __name__ == "__main__":
    from coursekit.console import run
    raise SystemExit(run(main))
