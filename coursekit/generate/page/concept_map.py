"""The concept map: a per-week *content* contract — the analog of course-level `context.yaml`.

`context.yaml` describes a course's **structure** (weeks, modules, titles); the concept map
describes a week's **content** — what it teaches — with the identical lifecycle: auto-seeded,
instructor-editable, living in `.vtconfig/`, read by both generators *and* the evaluator. It exists
to stop "the week's concepts" being re-derived from prose on every generation (the extraction wobble,
and the concepts a dense page silently skips): the concepts become an explicit list the generator
can't skip a member of, and the concept-delivery evaluator scores against a fixed list rather than
one it re-guesses each read.

**Three tiers, from the pedagogy literature — and the raw material for the lower two already exists.**
The transcriber's Extract stage writes a `.knowledge.json` beside every source (video/reading/slides),
so this module *reads and consolidates*; it does not extract from scratch.

    [ ENDURING UNDERSTANDING ]   the transferable big idea (UbD) — above any one concept; drives the
             ▲                    page's pullquote. The ONLY tier not in knowledge.json — a synthesis.
    [   CONCEPT MAP (nodes+edges) ]   the structural bridge (Novak). A node is a teaching concept /
             ▲                    learning objective — what a page section teaches and what gets
                                  scored; an edge is a `prerequisites` / `teaches_toward` relation.
    [   KNOWLEDGE COMPONENTS   ]   the micro-units (KLI) — the fine per-source concepts from
                                  knowledge.json, rolled up (nested) under a node, nothing discarded.

Read the diagram *upward* and it is the consolidation pass (gather KCs → form the map → synthesize
the understanding); read it *downward* and it is the page's teaching order (lead with the
understanding, teach each node with its KCs, prerequisites before dependents).

This module owns the schema, the deterministic reader/aggregator over `knowledge.json` (which
produces the *raw* pre-consolidation bundle), and the editable-artifact IO. The consolidation pass
itself (KCs → nodes + the enduring understanding) is a model step and lives with the generator.
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

# knowledge.json names its concrete examples differently by domain: the `coding` extract prompt uses
# `code_examples`, the subject-neutral default uses `examples_and_demonstrations`. Read either.
_EXAMPLE_KEYS = ("code_examples", "examples_and_demonstrations")
KNOWLEDGE_SUFFIX = ".knowledge.json"


# ------------------------------------------------------------- the schema (consolidated form)

class KeyMaterial(BaseModel):
    """Domain-specific concrete material a concept can't be taught faithfully without — the general
    form of "has code". `kind` is an OPEN, domain-named label (code, image, statute, quotation,
    case study, atomic diagram, …), never an enum, matching the "make no assumptions about the
    subject" discipline. `fidelity` is the handling instruction — how exactly it must be reproduced;
    `verbatim` material is the same class as a link (source-supplied, never invented), so it both
    steers the generator and aims the facticity critic at where correctness matters most."""
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(min_length=1)
    fidelity: str = "faithful"  # verbatim | faithful | illustrative


class Concept(BaseModel):
    """A node in the concept map — one teaching concept / learning objective (the consolidated level,
    ~6 per week). Its `components` are the knowledge components rolled up underneath it; its
    `prerequisites` / `teaches_toward` are the map's edges, within a week and across weeks."""
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    gist: str = ""                                   # a one-line explanation (why it matters)
    level: str | None = None                         # Bloom verb: remember | understand | apply | …
    components: list[str] = Field(default_factory=list)      # the KCs (from knowledge.json)
    key_material: list[KeyMaterial] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)   # edges — concepts assumed known
    teaches_toward: list[str] = Field(default_factory=list)  # edges — concepts this enables
    sources: list[str] = Field(default_factory=list)         # video | reading | slides | pdf ids


class ConceptMap(BaseModel):
    """The per-week artifact. `enduring_understanding` is the macro-insight above the nodes (UbD) —
    a synthesis, the most instructor-authored field, and the page's pullquote source."""
    model_config = ConfigDict(extra="forbid")
    week: str = Field(min_length=1)
    enduring_understanding: str = ""
    concepts: list[Concept] = Field(default_factory=list)


# ------------------------------- the raw, pre-consolidation bundle (what consolidation reads) ------

class KnowledgeComponent(BaseModel):
    """One knowledge.json concept, kept whole for the consolidation pass to group into nodes."""
    model_config = ConfigDict(extra="forbid")
    name: str
    gist: str = ""
    source: str = ""            # the source stem this KC came from


class WeekKnowledge(BaseModel):
    """The deterministic aggregate of a week's `knowledge.json` files — the input to consolidation,
    not yet a concept map. Nothing here is judged: KCs are unioned across sources, edges merged,
    material kinds collected, sources listed. Consolidation (a model step) turns this into a
    `ConceptMap` by grouping KCs into nodes and synthesizing the enduring understanding."""
    model_config = ConfigDict(extra="forbid")
    week: str = ""
    kcs: list[KnowledgeComponent] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    teaches_toward: list[str] = Field(default_factory=list)
    key_material: list[KeyMaterial] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


def _dedup(items) -> list[str]:
    """Union preserving first-seen order, case-insensitive — the same term surfaces from several
    sources and we want it once, in the order the week introduces it."""
    seen, out = set(), []
    for it in items:
        key = (it or "").strip().casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(it.strip())
    return out


def _material_from(knowledge: dict) -> list[KeyMaterial]:
    """Collect concrete-material kinds from a knowledge.json. Code examples are `verbatim` (they must
    be reproduced exactly); the neutral `examples_and_demonstrations` carry their own open `kind` and
    default to `faithful`. Consolidation assigns these to the right node and may refine fidelity."""
    out = []
    for ex in knowledge.get("code_examples") or []:
        lang = (ex.get("language") or "code").strip()
        out.append(KeyMaterial(kind="code" if lang in ("", "code") else lang, fidelity="verbatim"))
    for ex in knowledge.get("examples_and_demonstrations") or []:
        kind = (ex.get("kind") or "example").strip()
        out.append(KeyMaterial(kind=kind, fidelity="faithful"))
    return out


def read_week_knowledge(path, *, week: str = "") -> WeekKnowledge:
    """Aggregate every `*.knowledge.json` beside a week doc into the raw pre-consolidation bundle.

    `path` may be the week doc itself (`output/week 3/week-3.md`) or its directory; either way the
    knowledge files are its siblings. Missing or malformed files are skipped, not fatal — a partial
    week still yields a usable bundle. Returns an empty bundle when none are found (a course with no
    transcriber output falls back to the model-pass extractor, not to this reader)."""
    p = Path(path)
    folder = p if p.is_dir() else p.parent
    kcs, prereqs, toward, material, sources = [], [], [], [], []
    for kf in sorted(folder.glob(f"*{KNOWLEDGE_SUFFIX}")):
        try:
            data = json.loads(kf.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        stem = kf.name[: -len(KNOWLEDGE_SUFFIX)]
        sources.append(stem)
        for c in data.get("concepts") or []:
            name = (c.get("name") or "").strip()
            if name:
                kcs.append(KnowledgeComponent(
                    name=name, gist=(c.get("why_it_matters") or c.get("explanation") or "").strip(),
                    source=stem))
        prereqs += data.get("prerequisites") or []
        toward += data.get("leads_to") or []
        material += _material_from(data)
    # Dedup material by (kind, fidelity) — the same kind recurs across sources.
    seen_mat, uniq_mat = set(), []
    for m in material:
        key = (m.kind.casefold(), m.fidelity)
        if key not in seen_mat:
            seen_mat.add(key)
            uniq_mat.append(m)
    return WeekKnowledge(week=week, kcs=kcs, prerequisites=_dedup(prereqs),
                         teaches_toward=_dedup(toward), key_material=uniq_mat, sources=sources)


# ------------------------------------------------------------- editable-artifact IO

def concept_map_path(course_root, week_key: str) -> Path:
    """Where a week's concept map lives: `.vtconfig/concepts/week-<key>.yaml`, beside the pages
    supplements — instructor-editable, the same `.vtconfig/` home as `context.yaml` and `domain.md`."""
    return Path(course_root) / ".vtconfig" / "concepts" / f"week-{week_key}.yaml"


def load_concept_map(path) -> ConceptMap | None:
    """Read a concept map from its yaml, or None if absent (enrichment — its absence is never an
    error; the generator falls back to inline derivation). A *present but invalid* file raises, so a
    broken hand-edit is surfaced loudly rather than silently ignored."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        import yaml  # guarded: a machine without pyyaml degrades to "no map", like courseconfig
    except ImportError:
        return None
    data = yaml.safe_load(p.read_text()) or {}
    return ConceptMap.model_validate(data)


def save_concept_map(cm: ConceptMap, path) -> Path:
    """Write a concept map to its yaml, creating `.vtconfig/concepts/` if needed. Block style with
    field order preserved, so an instructor edits a readable file, not a flow-style blob."""
    import yaml
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    dumped = yaml.safe_dump(cm.model_dump(exclude_none=True), sort_keys=False,
                            default_flow_style=False, allow_unicode=True)
    p.write_text(dumped)
    return p
