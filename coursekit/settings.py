"""The settings API — every write to a coursekit-owned `.vtconfig/` file goes through here (CORE-1.4).

Faculty shouldn't have to edit the fragile YAML by hand: an interface calls these functions instead.
Each write is load → apply → validate the WHOLE file against its schema (`coursekit.schemas`) →
atomic replace. An invalid value raises a `CoursekitError` and leaves the file byte-identical, so
nothing written through here can fail `coursekit check`.

Two layers, one per kind of interface:

- **Whole documents** — `read(root, doc)` / `write(root, doc, data)` — for a GUI form that edits a
  file's settings and saves them together. `doc` is a short name (`quiz`, `page`, `evaluate`,
  `ingest`, `assignment`, `style`, `structure`) or `pages/<name>` for a page's supplements.
- **Dotted paths** — `get` / `set` / `unset` — for the CLI (`coursekit config set quiz.eu_question
  true`). The first segment names the document; `grading`, `expect`, and `weeks` live in the
  structure overlay, so `grading.groups.Projects.weight` works without naming the file. A list of
  named items (grading groups) is addressed by name; other lists by index.

`context.yaml` is the transcriber's file (one writer per file) and is never written here. Comments in a
file don't survive a write — PyYAML drops them — so a writer that wants a note at the top passes it as
`header`; anything that must persist belongs in a setting, not a comment.
"""

import os
from pathlib import Path

import yaml

from coursekit import courseconfig, schemas
from coursekit.outcomes import CoursekitError

DOCS = {
    "quiz": "quiz.yaml",
    "page": "page.yaml",
    "evaluate": "evaluate.yaml",
    "ingest": "ingest.yaml",
    "assignment": "assignment.yaml",
    "style": "style.yaml",
    "structure": "structure.coursekit.yaml",
}
_OVERLAY_SECTIONS = ("weeks", "grading", "expect")      # top-level keys of the structure overlay


def _list_fields(model, seen=None) -> frozenset:
    """Every field name, anywhere in the schemas, that holds a list — so a path that creates a missing
    container makes a list where the schema wants one (`grading.groups`), a mapping otherwise."""
    from typing import get_args, get_origin
    from pydantic import BaseModel
    seen = seen if seen is not None else []
    if model in seen:
        return frozenset()
    seen.append(model)
    out = frozenset()
    for name, f in model.model_fields.items():
        if get_origin(f.annotation) is list:
            out |= {name}
        for arg in (*get_args(f.annotation), f.annotation):
            for inner in (*get_args(arg), arg):
                if isinstance(inner, type) and issubclass(inner, BaseModel):
                    out |= _list_fields(inner, seen)
    return out


_LIST_FIELDS = frozenset().union(*(_list_fields(m) for m in (*schemas.SETTINGS.values(), schemas.Supplements)))


def _doc(root, doc: str) -> tuple[Path, type]:
    vt = Path(root) / courseconfig.VTCONFIG_DIR_NAME
    if doc.startswith("pages/") and len(doc) > len("pages/"):
        return vt / "pages" / f"{doc.removeprefix('pages/')}.yaml", schemas.Supplements
    if doc in DOCS:
        return vt / DOCS[doc], schemas.SETTINGS[DOCS[doc]]
    if doc == "context":
        raise CoursekitError("context.yaml belongs to the transcriber — coursekit never writes it.",
                             code="settings.not_owned", details={"doc": doc})
    raise CoursekitError(f"no settings document {doc!r} — use one of: {', '.join(DOCS)}, or pages/<name>",
                         code="settings.unknown_doc", details={"doc": doc, "allowed": list(DOCS)})


def read(root, doc: str) -> dict:
    """A document's settings, validated ({} when its file doesn't exist yet)."""
    path, model = _doc(root, doc)
    data = schemas.read_yaml(path)
    return schemas.validate(path, data, model).model_dump(exclude_defaults=True) if data else {}


def write(root, doc: str, data: dict, *, header: str = "") -> dict:
    """Replace a document's settings with `data`: validate everything, then atomically replace the file.
    Raises (leaving the file untouched) if anything is invalid. Returns the settings as stored."""
    path, model = _doc(root, doc)
    stored = schemas.validate(path, data, model).model_dump(exclude_defaults=True)
    body = yaml.safe_dump(stored, sort_keys=False, allow_unicode=True, default_flow_style=False) if stored else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(header + body, encoding="utf-8")
    os.replace(tmp, path)                                   # atomic: readers see old or new, never half
    return stored


# --------------------------------------------------------------- dotted paths (the CLI's view)
def _split(key: str) -> tuple[str, list[str]]:
    parts = [p for p in key.split(".") if p]
    if not parts:
        raise CoursekitError("no setting named — e.g. quiz.eu_question", code="settings.bad_key")
    if parts[0] in _OVERLAY_SECTIONS:
        return "structure", parts
    if parts[0] == "pages" and len(parts) >= 2:
        return f"pages/{parts[1]}", parts[2:]
    return parts[0], parts[1:]


def _child(node, seg: str, *, create: bool):
    """Step into `node` by one path segment. Lists of named items (dicts with a `name`) are addressed
    by name; other lists by index. With `create`, a missing dict key or named item is added."""
    if isinstance(node, dict):
        if seg not in node and create:
            node[seg] = [] if seg in _LIST_FIELDS else {}
        return node.get(seg)
    if isinstance(node, list):
        if seg.isdigit() and int(seg) < len(node):
            return node[int(seg)]
        for item in node:
            if isinstance(item, dict) and str(item.get("name")) == seg:
                return item
        if create:
            node.append({"name": seg})
            return node[-1]
    return None


def _walk(data: dict, parts: list[str], key: str, *, create: bool = False):
    node = data
    for seg in parts:
        node = _child(node, seg, create=create)
        if node is None:
            raise CoursekitError(f"no setting {key!r}", code="settings.no_such_key", details={"key": key})
    return node


def get(root, key: str):
    doc, parts = _split(key)
    data = read(root, doc)
    return _walk(data, parts, key) if parts else data


def set(root, key: str, value) -> dict:            # noqa: A001 — the verb is the API
    """Set one setting and save the document (validated as a whole). Creates the file, a missing
    section, or a missing named list item as needed."""
    doc, parts = _split(key)
    if not parts:
        raise CoursekitError(f"{key!r} names a whole document — give a setting inside it, e.g. {key}.<setting>",
                             code="settings.bad_key", details={"key": key})
    data = read(root, doc)
    parent = _walk(data, parts[:-1], key, create=True)
    last = parts[-1]
    if isinstance(parent, dict):
        parent[last] = value
    elif last.isdigit():
        if int(last) >= len(parent):
            raise CoursekitError(f"no item {last} in {key.rsplit('.', 1)[0]!r}", code="settings.no_such_key",
                                 details={"key": key})
        parent[int(last)] = value
    else:                                                   # a named item: set its fields
        if not isinstance(value, dict):
            raise CoursekitError(f"{key!r} is a whole item — set one of its fields, e.g. {key}.weight",
                                 code="settings.bad_key", details={"key": key})
        _child(parent, last, create=True).update(value)
    return write(root, doc, data)


def unset(root, key: str) -> dict:
    """Remove one setting (or a named list item) and save. Removing what isn't there is an error."""
    doc, parts = _split(key)
    data = read(root, doc)
    parent = _walk(data, parts[:-1], key) if parts[:-1] else data
    last = parts[-1] if parts else None
    if isinstance(parent, dict) and last in parent:
        del parent[last]
    elif isinstance(parent, list) and (item := _child(parent, last, create=False)) is not None:
        parent.remove(item)
    else:
        raise CoursekitError(f"no setting {key!r}", code="settings.no_such_key", details={"key": key})
    return write(root, doc, data)


def propose_section(root, section: str, value, *, force: bool = False, header: str = "") -> Path:
    """Write one structure-overlay section a proposer drafted (`weeks`, `grading`, `expect`), keeping the
    other sections. A section that is already declared may hold the faculty's edits, so it is replaced
    only with `force`. Validated and saved like any other write. Returns the overlay's path."""
    path, _ = _doc(root, "structure")
    data = read(root, "structure")
    if data.get(section) and not force:
        raise CoursekitError(f"{path} already declares `{section}:` — pass --force to redraft it (discards your "
                             f"edits to that section; the others are kept).", code="overlay.section_exists",
                             details={"path": str(path), "section": section})
    data[section] = value
    write(root, "structure", data, header=header)
    return path


def check(root):
    """Every settings file validated — see `schemas.check`."""
    return schemas.check(root)
