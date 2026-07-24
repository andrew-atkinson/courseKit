"""Documents -> `output/week-N.md`.

The adapter's top layer: resolve inputs, map each to a week, extract text, optionally reshape it
with the local model, and write the week doc where `discover.find_units` will find it
(`**/week-*.md`). Reuses the spine — `courseconfig.week_key` for week identity, `courseconfig.find_root`
for the course root, `prompts.load` for the (overridable) shaping prompt, and the `Provider` for the
one model call. No network.
"""

from pathlib import Path

from coursekit import courseconfig, prompts
from coursekit.ingest.extract import extract_text, is_supported

SHAPE_CATEGORY = "ingest"


# ------------------------------------------------------------- week mapping

def plan_weeks(paths: list[Path]) -> list[tuple[str, Path]]:
    """Map input files to `week-N` slugs. If every file names its week (`week-3.pdf`,
    `Week 2 - Exposure.pptx`), those numbers are used; otherwise all files are enumerated by sorted
    name (1-based). Mixing is resolved by enumerating everything, so a keyed and an unkeyed file can
    never collide silently. A genuine duplicate week is an error, not a lost file."""
    paths = sorted(paths, key=lambda p: p.name.lower())
    keys = [courseconfig.week_key(p.stem) for p in paths]
    if paths and all(k is not None for k in keys):
        plan = [(f"week-{k}", p) for k, p in zip(keys, paths)]
    else:
        plan = [(f"week-{i}", p) for i, p in enumerate(paths, 1)]

    seen: dict[str, Path] = {}
    for slug, p in plan:
        if slug in seen:
            raise ValueError(
                f"two inputs map to {slug}: '{seen[slug].name}' and '{p.name}'. "
                f"Name them week-N.<ext> to disambiguate.")
        seen[slug] = p
    return plan


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

    written = []
    for slug, src in plan:
        text = extract_text(src)
        if not raw:
            text = shape(text, provider, model, project_root=root)
        dest = out / f"{slug}.md"
        dest.write_text(text.strip() + "\n", encoding="utf-8")
        written.append((src, dest))
    return written
