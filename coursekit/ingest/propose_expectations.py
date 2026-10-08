"""Expectation proposer (FLOW-9 Phase 1.5, Layer A) — draft an `expect:` block from the course's OWN
signals, offline. Two deterministic sub-layers:

  L0 — structural induction (from the census): a type present in a strict MAJORITY of generating weeks
       becomes a week-scoped rule ("each week: 1 page"); a SPARSE type is NOT fabricated into a rule —
       it's flagged as a decision ("assignments appear once — declare a cadence?").
  L1-deterministic — concept-map rules (the concept map already encodes the pedagogy structure, so these
       are lookups, not model reasoning): a week marking an enduring understanding → expect an EU
       assessment (UbD); a concept-DENSE week → expect a glossary page (CLT). Each carries a rationale
       citing the framework + the map fact. (A "review week → recap" rule is judgmental → deferred to the
       L1-MODEL layer, not here.)

The draft is written merge-aware into `structure.coursekit.yaml` (preserving `weeks:`/`grading:`), with
the rationale as comments; the faculty owns it by editing. The model enters only for L1's residual + L2.
"""

from pathlib import Path

from coursekit import courseconfig
from coursekit.ingest.propose import overlay_path

# ponytail: a density threshold is a heuristic; 8 concepts ≈ "dense enough that a glossary helps" (CLT).
GLOSSARY_THRESHOLD = 8


def _load_cm(root: Path, week: str):
    """The week's concept map, or None. Offline, never raises."""
    from coursekit.generate.page.concept_map import concept_map_path, load_concept_map
    try:
        return load_concept_map(concept_map_path(root, week))
    except Exception:
        return None


def propose_expectations(path) -> tuple[dict, list[str]]:
    """Draft an `expect:` dict + human-readable notes (rationale + flagged decisions) from the course's
    own signals. Pure/offline."""
    from coursekit import census as cen

    root = courseconfig.find_root(Path(path).expanduser()) or Path(path).expanduser().resolve()
    c = cen.build_census(path)
    generating = [w for w in c.weeks if w.has_any_artifact()]
    n = len(generating)
    defaults, notes = [], []

    # L0 — modal induction over generating weeks
    for art, attr in (("page", "pages"), ("quiz", "quizzes"), ("concept-map", "concept_map")):
        cnt = sum(1 for w in generating if getattr(w, attr))
        if n and cnt * 2 > n:
            defaults.append({"scope": "week", "artifact": art, "count": 1})
            notes.append(f"{art}: each week — high confidence (modal: {cnt}/{n} weeks have one)")

    a_weeks = sum(1 for w in generating if w.assignments)
    a_total = sum(w.assignments for w in c.weeks)
    if a_total and a_weeks * 2 > n:                      # assignments are themselves the norm
        defaults.append({"scope": "week", "artifact": "assignment", "count": 1})
        notes.append(f"assignment: each week — modal ({a_weeks}/{n})")
    elif a_total:                                        # sparse → a flagged decision, NOT a fabricated rule
        notes.append(f"assignment: appears {a_total}x (sparse, not the norm) — DECISION NEEDED: declare a "
                     f"cadence (per module / per course / none). Add a rule by hand; coursekit won't guess it.")

    # L1-deterministic — concept-map rules
    overrides_week: dict = {}
    cm_weeks, eu_weeks = [], []
    for w in c.weeks:
        cm = _load_cm(root, w.week)
        if cm is None:
            continue
        cm_weeks.append(w.week)
        if getattr(cm, "enduring_understanding", ""):
            eu_weeks.append(w.week)
        n_concepts = len(getattr(cm, "concepts", []))
        if n_concepts >= GLOSSARY_THRESHOLD:
            overrides_week.setdefault(w.week, {})["page:glossary"] = 1
            notes.append(f"week {w.week}: page:glossary — CLT (dense: {n_concepts} concepts)")

    if eu_weeks and len(eu_weeks) == len(cm_weeks):      # universal → promote to a week-default
        defaults.append({"scope": "week", "artifact": "quiz:eu", "count": 1})
        notes.append("quiz:eu: each week — UbD (every concept-mapped week marks an enduring understanding)")
    else:
        for wk in eu_weeks:                               # otherwise per-week overrides
            overrides_week.setdefault(wk, {})["quiz:eu"] = 1
            notes.append(f"week {wk}: quiz:eu — UbD (marks an enduring understanding)")

    expect: dict = {"defaults": defaults}
    if overrides_week:
        expect["overrides"] = {"week": overrides_week}
    return expect, notes


_HEADER = (
    "# coursekit expectations overlay (FLOW-9 Phase 1.5, Layer A) — what each scope SHOULD contain, so\n"
    "# the census can report real gaps. This is a DRAFT proposed from the course's own signals; edit it\n"
    "# freely (it's your declaration). Rationale for each proposed rule:\n")


def write_expectations(path, expect: dict, notes: list[str], *, force: bool = False) -> Path:
    """Merge `expect` into the overlay, PRESERVING `weeks`/`grading`. Refuse to overwrite an existing
    `expect` block without `force`."""
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
    if data.get("expect") and not force:
        raise SystemExit(f"{dest} already declares `expect:` — pass --force to redraft (discards hand edits).")
    data["expect"] = expect
    header = _HEADER + "".join(f"#   - {note}\n" for note in notes) + "\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return dest
