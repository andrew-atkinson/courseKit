"""Structure proposer (FLOW-7 Phase 2) — scan a course tree, DECLARE its structure.

The naming heuristics, relocated. Instead of inferring structure on every run inside discovery, scan
ONCE and write a reviewable, editable overlay (`.vtconfig/structure.coursekit.yaml`) that the reader
composes with `context.yaml` and treats as authoritative. A file the heuristics cannot confidently key
is SURFACED as unassigned, never silently dropped — the fix for that whole class of bug.

coursekit writes only its OWN overlay, never the transcriber's `context.yaml` (the one-writer-per-file
rule — see agent/architecture.md). Scope is INPUT-structure analysis only: what materials exist and how
they group into weeks — NOT output design or sequencing, which are separate stations.
"""

from dataclasses import dataclass, field
from pathlib import Path

from coursekit import courseconfig
from coursekit.coursestructure import OVERLAY_NAME, _kind_from_suffix
from coursekit.ingest.extract import is_supported
from coursekit.ingest.ingest import _week_of

# Generated / config trees are not source material — never propose coursekit's own output as an input.
_EXCLUDE = {courseconfig.VTCONFIG_DIR_NAME, "output", "quizzes", "pages", ".git"}

_OVERLAY_HEADER = (
    "# coursekit structure overlay (FLOW-7) — the DECLARED course structure, composed with the\n"
    "# transcriber's context.yaml when the reader loads it. coursekit writes this file; you may edit\n"
    "# it freely. Precedence: context.yaml owns week titles/modules; this overlay owns each week's\n"
    "# typed `sources` (and an optional `doc:` pointer). Re-run `coursekit propose --force` to redraft\n"
    "# (which discards manual edits).\n\n"
)


@dataclass
class Proposal:
    """What the proposer found: weeks it could confidently key, and the files it could not."""
    weeks: dict = field(default_factory=dict)     # "week N" -> {"sources": [ {path,title,kind,role}, ... ]}
    unassigned: list = field(default_factory=list)  # [Path] supported files under no keyable week
    root: Path | None = None


def _role(stem: str) -> str:
    """An outline/overview FRAMES the week; everything else is content (replaces ingest's stem sniff)."""
    s = stem.lower()
    return "framing" if ("outline" in s or "overview" in s) else "content"


def _excluded(rel: Path) -> bool:
    return any(part in _EXCLUDE or part.startswith(".") for part in rel.parts)


def scan_supported(path) -> tuple[Path | None, list[Path]]:
    """(course root, supported documents under `path`), excluding coursekit's own generated/config
    trees. The shared scan for both the deterministic and the model-assisted proposers."""
    path = Path(path).expanduser().resolve()
    root = courseconfig.find_root(path)
    anchor = root or path
    files = []
    for p in sorted(path.rglob("*")):
        if not p.is_file() or not is_supported(p):
            continue
        rel = p.relative_to(anchor) if _is_under(p, anchor) else Path(p.name)
        if _excluded(rel):
            continue
        files.append(p)
    return root, files


def _sort_sources(entry: dict) -> None:
    # framing first, then by path — matches ingest._source_order so the consolidated doc agrees
    entry["sources"].sort(key=lambda s: (0 if s["role"] == "framing" else 1, s["path"].lower()))


def propose(path) -> Proposal:
    """Scan `path` for supported documents and group them into weeks by the SAME heuristics discovery
    used to use (`_week_of`: a `week-N` filename or ancestor directory). Files with no keyable week are
    collected as `unassigned` rather than dropped."""
    root, files = scan_supported(path)
    weeks: dict = {}
    unassigned: list = []
    for p in files:
        k = _week_of(p)
        if k:
            weeks.setdefault(f"week {k}", {"sources": []})["sources"].append(_source_entry(p, root))
        else:
            unassigned.append(p)

    for entry in weeks.values():
        _sort_sources(entry)
    weeks = {k: weeks[k] for k in sorted(weeks, key=_week_num_of)}
    return Proposal(weeks=weeks, unassigned=unassigned, root=root)


def _source_entry(p: Path, root: Path | None) -> dict:
    rel = p.relative_to(root) if (root and _is_under(p, root)) else Path(p.name)
    return {"path": str(rel), "title": p.stem, "kind": _kind_from_suffix(p.name), "role": _role(p.stem)}


def _is_under(p: Path, base: Path) -> bool:
    try:
        p.relative_to(base)
        return True
    except ValueError:
        return False


def _week_num_of(week_key: str):
    n = week_key.removeprefix("week ")
    return (0, int(n)) if n.isdigit() else (1, n)


def overlay_path(root: Path) -> Path:
    return Path(root) / courseconfig.VTCONFIG_DIR_NAME / OVERLAY_NAME


def write_overlay(proposal: Proposal, *, force: bool = False) -> Path:
    """Write the proposal to coursekit's own overlay file. Refuses to overwrite an existing overlay
    without `force`, so a re-run never silently discards the faculty's manual edits."""
    if proposal.root is None:
        raise SystemExit("no .vtconfig course root found — the overlay lives in .vtconfig/. "
                         "Create a .vtconfig/ folder in the course root first.")
    try:
        import yaml
    except ImportError:
        raise SystemExit("writing the overlay needs pyyaml (pip/uv install it).")
    dest = overlay_path(proposal.root)
    if dest.exists() and not force:
        raise SystemExit(f"{dest} already exists — pass --force to redraft (discards manual edits).")
    body = yaml.safe_dump({"weeks": proposal.weeks}, sort_keys=False, allow_unicode=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_OVERLAY_HEADER + body, encoding="utf-8")
    return dest
