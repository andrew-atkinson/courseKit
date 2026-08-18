"""Targeted quizzes (ASMT-17) — a quiz scoped to ONE document, not the whole week.

The quiz engine is material-agnostic (text → `bank.json`), so a targeted quiz is a SCOPING job, not a
new generator: extract one source (a reading / slide deck / PDF / `.md`), give it a DISTINCT output
slug so several quizzes can live under one week without colliding, and run the ordinary quiz generator
on it. The course's `domain.md` / voice / `quiz.yaml` still apply — they resolve from the source's
`.vtconfig` root, exactly as for a whole-week run.

    coursekit generate <course> --quizzes --source "<course>/week-3/readings/Barrett.pdf"
    → quizzes/week-3-barrett/{source.md, bank.json, bank.gift, quiz.json}
"""

from pathlib import Path

from coursekit import courseconfig
from coursekit.discover import Unit, slugify
from coursekit.ingest.extract import SUPPORTED_SUFFIXES, extract_text, is_supported


def _week_from_path(source: Path) -> str | None:
    """The week number from a `week-N` ancestor directory, if any — so the output slug carries it."""
    for p in source.parents:
        k = courseconfig.week_key(p.name)
        if k:
            return k
    return None


def targeted_slug(source: Path) -> str:
    """A distinct output slug for a targeted quiz: `week-<n>-<doc>` (or just `<doc>` off-week). Distinct
    from the plain `week-<n>` so a targeted quiz never overwrites the week quiz or another element's."""
    wk = _week_from_path(source)
    doc = slugify(source.stem)
    return f"week-{wk}-{doc}" if wk else doc


def generate_targeted_quiz(source, provider, model, *, output_root=None, max_iters=None):
    """Generate ONE quiz from a single document; returns the `RunResult`. Extracts the source's text,
    persists it + `bank.json`/GIFT to `quizzes/<slug>/` under the course (or `output_root`), and drives
    the standard quiz generator over it."""
    from coursekit import pipeline
    from coursekit.generate.quiz.generator import QuizGenerator

    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"no such file: {source}")
    if not is_supported(source):
        raise SystemExit(f"unsupported source '{source.name}' — need one of "
                         f"{', '.join(sorted(SUPPORTED_SUFFIXES))}")
    text = extract_text(source)

    cfg = courseconfig.load(source, config_name="quiz.yaml")     # domain.md / voice / quiz.yaml from here
    root = cfg.root
    slug = targeted_slug(source)
    base = Path(output_root).expanduser().resolve() if output_root else (root or source.parent)
    out_dir = base / "quizzes" / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # The engine reads a transcript FILE, so persist the extracted text beside the quiz — also a record
    # of exactly what was quizzed. Re-running overwrites it.
    material = out_dir / "source.md"
    material.write_text(text, encoding="utf-8")

    course_slug = slugify(cfg.course_title or (root.name if root else source.parent.name))
    unit = Unit(transcript_path=material, week_slug=slug, output_dir=out_dir,
                course_slug=course_slug, week_label=source.stem,
                course_title=cfg.course_title, module=None, course_root=root, config=cfg)
    kw = {} if max_iters is None else {"max_iters": max_iters}
    return pipeline.run_unit(unit, provider, model, QuizGenerator(), **kw)
