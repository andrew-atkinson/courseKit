"""Turn a path into a list of work units.

Decoupled by design: the primary input is a markdown file or a directory of them, so quizbot
works on any file set. If a videotranscriber `.vtconfig/` project root happens to be found by
walking up from the input, its `context.yaml` enriches the unit with course/week titles — but
its absence is never an error.

Output paths are resolved here, and only here, because this is the one layer that knows the
course root. Artifacts live with the course (a sibling `quizzes/` tree), never in the app.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from coursekit import courseconfig


@dataclass
class Unit:
    transcript_path: Path
    week_slug: str
    output_dir: Path
    course_slug: str
    week_label: str
    course_title: str | None = None
    module: str | None = None
    course_root: Path | None = None
    config: courseconfig.CourseConfig | None = None


def slugify(text: str) -> str:
    """Lowercase, path-safe, hyphen-joined. Never empty."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "untitled"


def _make_unit(transcript_path: Path, anchor_dir: Path, output_root: Path | None) -> Unit:
    stem = transcript_path.stem
    week_num = courseconfig.week_key(stem)
    week_slug = f"week-{week_num}" if week_num else slugify(stem)

    # Resolve the course project once. courseconfig owns root-finding, yaml loading, and the
    # graceful degradation (missing file / bad yaml / no pyyaml all give empty dicts, never raise).
    # legacy_search stays off: quizbot never had the transcriber's loose-file convention.
    cfg = courseconfig.load(transcript_path, config_name="quiz.yaml")
    course_root = cfg.root
    course_title = cfg.course_title
    week = cfg.week(week_num) if week_num else {}
    week_title = week.get("title")
    module = week.get("module")

    # A human-readable week label for the prompt.
    if week_num and week_title:
        week_label = f"Week {week_num}: {week_title}"
    elif week_num:
        week_label = f"Week {week_num}"
    else:
        week_label = stem

    # course_slug is an identifier (run_id, override paths, display), not part of the
    # course-anchored output path.
    if course_title:
        course_slug = slugify(course_title)
    elif course_root is not None:
        course_slug = slugify(course_root.name)
    else:
        course_slug = slugify(anchor_dir.name)

    # Output lives with the course, never in the app.
    if output_root is not None:
        output_dir = output_root / course_slug / week_slug
    elif course_root is not None:
        output_dir = course_root / "quizzes" / week_slug
    else:
        output_dir = anchor_dir / "quizzes" / week_slug

    return Unit(
        transcript_path=transcript_path,
        week_slug=week_slug,
        output_dir=output_dir,
        course_slug=course_slug,
        week_label=week_label,
        course_title=course_title,
        module=module,
        course_root=course_root,
        config=cfg,
    )


def find_units(path, *, output_root=None) -> list[Unit]:
    """Discover work units from a file or a directory.

    A file yields one unit. A directory yields one unit per combined per-week transcript
    (`week-*.md`); per-video files are excluded by the `week-` prefix.
    """
    path = Path(path).expanduser().resolve()
    output_root = Path(output_root).expanduser().resolve() if output_root else None

    if path.is_file():
        return [_make_unit(path, path.parent, output_root)]

    if path.is_dir():
        # The transcriber keeps combined docs under output/. When the input has one (e.g.
        # the user points at a course root), scan it, so stray week-*.md in sibling trees
        # like media/ or "before clean up/" are not collected.
        base = path / "output" if (path / "output").is_dir() else path
        seen = set()
        transcripts = []
        for p in sorted(base.glob("**/week-*.md")):
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                transcripts.append(rp)
        units = [_make_unit(p, path, output_root) for p in transcripts]
        _guard_no_output_collision(units)
        return units

    raise FileNotFoundError(f"no such file or directory: {path}")


def _guard_no_output_collision(units: list[Unit]) -> None:
    """Two units writing to one directory would clobber a week's bank silently."""
    by_dir: dict[Path, list[Path]] = {}
    for u in units:
        by_dir.setdefault(u.output_dir, []).append(u.transcript_path)
    clashes = {d: ts for d, ts in by_dir.items() if len(ts) > 1}
    if clashes:
        lines = [f"{d} <- {', '.join(str(t) for t in ts)}" for d, ts in clashes.items()]
        raise ValueError(
            "multiple transcripts resolve to the same output directory:\n  "
            + "\n  ".join(lines)
        )
