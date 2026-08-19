"""Course structure reader — the declared IR over `context.yaml` (FLOW-7).

coursekit long inferred a course's shape from filenames (`week-*.md`, `week-N/` folders). This reads
it instead from the SHARED `context.yaml` the transcriber already writes: `weeks: {"week N": {...}}`.
A week may declare a `doc:` (the consolidated week text discovery reads) and a typed `sources:` list
of `{path, title, kind, role}`; the transcriber's untyped `videos:` list is normalized into sources
of kind `video`, so a transcriber-authored course needs no migration.

Everything is optional and degrades to empty — the absence of a manifest is not an error, it just
means the caller falls back to filename inference. `has_declared_structure()` is the one signal that
says "drive discovery from the manifest, not the glob"; it fires only when a week carries coursekit's
own `doc`/`sources` keys, so a decoration-only course (title/module, or transcriber `videos`) keeps
today's behavior untouched.

This is a READER only; the proposer that WRITES a draft manifest is a later phase (UX-2).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from coursekit import courseconfig

# extension -> source kind: a deterministic fallback when a source doesn't declare `kind`.
_KIND_BY_SUFFIX = {
    ".pdf": "reading", ".docx": "reading", ".odt": "reading",
    ".txt": "notes", ".md": "notes",
    ".pptx": "slides", ".ppt": "slides",
    ".mp4": "video", ".mov": "video", ".m4v": "video", ".webm": "video",
}


def _kind_from_suffix(path: str) -> str:
    return _KIND_BY_SUFFIX.get(Path(path).suffix.lower(), "unknown")


def _week_sort(num: str):
    """Numeric weeks first, in order; any non-numeric key sorts after, lexically."""
    return (0, int(num)) if num.isdigit() else (1, num)


@dataclass(frozen=True)
class Source:
    """One declared source in a week — a reading, slide deck, video, or note. `path` is relative to
    the course root (or absolute); `resolve` joins it to the root. `role` distinguishes the outline
    that FRAMES the week from its CONTENT (replacing the `"outline" in stem` filename sniff)."""

    path: str
    title: str
    kind: str
    role: str = "content"          # content | framing

    def resolve(self, root: Path | None) -> Path:
        p = Path(self.path).expanduser()
        if p.is_absolute() or root is None:
            return p
        return Path(root) / p


def _as_source(raw, *, default_kind: str | None = None, default_role: str = "content") -> Source | None:
    """Coerce one declared entry (a dict) into a Source, or None when it names no path. Accepts both
    coursekit's `path` and the transcriber's `filename` key."""
    if not isinstance(raw, dict):
        return None
    path = raw.get("path") or raw.get("filename")
    if not path:
        return None
    path = str(path)
    kind = raw.get("kind") or default_kind or _kind_from_suffix(path)
    title = raw.get("title") or Path(path).stem
    role = raw.get("role") or default_role
    return Source(path=path, title=str(title), kind=str(kind), role=str(role))


class CourseStructure:
    """A read-only view of the declared course structure in `context.yaml`. Never raises; a missing
    or partial manifest yields empty results, so callers fall back to inference."""

    def __init__(self, cfg: courseconfig.CourseConfig):
        self._cfg = cfg
        weeks = (cfg.context or {}).get("weeks")
        self._weeks = weeks if isinstance(weeks, dict) else {}

    @classmethod
    def load(cls, start, *, config_name: str = "quiz.yaml") -> "CourseStructure":
        """Resolve the course containing `start` and read its structure. Never raises."""
        return cls(courseconfig.load(start, config_name=config_name))

    @property
    def root(self) -> Path | None:
        return self._cfg.root

    @property
    def course_title(self) -> str | None:
        return self._cfg.course_title

    def _entry(self, week_num: str) -> dict:
        entry = self._weeks.get(f"week {week_num}")
        return entry if isinstance(entry, dict) else {}

    def iter_weeks(self) -> list[tuple[str, dict]]:
        """(week_num, entry) for every declared week, numeric order first."""
        out = []
        for key, entry in self._weeks.items():
            k = courseconfig.week_key(key)
            if k is not None and isinstance(entry, dict):
                out.append((k, entry))
        return sorted(out, key=lambda kv: _week_sort(kv[0]))

    def has_declared_structure(self) -> bool:
        """True when at least one week declares coursekit's own `doc` or `sources` — the signal to
        drive discovery from the manifest. Decoration-only weeks (title/module) and the transcriber's
        `videos:` do NOT trigger it, so existing courses keep the filename-glob path unchanged."""
        return any(entry.get("doc") or entry.get("sources") for _, entry in self.iter_weeks())

    def week_label(self, week_num: str) -> str:
        """`Week 3: Exposure` / `Week 3` from the declared title, matching discover's label format."""
        title = self._entry(week_num).get("title")
        return f"Week {week_num}: {title}" if title else f"Week {week_num}"

    def week_module(self, week_num: str) -> str | None:
        return self._entry(week_num).get("module")

    def week_doc(self, week_num: str) -> Path | None:
        """The consolidated week doc discovery should read: the declared `doc:` (resolved against the
        root) when present, else the default `output/week-<n>.md` when a root is known, else None."""
        doc = self._entry(week_num).get("doc")
        if doc:
            p = Path(str(doc)).expanduser()
            return p if p.is_absolute() or self.root is None else self.root / p
        if self.root is not None:
            return self.root / "output" / f"week-{week_num}.md"
        return None

    def sources_for(self, week_num: str) -> list[Source]:
        """The typed sources for a week: the declared `sources:` list, or — when absent — the
        transcriber's `videos:` normalized to kind `video` (their filenames are relative to the week
        `folder`, so join it). Empty when neither is present."""
        entry = self._entry(week_num)
        raw = entry.get("sources")
        if isinstance(raw, list):
            return [s for s in (_as_source(r) for r in raw) if s is not None]
        vids = entry.get("videos")
        if isinstance(vids, list):
            folder = entry.get("folder")
            out = []
            for r in vids:
                s = _as_source(r, default_kind="video")
                if s is None:
                    continue
                if folder and not Path(s.path).is_absolute():
                    s = replace(s, path=str(Path(str(folder)) / s.path))
                out.append(s)
            return out
        return []
