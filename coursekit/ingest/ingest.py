"""Documents -> `output/week-N.md`.

The adapter's top layer: resolve inputs, map each to a week, extract text, optionally reshape it
with the local model, and write the week doc where `discover.find_units` will find it
(`**/week-*.md`). Reuses the spine — `courseconfig.week_key` for week identity, `courseconfig.find_root`
for the course root, `prompts.load` for the (overridable) shaping prompt, and the `Provider` for the
one model call. No network.
"""

import re
from pathlib import Path

from coursekit import courseconfig, prompts
from coursekit.ingest.extract import extract_text, is_supported

SHAPE_CATEGORY = "ingest"


# ------------------------------------------------------------- week mapping

# An ANCESTOR only counts as a week when it IS a week folder (`week-3`, `week 3`, `week_3`) — not just
# any path component that happens to contain "week" and a digit (a temp dir, a home folder), which
# walking to the filesystem root would otherwise false-match.
_WEEK_DIR_RE = re.compile(r"^week[\s_-]?(\d+)$", re.IGNORECASE)


def _week_of(p: Path) -> str | None:
    """A source's week: its own filename (`week-3.pdf`) first, then the nearest `week-N` ANCESTOR
    directory (`.../week-3/readings/foo.pdf`) — a folder-per-week course keys off the directory."""
    k = courseconfig.week_key(p.stem)
    if k:
        return k
    for parent in p.parents:
        m = _WEEK_DIR_RE.match(parent.name)
        if m:
            return m.group(1)
    return None


def _week_sort_key(slug: str):
    n = slug.removeprefix("week-")
    return (0, int(n)) if n.isdigit() else (1, n)


def _source_order(p: Path):
    """Within a week, put an outline first (it frames the week), then everything else by name."""
    return (0 if "outline" in p.stem.lower() else 1, p.name.lower())


def plan_weeks(paths: list[Path]) -> list[tuple[str, list[Path]]]:
    """Group input files into weeks, so a week that is a FOLDER of many docs (readings + slides + …)
    consolidates into ONE `week-N.md` (FLOW-2 — multiple sources per week). A file's week is its own
    name (`week-3.pdf`) or a `week-N` ANCESTOR directory. When NO file names a week, fall back to
    enumerating each doc as its own week (a flat folder of readings). A file with no discernible week
    is dropped when keyed weeks exist — e.g. a course-level outline at the root is not week content."""
    weeks: dict[str, list[Path]] = {}
    unkeyed: list[Path] = []
    for p in sorted(paths, key=lambda p: p.name.lower()):
        k = _week_of(p)
        if k:
            weeks.setdefault(f"week-{k}", []).append(p)
        else:
            unkeyed.append(p)
    if not weeks:
        return [(f"week-{i}", [p]) for i, p in enumerate(unkeyed, 1)]
    for srcs in weeks.values():
        srcs.sort(key=_source_order)
    return [(slug, weeks[slug]) for slug in sorted(weeks, key=_week_sort_key)]


def _inputs(path: Path) -> list[Path]:
    path = Path(path)
    if path.is_file():
        return [path] if is_supported(path) else []
    return [p for p in sorted(path.rglob("*")) if p.is_file() and is_supported(p)]


def _output_dir(path: Path, out_dir) -> Path:
    """Where the week docs go: the course's `output/` when a `.vtconfig/` root is found (matching the
    transcriber), else an `output/` beside the input. An explicit out_dir overrides."""
    if out_dir:
        return Path(out_dir)
    root = courseconfig.find_root(Path(path))
    base = root if root else (Path(path) if Path(path).is_dir() else Path(path).parent)
    return base / "output"


# ------------------------------------------------------------- shaping

def shape(raw_text: str, provider, model: str, *, project_root=None) -> str:
    """Reshape raw extracted text into a teaching-ready week doc via the local model. A faithful
    cleanup+structuring pass, not a summary — the prompt forbids inventing or dropping content."""
    p = prompts.load(SHAPE_CATEGORY, "shape", project_root=project_root)
    messages = [{"role": "system", "content": p.body},
                {"role": "user", "content": raw_text}]
    return provider.chat(model=model, messages=messages)


# ------------------------------------------------------------- orchestration

def ingest(path, *, out_dir=None, raw: bool = False, provider=None,
           model: str | None = None) -> list[tuple[Path, Path]]:
    """Ingest every supported document under `path` into `output/week-N.md`.

    Returns [(source, written)] in week order. With `raw=True` the extracted text is written as-is
    (deterministic, no model); otherwise each doc is reshaped by the local model — `provider` and
    `model` are then required.
    """
    inputs = _inputs(path)
    if not inputs:
        return []
    if not raw and provider is None:
        raise ValueError("shaping needs a provider; pass raw=True to skip the model")

    plan = plan_weeks(inputs)
    out = _output_dir(path, out_dir)
    out.mkdir(parents=True, exist_ok=True)
    root = courseconfig.find_root(Path(path))

    def _text(src: Path) -> str:
        t = extract_text(src)
        return shape(t, provider, model, project_root=root) if not raw else t

    written = []
    for slug, sources in plan:
        if len(sources) == 1:
            body = _text(sources[0]).strip()          # a single source: the doc as-is (back-compat)
        else:
            # Consolidate a week's docs into ONE doc, each under a `## <source>` header so the week
            # stays SOURCE-ADDRESSABLE (a targeted quiz / a source-scoped page can still find it) —
            # structure preserved, not a flat blob (FLOW-2 / PAGE-13).
            body = "\n\n".join(f"## {s.stem}\n\n{_text(s).strip()}" for s in sources)
        dest = out / f"{slug}.md"
        dest.write_text(body.strip() + "\n", encoding="utf-8")
        for s in sources:
            written.append((s, dest))
    return written
