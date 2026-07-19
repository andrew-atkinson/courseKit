"""Course-project configuration.

A course project is a directory marked by `.vtconfig/`, the same marker the videotranscriber uses.
Inside it, three files with three different owners:

    context.yaml   Shared course structure — title, weeks, modules. Authored by the transcriber
                   (vt_context.py) from a media scan, optionally enriched by a Canvas manifest;
                   read by every tool.
    config.yaml    The transcriber's own technical settings. Quizbot does not read it.
    quiz.yaml      Quizbot's own technical settings. The transcriber does not read it.

`courseconfig` is the shared *mechanism* — find the root, read a yaml file, normalise a week
reference — while each tool owns its config *file*, passed by name to `load()`. Course structure is
shared because it is a fact about the course; technical settings are per-tool because the tools do
different jobs (the transcriber runs vision and whisper models; quizbot runs a tool-calling text
model, and may legitimately want a different one).

`load()` never raises. A course config is enrichment: its absence, corruption, or a machine without
pyyaml all degrade to empty dicts rather than failing a run. That was already how `discover.py`
treated `context.yaml`; this promotes it and makes it uniform.
"""

import re
from dataclasses import dataclass
from pathlib import Path

VTCONFIG_DIR_NAME = ".vtconfig"


def week_key(ref) -> str | None:
    """Normalise a week reference to its bare number, or None when there isn't one.

    `week-3.md`, `Week 3: Repetition`, `week 3`, `3`, and the int `3` all map to `"3"`; a stem
    like `intro.md` maps to None. This is the single normalisation that `discover._week_number`
    and `pipeline._week_key` each grew their own copy of.
    """
    s = str(ref).strip()
    m = re.search(r"week[-_ ]?(\d+)", s, re.IGNORECASE)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d+", s):
        return s
    return None


@dataclass(frozen=True)
class CourseConfig:
    """A resolved course project. Any field may be empty/None when nothing was found."""

    root: Path | None            # the directory containing .vtconfig/, or None
    config: dict                 # this tool's config file, {} when absent
    context: dict                # the shared context.yaml, {} when absent
    config_path: Path | None     # where this tool's config lives (or would, for a future write)
    context_path: Path | None

    def value(self, key: str, fallback=None):
        """A key from this tool's config, or the fallback when unset or null."""
        v = self.config.get(key) if self.config else None
        return v if v is not None else fallback

    def prompt_name(self, key: str, cli_arg: str | None = None) -> str:
        """Which named prompt to use: CLI arg wins, then this tool's config, then 'default'."""
        if cli_arg:
            return cli_arg
        v = self.config.get(key) if self.config else None
        return v if v else "default"

    def week(self, week_ref) -> dict:
        """The shared context's entry for a week, keyed by its number. {} when unknown."""
        k = week_key(week_ref)
        if k is None or not self.context:
            return {}
        weeks = self.context.get("weeks") or {}
        return weeks.get(f"week {k}") or {}

    @property
    def course_title(self) -> str | None:
        return (self.context or {}).get("course_title") if self.context else None


def find_root(start: Path) -> Path | None:
    """The nearest ancestor (inclusive) containing a `.vtconfig/` marker, like git finds `.git`."""
    d = Path(start).resolve()
    if d.is_file():
        d = d.parent
    for parent in [d, *d.parents]:
        if (parent / VTCONFIG_DIR_NAME).is_dir():
            return parent
    return None


def _find_file(start: Path, name: str, legacy_search: bool) -> Path | None:
    """Prefer `<root>/.vtconfig/<name>`. With legacy_search, fall back to a loose `<name>` in the
    start dir, its parent, or grandparent — for projects predating `.vtconfig/`.

    legacy_search is off by default and opt-in per call, so quizbot (which never had the loose-file
    convention) does not inherit it, and a stray context.yaml above an input cannot silently become
    authoritative.
    """
    d = Path(start)
    if d.is_file():
        d = d.parent
    root = find_root(d)
    if root:
        candidate = root / VTCONFIG_DIR_NAME / name
        if candidate.is_file():
            return candidate
    if legacy_search:
        for anc in (d, d.parent, d.parent.parent):
            candidate = anc / name
            if candidate.is_file():
                return candidate
    return None


def find_context_file(start: Path, *, legacy_search: bool = False) -> Path | None:
    return _find_file(start, "context.yaml", legacy_search)


def find_config_file(start: Path, name: str = "config.yaml", *,
                     legacy_search: bool = False) -> Path | None:
    return _find_file(start, name, legacy_search)


def _read_yaml(path: Path | None) -> dict:
    """A yaml mapping, or {} for anything that isn't one — missing file, bad YAML, no pyyaml."""
    if path is None or not path.is_file():
        return {}
    try:
        import yaml  # guarded: a machine without pyyaml degrades rather than crashing
    except ImportError:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load(start, *, config_name: str = "config.yaml",
         legacy_search: bool = False) -> CourseConfig:
    """Resolve the course project containing `start`. Never raises.

    `config_name` selects which tool's config file to read — quizbot passes "quiz.yaml", the
    transcriber "config.yaml". The path fields point at where each file lives, or where it *would*
    live under `.vtconfig/` when a root is known but the file is absent, so a later write has a
    target.
    """
    start = Path(start).expanduser().resolve()
    root = find_root(start)

    context_path = find_context_file(start, legacy_search=legacy_search)
    config_path = find_config_file(start, config_name, legacy_search=legacy_search)
    if root is not None:
        context_path = context_path or root / VTCONFIG_DIR_NAME / "context.yaml"
        config_path = config_path or root / VTCONFIG_DIR_NAME / config_name

    return CourseConfig(
        root=root,
        config=_read_yaml(config_path),
        context=_read_yaml(context_path),
        config_path=config_path,
        context_path=context_path,
    )
