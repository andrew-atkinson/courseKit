"""Artifact records (CORE-4) — beside each artifact, what it was made from and how; and whether it still
matches its course. The design, and why the verdict comes from the brief: agent/core-4-design.md.

A record is a list of steps (generate, the EU pass, the intro, a fix, a reorder), each with who took it,
when, the model and coursekit version, and two fingerprints:

- `brief` — the hash of exactly the messages the model was shown. It decides staleness: a check rebuilds
  the brief from today's files with the step's own builder and compares.
- `read` — every file the step's loaders opened, with its hash. It only explains a verdict ("week-7.md
  changed"); it may over-include, because it never decides anything.

Status is never stored: `status()` works it out from today's files. A record is written only by the code
that writes its artifact, right after it (`write_step`).
"""

import contextlib
import hashlib
import json
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

RECORD = "record.json"
VERSION = 1
ABSENT = "absent"
_PACKAGE = Path(__file__).resolve().parent.parent          # where the shipped prompts/ live
_reads: ContextVar[dict | None] = ContextVar("coursekit_record_reads", default=None)


def _hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()[:16]


def file_hash(path) -> str:
    try:
        return _hash_bytes(Path(path).read_bytes())
    except (FileNotFoundError, NotADirectoryError):
        return ABSENT


def digest(messages) -> str:
    """The fingerprint of a brief: the messages, exactly as sent."""
    return _hash_bytes(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode("utf-8"))


@contextlib.contextmanager
def reading():
    """Collect every file the loaders `note` while building a brief: {absolute path: hash}."""
    seen: dict[str, str] = {}
    token = _reads.set(seen)
    try:
        yield seen
    finally:
        _reads.reset(token)


def note(path) -> None:
    """A loader read `path` (or looked for it: an absent file counts, so creating one is explained)."""
    seen = _reads.get()
    if seen is not None and path is not None:
        p = Path(path).resolve()
        seen[str(p)] = file_hash(p)


@lru_cache(maxsize=1)
def _commit() -> str:
    from coursekit.evalstore import coursekit_commit
    return coursekit_commit()


def _key(path: str, root: Path | None) -> str:
    """A stable name for a file in a record: `coursekit:` for the shipped prompts, else course-relative."""
    p = Path(path)
    for base, prefix in ((_PACKAGE / "prompts", "coursekit:"), (root, "")):
        if base is not None:
            try:
                return prefix + p.relative_to(base).as_posix()
            except ValueError:
                pass
    return p.as_posix()


def _resolve(key: str, root: Path | None) -> Path:
    if key.startswith("coursekit:"):
        return _PACKAGE / "prompts" / key.removeprefix("coursekit:")
    p = Path(key)
    return p if p.is_absolute() or root is None else root / p


def _root(art_dir: Path) -> Path | None:
    from coursekit.courseconfig import find_root
    return find_root(art_dir)


def load(art_dir) -> dict | None:
    try:
        return json.loads((Path(art_dir) / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _outputs(art_dir: Path, names) -> dict[str, str]:
    return {n: file_hash(art_dir / n) for n in names}


def is_edited(art_dir) -> bool:
    """Has the artifact changed since coursekit last wrote it (a hand edit)?"""
    if art_dir is None:
        return False
    rec = load(art_dir)
    return bool(rec) and _outputs(Path(art_dir), rec["output"]) != rec["output"]


def write_step(art_dir, *, kind: str, unit: str | None, step: str, by: str, outputs,
               brief=None, read: dict | None = None, model: str | None = None,
               options: dict | None = None, fresh: bool = False, edited: bool = False) -> None:
    """Add one step to the artifact's record, after the artifact is written. `fresh` starts a new record
    (a whole new generation); `edited` notes that it was edited by hand before this step. A later step on
    an artifact with no record (one made before records) writes nothing: its status stays unknown, never
    "current" on the strength of a step that isn't how it was made."""
    art_dir = Path(art_dir)
    root = _root(art_dir)
    rec = None if fresh else load(art_dir)
    if rec is None and not fresh:
        return
    if rec is None:
        rec = {"record": VERSION, "kind": kind, "unit": unit, "steps": [], "output": {}, "evaluations": []}
    now = datetime.now().isoformat(timespec="seconds")
    if edited:
        rec["steps"].append({"step": "edited", "by": "instructor", "found": now})
    entry = {"step": step, "at": now, "by": by, "coursekit": _commit()}
    if model:
        entry["model"] = model
    if options:                                        # its paths, course-relative like `read`
        entry["options"] = {k: _key(v, root) if k in ("text", "source") else v for k, v in options.items()}
    if brief is not None:
        entry["brief"] = brief
        entry["read"] = {_key(p, root): h for p, h in sorted((read or {}).items())}
    rec["steps"].append(entry)
    rec["output"] = _outputs(art_dir, outputs)
    tmp = art_dir / f".{RECORD}.tmp"
    tmp.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    tmp.replace(art_dir / RECORD)


# --------------------------------------------------------------------------- the check

@dataclass
class Status:
    """What a check found. `state` is current, stale, outdated, or unknown; `edited` is separate, because
    an artifact can be edited and stale at once. `reasons` say why, in words a person can act on."""
    state: str
    edited: bool = False
    reasons: list[str] = field(default_factory=list)


def status(art_dir, rebuild) -> Status:
    """Compare an artifact's record with today's files. `rebuild(record, step)` returns the messages that
    step would send today (or None when it can't be rebuilt offline, e.g. a fix)."""
    art_dir = Path(art_dir)
    rec = load(art_dir)
    if rec is None:
        return Status("unknown", reasons=["no record: made before records, or not by coursekit"])
    root = _root(art_dir)
    latest = {}
    for s in rec["steps"]:
        if "brief" in s:
            latest[s["step"]] = s                       # a re-run of a step supersedes the earlier one
    stale, outdated = [], []
    for s in latest.values():
        try:
            if digest(rebuild(rec, s)) == s["brief"]:
                continue
        except Exception as e:                          # e.g. the unit's text is gone: say so, don't crash
            stale.append(f"{s['step']}: can't be rebuilt from today's files ({type(e).__name__}: {e})")
            continue
        changed = [k for k, h in s["read"].items() if file_hash(_resolve(k, root)) != h]
        course = [k for k in changed if not k.startswith("coursekit:")]
        if course:
            stale.append(f"{s['step']}: {', '.join(course)} changed since it was made")
        elif changed or s.get("coursekit") != _commit():
            outdated.append(f"{s['step']}: made with an older coursekit "
                            f"({', '.join(changed) or 'its code'} changed)")
        else:
            stale.append(f"{s['step']}: what the model would be shown has changed")
    edited = _outputs(art_dir, rec["output"]) != rec["output"]
    reasons = stale + outdated + (["edited by hand since coursekit last wrote it"] if edited else [])
    return Status("stale" if stale else "outdated" if outdated else "current", edited, reasons)
