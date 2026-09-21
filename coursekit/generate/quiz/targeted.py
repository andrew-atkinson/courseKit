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

from coursekit import courseconfig, coursestructure
from coursekit.discover import Unit, slugify
from coursekit.ingest.extract import SUPPORTED_SUFFIXES, extract_text, is_supported
from coursekit.ingest.ingest import _week_of


def _declared_week_of(source: Path, struct) -> str | None:
    """The week a `--source` belongs to per the DECLARED structure — matched by resolved path, so a
    source the manifest assigns to a week is placed there even when its path doesn't encode the week."""
    src = Path(source).expanduser().resolve()
    for week_num, _ in struct.iter_weeks():
        for s in struct.sources_for(week_num):
            if s.resolve(struct.root).resolve() == src:
                return week_num
    return None


def targeted_slug(source: Path, struct=None) -> str:
    """A distinct output slug for a targeted quiz: `week-<n>-<doc>` (or just `<doc>` off-week). Distinct
    from the plain `week-<n>` so a targeted quiz never overwrites the week quiz or another element's.

    Week detection prefers the DECLARED structure (FLOW-7) — a source the manifest assigns to a week
    uses THAT week — then falls back to ingest's strict `_week_of` ancestor match (which, unlike the old
    loose per-ancestor `week_key`, won't mistake a bare-numeric ancestor like `.../2024/` for a week)."""
    wk = _declared_week_of(source, struct) if struct is not None else None
    if wk is None:
        wk = _week_of(source)
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
    if not text.strip():
        raise SystemExit(
            f"extracted no text from '{source.name}' — nothing to quiz. If it's a scanned/image PDF it "
            f"has no text layer; OCR it first, or supply a text-based source (.md/.txt/.docx/.pptx). "
            f"(Generating anyway would produce questions from the model's own knowledge, not your "
            f"material — an ungrounded quiz.)")

    cfg = courseconfig.load(source, config_name="quiz.yaml")     # domain.md / voice / quiz.yaml from here
    root = cfg.root
    slug = targeted_slug(source, coursestructure.CourseStructure(cfg))   # declared week wins, reusing cfg
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
