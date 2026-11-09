"""A quiz's record (CORE-4.1): which steps made it, and how a check rebuilds each step's brief from today's
files. The steps with a brief are `generate` (the main run), `eu` (the enduring-understanding question),
and `intro`; a `fix` and a `reorder` are provenance only. See coursekit/records.py and
agent/core-4-design.md.

Every rebuild calls the same function the run did — `QuizGenerator.build_messages`, `eu.eu_brief`,
`intro.intro_brief` — so the check and the run can't disagree about what the model is shown.

    uv run python -m coursekit.generate.quiz.record "/path/to/course"     # each quiz's status
"""

import json
from dataclasses import replace
from pathlib import Path

from coursekit import courseconfig, records

OUTPUTS = ("bank.json", "quiz.json")      # what a quiz is; the .gift files are derived from these


def options(unit, *, concept_shape: bool = True, source=None, overrides: dict | None = None) -> dict:
    """What a rebuild needs beyond today's files: the unit's text, and how the run was asked for."""
    opts = {"text": str(Path(unit.transcript_path).resolve())}
    if not concept_shape:
        opts["concept_shape"] = False
    if source is not None:
        opts["source"] = str(Path(source).resolve())
    if overrides:
        opts["overrides"] = overrides
    return opts


def _unit_and_text(opts: dict, art_dir: Path):
    root = records._root(art_dir)
    if "source" in opts:                                   # a single-document quiz: rebuild from the document
        from coursekit.generate.quiz import targeted
        return targeted.prepare(records._resolve(opts["source"], root))
    from coursekit.discover import find_units
    path = records._resolve(opts["text"], root)
    records.note(path)
    (unit,) = find_units(path)                             # the unit whose text this is, as a run finds it
    return unit, path.read_text(encoding="utf-8")


def _cfg(unit, opts: dict):
    cfg = courseconfig.load(unit.transcript_path, config_name="quiz.yaml")
    if opts.get("overrides"):
        cfg = replace(cfg, config={**(cfg.config or {}), **opts["overrides"]})
    return cfg


def _eu(unit) -> str:
    from coursekit.generate.page.concept_map import load_for_unit
    cm = load_for_unit(unit)
    return cm.enduring_understanding if cm is not None else ""


def rebuild(step: dict, art_dir) -> list[dict]:
    """The messages `step` would send today."""
    from coursekit.generate.quiz import eu, intro
    from coursekit.generate.quiz.bank import Bank
    from coursekit.generate.quiz.generator import QuizGenerator

    art_dir, opts = Path(art_dir), step.get("options", {})
    if step["step"] == "intro":
        with records.reading():           # finding the unit isn't part of the intro's brief: don't explain by it
            unit, text = _unit_and_text(opts, art_dir)
    else:
        unit, text = _unit_and_text(opts, art_dir)
    cfg = _cfg(unit, opts)
    if step["step"] == "generate":
        return QuizGenerator(concept_shape=opts.get("concept_shape", True)).build_messages(unit, text, cfg)
    if step["step"] == "eu":
        return eu.eu_brief(text, _eu(unit), unit.course_root)
    if step["step"] == "intro":
        for name in OUTPUTS:
            records.note(art_dir / name)
        bank = Bank.model_validate_json((art_dir / "bank.json").read_text(encoding="utf-8"))
        order = [g["group_id"] for g in json.loads((art_dir / "quiz.json").read_text(encoding="utf-8"))["groups"]]
        return intro.intro_brief(bank, _eu(unit), order, domain=cfg.domain, voice=cfg.voice,
                                 project_root=unit.course_root)
    raise ValueError(f"a quiz has no rebuildable step {step['step']!r}")


def write(art_dir, unit, step: str, *, opts: dict | None = None, model: str | None = None,
          brief: str | None = None, read: dict | None = None, by: str = "model",
          fresh: bool = False, edited: bool = False) -> None:
    """Record one step, after the quiz is written. The EU and intro steps fingerprint their brief by
    rebuilding it here, from the files just written; `generate` passes the digest of what it sent."""
    if brief is None and step in ("eu", "intro"):
        with records.reading() as read:
            brief = records.digest(rebuild({"step": step, "options": opts or {}}, art_dir))
    records.write_step(art_dir, kind="quiz", unit=(unit.week_num or unit.week_slug) if unit else None,
                       step=step, by=by, outputs=OUTPUTS, brief=brief, read=read, model=model,
                       options=opts, fresh=fresh, edited=edited)


def status(art_dir) -> records.Status:
    return records.status(art_dir, lambda rec, step: rebuild(step, art_dir))


def main() -> int:
    import argparse

    from coursekit import outcomes
    from coursekit.course import Course

    ap = argparse.ArgumentParser(description="Show whether each quiz still matches its course (CORE-4).")
    ap.add_argument("course")
    args = ap.parse_args()
    with outcomes.capture(sink=lambda n: None):
        quizzes = Course.load(args.course).artifacts_for(kind="quiz")
    for a in quizzes:
        st = status(a.path.parent)
        print(f"{a.slug:32} {st.state}{' + edited' if st.edited else ''}")
        for r in st.reasons:
            print(f"    {r}")
    return 0


if __name__ == "__main__":
    from coursekit.console import run
    raise SystemExit(run(main))
