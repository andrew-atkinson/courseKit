"""The consolidation pass: a week's raw knowledge components → a consolidated `ConceptMap`.

This is the model step in the concept-map pipeline (the diagram read *upward*): `concept_map.py`
gathers the fine knowledge components from the transcriber's `knowledge.json` deterministically, and
this rolls them up into the ~handful of teaching concepts a page section teaches, plus the one
enduring understanding above them. It lives with the generator, not in `concept_map.py`, because it
is generation — domain-aware, model-driven — the same reason the page brief lives in `context.py`.

JSON in, JSON out: the input bundle is JSON (knowledge.json), the model returns a JSON concept map,
and pydantic validates it — the same shape as the transcriber's own extract stage, which this local
model already does reliably. The consolidated map is then the contract every downstream reader uses.
"""

import json
import re

from coursekit import courseconfig, prompts
from coursekit.generate.page.concept_map import ConceptMap, WeekKnowledge, read_week_knowledge
from coursekit.generate.quiz.evaluate import READ_TEMPERATURE

PAGE_CATEGORY = "page"


def _bundle_for_prompt(wk: WeekKnowledge) -> str:
    """Render the raw bundle as the grounded input the model consolidates — the knowledge components
    with their source, and the week's merged edges and material kinds. Readable, not JSON, so the
    model reads it as material to analyse rather than a structure to echo back."""
    lines = ["Knowledge components (fine-grained concepts, one per line, with the source they came "
             "from):"]
    for k in wk.kcs:
        gist = f" — {k.gist}" if k.gist else ""
        src = f"  [source: {k.source}]" if k.source else ""
        lines.append(f"- {k.name}{src}{gist}")
    lines.append("")
    lines.append(f"Prerequisites (assumed knowledge): {', '.join(wk.prerequisites) or '(none)'}")
    lines.append(f"Teaches toward (what these enable): {', '.join(wk.teaches_toward) or '(none)'}")
    mats = ", ".join(f"{m.kind} ({m.fidelity})" for m in wk.key_material) or "(none)"
    lines.append(f"Concrete material present: {mats}")
    lines.append(f"Sources: {', '.join(wk.sources) or '(none)'}")
    return "\n".join(lines)


def _extract_json(reply: str) -> dict:
    """Pull the JSON object from a model reply, tolerating a ```json fence or surrounding prose —
    a small local model wraps its output inconsistently. Raises ValueError with the raw reply when no
    JSON object can be read, so a build failure is legible rather than a bare JSONDecodeError."""
    s = (reply or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.DOTALL)
    if fence:
        s = fence.group(1)
    elif not s.startswith("{"):
        i, j = s.find("{"), s.rfind("}")
        if i != -1 and j > i:
            s = s[i:j + 1]
    try:
        data = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"consolidation did not return valid JSON: {e}\n---\n{reply}") from e
    if not isinstance(data, dict):
        raise ValueError(f"consolidation returned {type(data).__name__}, expected an object\n---\n{reply}")
    return data


def _messages(prompt_name: str, user_content: str, *, domain: str, project_root) -> list[dict]:
    system = prompts.load(PAGE_CATEGORY, prompt_name, project_root=project_root)
    return [{"role": "system", "content": courseconfig.domain_preface(domain) + system.body},
            {"role": "user", "content": user_content}]


def _parse(reply: str, week: str) -> ConceptMap:
    """The model's reply → a validated `ConceptMap`. The week label is set by us, not the model — one
    less thing for it to get wrong."""
    data = _extract_json(reply)
    data["week"] = week
    return ConceptMap.model_validate(data)


def _call(prompt_name: str, user_content: str, provider, model: str, *, week: str, domain: str,
          project_root) -> ConceptMap:
    """Shared model call: domain-aware system prompt + a user message → a validated `ConceptMap`."""
    messages = _messages(prompt_name, user_content, domain=domain, project_root=project_root)
    return _parse(provider.chat(model=model, messages=messages, temperature=READ_TEMPERATURE), week)


def _material(text: str) -> str:
    return f"The week's teaching material:\n<material>\n{text}\n</material>"


def consolidate(wk: WeekKnowledge, provider, model: str, *, week: str = "", domain: str = "",
                project_root=None) -> ConceptMap:
    """Roll a raw `WeekKnowledge` bundle (the transcriber's knowledge.json) up into a `ConceptMap`. A
    week with no knowledge components short-circuits to an empty map without a model call — the caller
    falls back to `build_concept_map_from_text` (or inline derivation)."""
    week = week or wk.week
    if not wk.kcs:
        return ConceptMap(week=week)
    return _call("consolidate", _bundle_for_prompt(wk), provider, model,
                 week=week, domain=domain, project_root=project_root)


def build_concept_map_from_text(text: str, provider, model: str, *, week: str = "", domain: str = "",
                                project_root=None) -> ConceptMap:
    """The fallback producer for a course with NO transcriber knowledge.json: read the week's teaching
    text directly and build the same `ConceptMap` (identify concepts, roll up components, name the
    enduring understanding). Same schema, same downstream consumers — only the source differs."""
    return _call("extract", _material(text), provider, model, week=week, domain=domain, project_root=project_root)


def build_concept_map(path, provider, model: str, *, week: str = "", domain: str = "",
                      project_root=None) -> ConceptMap:
    """End-to-end for one week: read the sibling `knowledge.json` files → consolidate → `ConceptMap`.
    Falls back to extracting from the week text when there is no knowledge.json. `path` is the week doc
    or its directory; save the result with `concept_map.save_concept_map`."""
    wk = read_week_knowledge(path, week=week)
    if wk.kcs:
        return consolidate(wk, provider, model, week=week, domain=domain, project_root=project_root)
    from pathlib import Path
    text = Path(path).read_text(encoding="utf-8") if Path(path).is_file() else ""
    return build_concept_map_from_text(text, provider, model, week=week, domain=domain,
                                       project_root=project_root)


# --------------------------------------------------------------------------- `analyze`, one unit
def analyze_brief(unit) -> list[dict]:
    """What `analyze` shows the model for `unit`: the transcriber's knowledge components when there are
    any, else the unit's own text. The run and a record's check both build it here (CORE-4.2)."""
    from pathlib import Path

    from coursekit import records
    cfg = courseconfig.load(unit.transcript_path, config_name="page.yaml")
    wk = read_week_knowledge(unit.transcript_path, week=unit.week_label or unit.week_slug)
    if wk.kcs:
        return _messages("consolidate", _bundle_for_prompt(wk), domain=cfg.domain, project_root=unit.course_root)
    records.note(unit.transcript_path)
    text = Path(unit.transcript_path).read_text(encoding="utf-8")
    return _messages("extract", _material(text), domain=cfg.domain, project_root=unit.course_root)


def analyze_unit(unit, provider, model: str):
    """`analyze` for one unit: build its concept map and save it, then split its text into per-concept
    material beside it (best-effort — a failure only warns, and decomposition falls back to slicing).
    Each step is recorded. Returns (map, path, material spans written)."""
    from coursekit import outcomes, records
    from coursekit.generate.page import concept_map as cmap
    from coursekit.generate.page import record
    from coursekit.generate.page import segment as seg

    with records.reading() as read:
        messages = analyze_brief(unit)
    cm = _parse(provider.chat(model=model, messages=messages, temperature=READ_TEMPERATURE),
                unit.week_label or unit.week_slug)
    path = cmap.save_concept_map(cm, cmap.concept_map_path(unit.course_root, unit.week_num))
    record.write_map(unit, "analyze", messages, read, model, fresh=True)
    try:
        with records.reading() as read:
            plan = seg.brief(unit)
        mats = seg.segment(plan, provider, model) if plan else {}
        if mats:
            seg.save_materials(mats, seg.materials_path(unit.course_root, unit.week_num))
            record.write_map(unit, "segment", plan[2], read, model)
    except Exception as e:
        mats = {}
        outcomes.warn("analyze.segment_skipped", f"  (segmentation skipped for {unit.week_label or unit.week_slug}: "
                                                 f"{type(e).__name__}: {e})", unit=unit.week_slug)
    return cm, path, len(mats)
