"""Turn a path into a list of generation runs.

The primary input is a markdown file or a directory of them, so coursekit works on any file set;
a `.vtconfig/` root found above it enriches each unit with course/unit titles, but its absence is
never an error. The units themselves come from the course model (`coursekit/course.py`), and each
run (`Unit` here — CORE-5 renames it) is built by `Course.run_target`, the one place output paths
are resolved. Artifacts live with the course (a sibling `quizzes/` tree), never in the app.
"""

import re
from dataclasses import dataclass, replace
from pathlib import Path
from coursekit import courseconfig, outcomes


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


def find_units(path, *, output_root=None, subdir: str = "quizzes") -> list[Unit]:
    """The units a generation run covers, from the course model (CORE-2): a file is one unit (the
    unit whose doc it is, else a unit of its own); a folder is every unit with a doc under it, in the
    course's unit order. `subdir` names the artifact tree under the course (`quizzes`, `pages`, …).
    """
    from coursekit.course import Course
    path = Path(path).expanduser().resolve()
    output_root = Path(output_root).expanduser().resolve() if output_root else None
    if not path.exists():
        raise FileNotFoundError(f"no such file or directory: {path}")

    with outcomes.capture(sink=lambda n: None):            # stray artifacts are the emitters' concern
        course = Course.load(path if path.is_dir() else path.parent)
    if path.is_file():
        unit = next((u for u in course.units if u.doc == path), None)
        targets = [unit or replace(course.target_unit(courseconfig.week_key(path.stem) or path.stem), doc=path)]
    else:
        targets = [u for u in course.units if u.doc is not None and u.doc.is_relative_to(path)]
    # A unit with two docs on disk becomes two runs into one folder, which the guard below refuses.
    runs = [replace(u, doc=d) for u in targets for d in course.duplicate_docs.get(u.id, [u.doc])]
    units = [course.run_target(u, subdir=subdir, output_root=output_root) for u in runs]
    _guard_no_output_collision(units)
    return units


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
