"""Boundary-correct per-concept material — analyze-time segmentation of the week text.

The keyword slicer (`decompose.slice_material`) is retrieval, not segmentation: it scores chunks by the
concept's own words, so a worked example that doesn't repeat the concept's name (the code/case/figure
that follows "let's see it:") scores zero and is dropped, and the section arrives with a definition and
no demonstration. The fix is to stop re-deriving boundaries at generation time — when `analyze` builds
the concept map, partition the week text into ONE contiguous span per concept and store it, so
decomposition reads boundary-correct, verbatim material with each concept's example included by
construction. Material-kind-agnostic: it works for code, a case, a statute, an image caption — anything.

Mechanism (a small, robust model output): chunk the text; the model marks, in concept order, the chunk
where each concept's teaching BEGINS; the spans between marks partition the transcript. It assumes
concepts are taught roughly in order — a safe assumption, since the map itself is built by reading the
text top to bottom. Stored beside the map as `week-<key>.materials.json`; when it is absent (or a
concept's span is empty) decomposition falls back to the keyword slicer, so nothing breaks.
"""

import json
import re
from pathlib import Path

from coursekit import prompts

MATERIALS_SUFFIX = ".materials.json"


# --------------------------------------------------------------------- deterministic pieces (testable)
def chunk_text(text: str, *, min_len: int = 200) -> list[str]:
    """Split the week text into chunks on blank lines, merging small paragraphs forward so a chunk is a
    substantial unit (a heading travels with the prose under it) rather than a one-line fragment."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        buf = f"{buf}\n\n{p}" if buf else p
        if len(buf) >= min_len:
            chunks.append(buf)
            buf = ""
    if buf:
        if chunks:
            chunks[-1] = chunks[-1] + "\n\n" + buf
        else:
            chunks.append(buf)
    return chunks


def parse_boundaries(reply: str, n_concepts: int, n_chunks: int) -> list[int]:
    """Turn the model's reply into exactly `n_concepts` start indices — 0-based, clamped, non-decreasing,
    first forced to 0 — so the spans always form a valid partition however the model answered."""
    nums: list[int] = []
    m = re.search(r"\[[^\]]*\]", reply, re.S)
    if m:
        try:
            nums = [int(x) for x in json.loads(m.group(0))]
        except Exception:
            nums = []
    if not nums:
        nums = [int(x) for x in re.findall(r"\d+", reply)]
    idx = [max(0, min(n_chunks - 1, n - 1)) for n in nums] if n_chunks else []  # 1-based → 0-based
    starts: list[int] = []
    prev = 0
    for i in range(n_concepts):
        s = idx[i] if i < len(idx) else prev
        starts.append(max(prev, s))                    # non-decreasing
        prev = starts[-1]
    if starts:
        starts[0] = 0                                  # first concept owns the lead-in; no orphan chunks
    return starts


def materials_from_boundaries(chunks: list[str], starts: list[int], cm) -> dict[str, str]:
    """Partition `chunks` into one verbatim span per concept, keyed by concept name. An empty span (two
    concepts marked at the same chunk) is omitted, so decomposition falls back to the slicer for it."""
    mats: dict[str, str] = {}
    for i, c in enumerate(cm.concepts):
        s = starts[i] if i < len(starts) else len(chunks)
        e = starts[i + 1] if i + 1 < len(starts) else len(chunks)
        span = chunks[s:max(s, e)]
        if span:
            mats[c.name] = "\n\n".join(span)
    return mats


# --------------------------------------------------------------------- the model pass + persistence
def build_messages(chunks: list[str], cm, *, project_root=None) -> list[dict]:
    numbered = "\n\n".join(f"[chunk {i + 1}]\n{c}" for i, c in enumerate(chunks))
    concepts = "\n".join(f"{i + 1}. {c.name}" + (f" — {c.gist}" if c.gist else "")
                         for i, c in enumerate(cm.concepts))
    system = prompts.load("page", "segment", project_root=project_root).body
    user = (f"CONCEPTS (in the order they are taught):\n{concepts}\n\n"
            f"TRANSCRIPT CHUNKS (numbered 1 to {len(chunks)}):\n{numbered}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def segment_week(text: str, cm, provider, model, *, project_root=None) -> dict[str, str]:
    """Segment the week text into per-concept material. Returns {concept_name: material}, or {} when
    there is nothing to segment. Best-effort — a parse or model hiccup yields {} (the caller degrades)."""
    chunks = chunk_text(text)
    if not chunks or not cm.concepts:
        return {}
    reply = provider.chat(model=model, messages=build_messages(chunks, cm, project_root=project_root),
                          temperature=0.2)
    starts = parse_boundaries(reply, len(cm.concepts), len(chunks))
    return materials_from_boundaries(chunks, starts, cm)


def materials_path(course_root, week_key: str) -> Path:
    return Path(course_root) / ".vtconfig" / "concepts" / f"week-{week_key}{MATERIALS_SUFFIX}"


def save_materials(mats: dict, path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(mats, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def load_materials(path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_materials_for_unit(unit) -> dict | None:
    """The per-concept materials for a discovered week `unit`, or None. Best-effort, like the map loader."""
    if not getattr(unit, "course_root", None):
        return None
    key = unit.week_num
    return load_materials(materials_path(unit.course_root, key)) if key else None
