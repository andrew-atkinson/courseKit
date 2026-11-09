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

from coursekit import atomic

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


def load(art_dir, name: str = RECORD) -> dict | None:
    try:
        return json.loads((Path(art_dir) / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def name_for(path) -> str:
    """The record of a single-file artifact (a concept map, an overview page) sits beside it:
    `week-7.yaml` → `week-7.record.json`. A folder's artifact (a quiz, a page) has `record.json`."""
    return f"{Path(path).stem}.record.json"


def _outputs(art_dir: Path, names) -> dict[str, str]:
    return {n: file_hash(art_dir / n) for n in names}


def is_edited(art_dir, name: str = RECORD) -> bool:
    """Has the artifact changed since coursekit last wrote it (a hand edit)?"""
    if art_dir is None:
        return False
    rec = load(art_dir, name)
    return bool(rec) and _outputs(Path(art_dir), rec["output"]) != rec["output"]


def write_step(art_dir, *, step: str, by: str, brief=None, read: dict | None = None, model: str | None = None,
               options: dict | None = None, **record) -> None:
    """Add one step to the artifact's record (see `write_steps`)."""
    write_steps(art_dir, [{"step": step, "by": by, "brief": brief, "read": read, "model": model,
                           "options": options}], **record)


def write_steps(art_dir, steps: list[dict], *, kind: str, unit: str | None, outputs, fresh: bool = False,
                edited: bool = False, name: str = RECORD) -> None:
    """Add steps to the artifact's record, after the artifact is written: each a dict of `step`, `by`, and
    optionally `brief`, `read`, `model`, `options`, and `wrote` (which outputs it wrote, when a record's
    steps each write a different file, as `analyze` writes a map and then its material). `fresh` starts a new record (a whole new generation);
    `edited` notes that it was edited by hand before these steps. A later step on an artifact with no
    record (one made before records) writes nothing: its status stays unknown, never "current" on the
    strength of a step that isn't how it was made."""
    art_dir = Path(art_dir)
    root = _root(art_dir)
    rec = None if fresh else load(art_dir, name)
    if rec is None and not fresh:
        return
    if rec is None:
        rec = {"record": VERSION, "kind": kind, "unit": unit, "steps": [], "output": {}, "evaluations": []}
    now = datetime.now().isoformat(timespec="seconds")
    if edited:
        rec["steps"].append({"step": "edited", "by": "instructor", "found": now})
    for s in steps:
        entry = {"step": s["step"], "at": now, "by": s["by"], "coursekit": _commit()}
        if s.get("model"):
            entry["model"] = s["model"]
        if s.get("wrote"):                             # the outputs this step wrote, when not all of them
            entry["wrote"] = list(s["wrote"])
        if s.get("options"):                           # its paths, course-relative like `read`
            entry["options"] = {k: _key(v, root) if k in ("text", "source") else v
                                for k, v in s["options"].items()}
        if s.get("brief") is not None:
            entry["brief"] = s["brief"]
            entry["read"] = {_key(p, root): h for p, h in sorted((s.get("read") or {}).items())}
        rec["steps"].append(entry)
    rec["output"] = _outputs(art_dir, outputs)
    atomic.write(art_dir / name, json.dumps(rec, indent=2))


def unit_for(text_key: str, art_dir):
    """The unit whose text is `text_key` (a record's `options["text"]`), found as a run finds it, and the
    text — noted, since every brief built from it reads it."""
    from coursekit.discover import find_units
    path = _resolve(text_key, _root(Path(art_dir)))
    note(path)
    (unit,) = find_units(path)
    return unit, path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- the check

# Each kind's `rebuild(record, step, art_dir)`: the messages that step would send today. A module name,
# imported when a check needs it, so this module depends on no generator.
_REBUILDERS = {"quiz": "coursekit.generate.quiz.record", "page": "coursekit.generate.page.record",
               "concept_map": "coursekit.generate.page.record",
               "assignment": "coursekit.generate.assignment.build", "overview": "coursekit.generate.overview"}


@dataclass
class Status:
    """What a check found. `state` is current, stale, outdated, or unknown; `edited` is separate, because
    an artifact can be edited and stale at once. `reasons` say why, in words a person can act on."""
    state: str
    edited: bool = False
    reasons: list[str] = field(default_factory=list)
    by_step: tuple = field(default=(), compare=False, repr=False)   # ((steps, reason), …) behind `stale`


def _made_by(path: Path, art: tuple) -> tuple | None:
    """The record (folder, name) whose artifact `path` is part of, other than `art` itself — an input that
    is itself an artifact, such as the concept map a quiz was built from."""
    for rp in sorted(path.parent.glob("*record.json")):
        found = (path.parent, rp.name)
        if found != art and path.name in (load(*found) or {}).get("output", {}):
            return found
    return None


def status(art_dir, name: str = RECORD, *, _seen: frozenset = frozenset()) -> Status:
    """Compare an artifact's record with today's files, rebuilding each step's brief with its kind's own
    builder. An input that is itself an artifact and is stale makes this one stale too (upstream)."""
    import importlib
    art_dir = Path(art_dir)
    rec = load(art_dir, name)
    if rec is None:
        return Status("unknown", reasons=["no record: made before records, or not by coursekit"])
    rebuild = importlib.import_module(_REBUILDERS[rec["kind"]]).rebuild
    root = _root(art_dir)
    latest = {}
    for s in rec["steps"]:
        if "brief" in s:
            latest[s["step"]] = s                       # a re-run of a step supersedes the earlier one
    stale, outdated, upstream = [], [], {}         # stale: (the steps it's about, why)
    for s in latest.values():
        for k in s["read"]:
            if not k.startswith("coursekit:"):
                upstream.setdefault(k, []).append(s["step"])
        try:
            if digest(rebuild(rec, s, art_dir)) == s["brief"]:
                continue
        except Exception as e:                          # e.g. the unit's text is gone: say so, don't crash
            stale.append(({s["step"]}, f"{s['step']}: can't be rebuilt from today's files ({type(e).__name__}: {e})"))
            continue
        changed = [k for k, h in s["read"].items() if file_hash(_resolve(k, root)) != h]
        course = [k for k in changed if not k.startswith("coursekit:")]
        if course:
            stale.append(({s["step"]}, f"{s['step']}: {', '.join(course)} changed since it was made"))
        elif changed or s.get("coursekit") != _commit():
            outdated.append(f"{s['step']}: made with an older coursekit "
                            f"({', '.join(changed) or 'its code'} changed)")
        else:
            stale.append(({s["step"]}, f"{s['step']}: what the model would be shown has changed"))
    here = (art_dir, name)
    for k, steps in upstream.items():
        path = _resolve(k, root)
        made = _made_by(path, here)
        if made is None or made in _seen:
            continue
        up = status(*made, _seen=_seen | {here})
        writers = {s["step"] for s in load(*made)["steps"] if path.name in s.get("wrote", [path.name])}
        why = [r for s, r in up.by_step if s & writers]
        if why:                                         # the steps that made this very file are stale
            stale.append((set(steps), f"{', '.join(steps)}: built from {k}, which is itself stale ({'; '.join(why)})"))
    edited = _outputs(art_dir, rec["output"]) != rec["output"]
    reasons = [r for _, r in stale] + outdated + (["edited by hand since coursekit last wrote it"] if edited else [])
    return Status("stale" if stale else "outdated" if outdated else "current", edited, reasons, tuple(stale))


def main() -> int:
    """Print every record's status under a course: `python -m coursekit.records PATH`."""
    import argparse
    ap = argparse.ArgumentParser(description="Show whether each artifact still matches its course (CORE-4).")
    ap.add_argument("course")
    root = Path(ap.parse_args().course).expanduser().resolve()
    found = sorted(root.rglob("*record.json"))
    if not found:
        print(f"No records under {root}: everything there was made before records, so its status is unknown.")
    for rp in found:
        st = status(rp.parent, rp.name)
        made = rp.parent if rp.name == RECORD else rp.parent / rp.name.removesuffix(".record.json")
        print(f"{made.relative_to(root).as_posix():48} {st.state}{' + edited' if st.edited else ''}")
        for r in st.reasons:
            print(f"    {r}")
    return 0


if __name__ == "__main__":
    from coursekit.console import run
    raise SystemExit(run(main))
