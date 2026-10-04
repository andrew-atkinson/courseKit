"""Grading-group proposer (STRC-2) — scan a course's generated artifacts and draft a `grading:` block
(assignment GROUPS + a content-kind→group placement) into coursekit's own structure overlay.

Like FLOW-7's structure proposer, this relocates the guessing into a file the faculty own. It proposes
the STRUCTURE (which groups exist, what lands in them) but **equal-weight placeholders**, never an
invented distribution — deciding that Projects is worth 40% and Quizzes 20% is a faculty value judgment,
not something to fabricate (the same lesson as the arbitrary rubric split). The write is merge-aware:
it sets only `grading` and preserves a `weeks` block the structure proposer may have written.
"""

from pathlib import Path

from coursekit import courseconfig
from coursekit.ingest.propose import overlay_path

# content kind -> the gradebook group it proposes. Kinds are detected from generated artifacts on disk.
_GROUP_NAME = {"assignment": "Assignments", "quiz": "Quizzes"}

_HEADER = (
    "# coursekit grading overlay (STRC-2) — declared assignment GROUPS + weights, read by the course\n"
    "# cartridge. The weights below are EQUAL PLACEHOLDERS: set them to how much each group should\n"
    "# count toward the final grade (percentages; they need not sum to 100 — Canvas normalizes). Edit\n"
    "# `placement` to move an item to another group (by content kind, or by a specific item slug).\n\n"
)


def scan_kinds(root: Path) -> list[str]:
    """Which graded artifact KINDS exist under the course, in a stable order (assignments, then quizzes)."""
    kinds = []
    if any(root.glob("assignments/**/assignment.json")):
        kinds.append("assignment")
    if any(root.glob("quizzes/**/bank.json")):
        kinds.append("quiz")
    return kinds


def propose_grading(path) -> dict:
    """Draft a `grading` dict from the kinds present: one group per kind, equal-weight placeholders, and
    a kind→group placement map. Empty dict when no graded artifacts are found."""
    root = courseconfig.find_root(Path(path).expanduser()) or Path(path).expanduser().resolve()
    kinds = scan_kinds(root)
    if not kinds:
        return {}
    w = round(100 / len(kinds), 1)
    groups = [{"name": _GROUP_NAME[k], "weight": w} for k in kinds]
    drift = round(100 - w * len(kinds), 1)       # keep the placeholders summing to exactly 100
    if drift:
        groups[0]["weight"] = round(groups[0]["weight"] + drift, 1)
    return {"groups": groups, "placement": {k: _GROUP_NAME[k] for k in kinds}}


def write_grading(path, grading: dict, *, force: bool = False) -> Path:
    """Merge `grading` into the overlay, PRESERVING any existing `weeks`. Refuse to overwrite an existing
    `grading` block without `force` (so a re-run never silently discards hand-set weights)."""
    try:
        import yaml
    except ImportError:
        raise SystemExit("writing the overlay needs pyyaml (pip/uv install it).")
    root = courseconfig.find_root(Path(path).expanduser())
    if root is None:
        raise SystemExit("no .vtconfig course root found — create a .vtconfig/ folder in the course root first.")
    dest = overlay_path(root)
    data = courseconfig._read_yaml(dest) if dest.exists() else {}
    if not isinstance(data, dict):
        data = {}
    if data.get("grading") and not force:
        raise SystemExit(f"{dest} already declares `grading:` — pass --force to redraft (discards hand-set weights).")
    data["grading"] = grading
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_HEADER + yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return dest
