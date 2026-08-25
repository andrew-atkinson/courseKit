"""Model-assisted structure proposer (FLOW-7 Phase 4).

When a course tree encodes no `week-N` markers — files named by TOPIC, folders named by module — the
deterministic proposer leaves everything unassigned. This asks a local model to GROUP the real files
into weeks instead. It is the same job (input-structure analysis) with a smarter guesser: it emits the
SAME `Proposal`, which `propose.write_overlay` writes and `coursestructure` reads. Nothing downstream
changes.

Two disciplines make the model safe here:
  1. **No invention.** The model is handed the EXACT list of files that exist and commits groupings
     through an `assign_week` tool; every path it returns is validated against that list and a made-up
     path is dropped. It arranges what exists — it cannot conjure a file (the structural analogue of the
     no-fabricated-URL rule).
  2. **Descriptive, not prescriptive.** It groups and PRESERVES any order the tree already implies; it
     does not decide what *should* be taught or invent a pedagogical sequence (that is a separate
     station). Uncertain files are left unassigned, never force-fit. The result is a draft overlay the
     faculty reviews.

`kind` (reading/slides/…) and `role` (framing/content) are derived deterministically from the filename,
exactly as the deterministic proposer does — the model is asked only for the hard part: which week.
"""

import json
from pathlib import Path

from coursekit import courseconfig
from coursekit.ingest.extract import extract_text
from coursekit.ingest.propose import Proposal, _source_entry, _sort_sources, _week_num_of, scan_supported

_PEEK_CHARS = 240

_ASSIGN_SPEC = {
    "name": "assign_week",
    "description": ("Assign a group of the listed files to one week. Call once per week. Use ONLY "
                    "paths from the file list — never invent a path. Omit a file you cannot place."),
    "parameters": {
        "type": "object",
        "properties": {
            "number": {"type": "integer", "description": "The week number (1-based)."},
            "title": {"type": "string", "description": "A short topic title for the week, e.g. 'Exposure'."},
            "source_paths": {
                "type": "array", "items": {"type": "string"},
                "description": "Relative paths of this week's files, copied verbatim from the list.",
            },
        },
        "required": ["number", "source_paths"],
        "additionalProperties": False,
    },
}

_SYSTEM = (
    "You organize a course's existing raw materials into weeks. You are given the EXACT list of files "
    "that exist; your job is to group them.\n"
    "Rules:\n"
    "- Call assign_week(number, title, source_paths) once per week. Copy paths VERBATIM from the list; "
    "never invent a path or a file.\n"
    "- Group by topic and by any order the materials already imply (numbered folders, a syllabus, "
    "ordinals in filenames). Preserve that order; if none exists, use a sensible reading order and "
    "know the instructor will review it.\n"
    "- Leave a file OUT if you cannot confidently place it — do not force-fit. Unplaced files are "
    "reported for the instructor, which is fine.\n"
    "- Describe what EXISTS. Do not invent content, and do not decide what SHOULD be taught or design a "
    "new sequence — only arrange the files given."
)


def _peek(p: Path) -> str:
    try:
        text = " ".join(extract_text(p).split())
    except Exception:
        return ""
    return text[:_PEEK_CHARS]


def build_manifest(files: list[Path], root: Path | None, *, deep: bool = False) -> str:
    """The file list the model reasons over — relative paths, optionally each with a short content peek."""
    lines = []
    for p in files:
        rel = _rel(p, root)
        lines.append(f"- {rel}")
        if deep:
            peek = _peek(p)
            if peek:
                lines.append(f"    | {peek}")
    return "\n".join(lines)


def _rel(p: Path, root: Path | None) -> str:
    try:
        return str(p.relative_to(root)) if root else p.name
    except ValueError:
        return p.name


def propose_with_model(path, provider, model, *, deep: bool = False) -> Proposal:
    """Group a course's files into weeks with a local model. Returns the same `Proposal` the
    deterministic proposer does — validated so every assigned path is a real file."""
    root, files = scan_supported(path)
    if not files:
        return Proposal(weeks={}, unassigned=[], root=root)

    by_rel = {_rel(p, root): p for p in files}
    domain = courseconfig.load(path, config_name="quiz.yaml").domain
    user = (f"COURSE DOMAIN: {domain}\n\n" if domain else "") + \
        f"Files (relative to the course root):\n{build_manifest(files, root, deep=deep)}"
    reply = provider.chat_with_tools(
        model=model,
        messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
        tools=[_ASSIGN_SPEC],
    )

    weeks: dict = {}
    assigned: set = set()
    for call in (reply.tool_calls or []):
        if call.name != "assign_week":
            continue
        try:
            args = json.loads(call.arguments or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(args, dict):
            continue
        num = courseconfig.week_key(str(args.get("number")))
        if not num:
            continue
        valid = [by_rel[pp] for pp in (args.get("source_paths") or []) if pp in by_rel]
        if not valid:
            continue
        entry = weeks.setdefault(f"week {num}", {"sources": []})
        if args.get("title") and "title" not in entry:
            entry["title"] = str(args["title"])
        for p in valid:
            if p not in assigned:
                entry["sources"].append(_source_entry(p, root))
                assigned.add(p)

    for entry in weeks.values():
        _sort_sources(entry)
    weeks = {k: {"title": v["title"], "sources": v["sources"]} if "title" in v else {"sources": v["sources"]}
             for k, v in sorted(weeks.items(), key=lambda kv: _week_num_of(kv[0]))}
    unassigned = [p for p in files if p not in assigned]
    return Proposal(weeks=weeks, unassigned=unassigned, root=root)
