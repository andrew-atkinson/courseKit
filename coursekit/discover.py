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
from coursekit import courseconfig, coursestructure


@dataclass
class Unit:
    transcript_path: Path
    week_slug: str
    output_dir: Path
    course_slug: str
    week_label: str
    week_num: str | None = None      # the bare week number ("3"), carried so consumers need not
                                     # re-derive it with week_key(week_slug); None for a non-week unit
    course_title: str | None = None
    module: str | None = None
    course_root: Path | None = None
    config: courseconfig.CourseConfig | None = None


def slugify(text: str) -> str:
    """Lowercase, path-safe, hyphen-joined. Never empty."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "untitled"


def _course_slug(course_title, course_root: Path | None, anchor_dir: Path) -> str:
    """An identifier for the course (run_id, override paths, display) — not part of the
    course-anchored output path. Title first, then the root dir name, then the input dir."""
    if course_title:
        return slugify(course_title)
    if course_root is not None:
        return slugify(course_root.name)
    return slugify(anchor_dir.name)


def _output_dir(course_slug: str, week_slug: str, course_root: Path | None,
                anchor_dir: Path, output_root: Path | None, subdir: str) -> Path:
    """Where a unit's artifacts go. Output lives WITH the course (a sibling `subdir` tree), never in
    the app; `subdir` (quizzes/, pages/, …) keeps each generator's tree side by side."""
    if output_root is not None:
        return output_root / course_slug / week_slug
    if course_root is not None:
        return course_root / subdir / week_slug
    return anchor_dir / subdir / week_slug


def _make_unit(transcript_path: Path, anchor_dir: Path, output_root: Path | None,
               subdir: str = "quizzes") -> Unit:
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

    course_slug = _course_slug(course_title, course_root, anchor_dir)
    output_dir = _output_dir(course_slug, week_slug, course_root, anchor_dir, output_root, subdir)

    return Unit(
        transcript_path=transcript_path,
        week_slug=week_slug,
        output_dir=output_dir,
        course_slug=course_slug,
        week_label=week_label,
        week_num=week_num,
        course_title=course_title,
        module=module,
        course_root=course_root,
        config=cfg,
    )


def _units_from_manifest(struct, anchor_dir: Path, output_root: Path | None,
                         subdir: str) -> list[Unit]:
    """Build units from a DECLARED course structure (FLOW-7) instead of inferring from filenames.

    Each declared week whose `doc` FILE exists becomes a unit, carrying the declared week number,
    title, and module directly — so a week doc can be named anything (`w3.md`, `exposure.md`), not
    just `week-3.md`. A declared week with no doc on disk yet (not ingested) is skipped, exactly as
    the glob skips a week with no file. `config` is resolved the same way `_make_unit` does.
    """
    root = struct.root
    course_title = struct.course_title
    course_slug = _course_slug(course_title, root, anchor_dir)
    units = []
    for week_num, _entry in struct.iter_weeks():
        doc = struct.week_doc(week_num)
        if doc is None or not doc.is_file():
            continue
        doc = doc.resolve()
        week_slug = f"week-{week_num}"
        units.append(Unit(
            transcript_path=doc,
            week_slug=week_slug,
            output_dir=_output_dir(course_slug, week_slug, root, anchor_dir, output_root, subdir),
            course_slug=course_slug,
            week_label=struct.week_label(week_num),
            week_num=week_num,
            course_title=course_title,
            module=struct.week_module(week_num),
            course_root=root,
            config=courseconfig.load(doc, config_name="quiz.yaml"),
        ))
    _guard_no_output_collision(units)
    return units


def find_units(path, *, output_root=None, subdir: str = "quizzes") -> list[Unit]:
    """Discover work units from a file or a directory.

    A file yields one unit. A directory yields one unit per week. When the course DECLARES its
    structure (`context.yaml` with `doc`/`sources` per week — FLOW-7), the declared weeks are
    authoritative, so a week doc may be named anything. Otherwise weeks are inferred by globbing
    combined per-week transcripts (`week-*.md`; per-video files excluded by the `week-` prefix).
    `subdir` names the artifact tree under the course (default `quizzes`; pages use `pages`).
    """
    path = Path(path).expanduser().resolve()
    output_root = Path(output_root).expanduser().resolve() if output_root else None

    if path.is_file():
        return [_make_unit(path, path.parent, output_root, subdir)]

    if path.is_dir():
        # Declared structure wins over inference when present (FLOW-7). Absent → today's glob.
        struct = coursestructure.CourseStructure.load(path)
        if struct.has_declared_structure():
            return _units_from_manifest(struct, path, output_root, subdir)

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
        units = [_make_unit(p, path, output_root, subdir) for p in transcripts]
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
