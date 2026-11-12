"""Targeted quizzes (ASMT-17) — a quiz scoped to ONE document, not the whole week.

The quiz engine is material-agnostic (text → `bank.json`), so a targeted quiz is a SCOPING job, not a
new generator: extract one source (a reading / slide deck / PDF / `.md`), give it a DISTINCT output
slug so several quizzes can live under one week without colliding, and run the ordinary quiz generator
on it. The course's `domain.md` / voice / `quiz.yaml` still apply — they resolve from the source's
`.vtconfig` root, exactly as for a whole-week run.

    coursekit generate <course> --quizzes --source "<course>/week-3/readings/Barrett.pdf"
    → quizzes/week-3-barrett/{source.md, bank.json, bank.gift, quiz.json}
"""

from dataclasses import replace
from pathlib import Path

from coursekit import atomic, courseconfig, coursestructure, outcomes
from coursekit.course import Course
from coursekit.discover import slugify
from coursekit.ingest.extract import SUPPORTED_SUFFIXES, extract_text, is_supported
from coursekit.ingest.ingest import _week_of
from coursekit.outcomes import CoursekitError


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
    wk = unit_of(source, struct)
    doc = slugify(source.stem)
    return f"week-{wk}-{doc}" if wk else doc


def unit_of(source: Path, struct=None) -> str | None:
    """The unit number a `--source` belongs to: the DECLARED structure first, then the path."""
    wk = _declared_week_of(source, struct) if struct is not None else None
    return wk if wk is not None else _week_of(source)


def prepare(source, *, output_root=None):
    """A single-document quiz's run and its text, writing nothing: the unit the document is filed under,
    scoped to the document (its own slug, label and folder). Shared by the run and by its record's check
    (CORE-4), so the two can't disagree about what the model is shown."""
    from coursekit import records

    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise CoursekitError(f"no such file: {source}", code="source.not_found", category="source",
                             details={"path": str(source)})
    if not is_supported(source):
        raise CoursekitError(f"unsupported source '{source.name}' — need one of "
                             f"{', '.join(sorted(SUPPORTED_SUFFIXES))}", code="source.unsupported",
                             category="source", details={"path": str(source), "allowed": sorted(SUPPORTED_SUFFIXES)})
    records.note(source)
    text = extract_text(source)
    if not text.strip():
        raise CoursekitError(
            f"extracted no text from '{source.name}' — nothing to quiz. If it's a scanned/image PDF it "
            f"has no text layer; OCR it first, or supply a text-based source (.md/.txt/.docx/.pptx). "
            f"(Generating anyway would produce questions from the model's own knowledge, not your "
            f"material — an ungrounded quiz.)",
            code="source.no_text", category="source", details={"path": str(source)})

    cfg = courseconfig.load(source, config_name="quiz.yaml")     # domain.md / voice / quiz.yaml from here
    root = cfg.root
    struct = coursestructure.CourseStructure(cfg)
    slug = targeted_slug(source, struct)                         # declared unit wins, reusing cfg
    base = Path(output_root).expanduser().resolve() if output_root else (root or source.parent)
    out_dir = base / "quizzes" / slug

    # The unit number lets unit-keyed lookups (its concept map's enduring understanding, for
    # `eu_question`) find the unit (ASMT-19 layer 1). The engine reads a transcript FILE, so the run reads
    # the extracted text from `source.md` beside the quiz, which `generate_targeted_quiz` writes.
    wk = unit_of(source, struct)
    with outcomes.capture(sink=lambda n: None):
        course = Course.load(source.parent)
    unit = replace(course.run_target(course.target_unit(wk or slug)), transcript_path=out_dir / "source.md",
                   week_slug=slug, output_dir=out_dir, week_label=source.stem, week_num=wk, module=None)
    return unit, text


def generate_targeted_quiz(source, provider, model, *, output_root=None, max_iters=None, force=False):
    """Generate ONE quiz from a single document; returns the `RunResult`. Extracts the source's text,
    persists it + `bank.json`/GIFT to `quizzes/<slug>/` under the course (or `output_root`), and drives
    the standard quiz generator over it."""
    from coursekit import pipeline, records
    from coursekit.generate.quiz.generator import QuizGenerator

    unit, text = prepare(source, output_root=output_root)
    records.refuse_edited([unit.output_dir], force=force)
    # Persist the extracted text beside the quiz — also a record of exactly what was quizzed. Re-running
    # overwrites it. The quiz's SHAPE stays the document's own: concept_shape=False keeps the unit's
    # concept list out of a single reading's brief.
    atomic.write(unit.transcript_path, text)
    kw = {} if max_iters is None else {"max_iters": max_iters}
    return pipeline.run_unit(unit, provider, model,
                             QuizGenerator(concept_shape=False, source=Path(source).expanduser().resolve()), **kw)
