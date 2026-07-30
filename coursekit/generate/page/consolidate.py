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


def consolidate(wk: WeekKnowledge, provider, model: str, *, week: str = "", domain: str = "",
                project_root=None) -> ConceptMap:
    """Roll a raw `WeekKnowledge` bundle up into a `ConceptMap` via the model. The week label is set
    by us, not the model — one less thing for it to get wrong. A week with no knowledge components
    short-circuits to an empty map (the caller falls back to inline derivation) without a model call."""
    week = week or wk.week
    if not wk.kcs:
        return ConceptMap(week=week)
    system = prompts.load(PAGE_CATEGORY, "consolidate", project_root=project_root)
    system_message = courseconfig.domain_preface(domain) + system.body
    messages = [{"role": "system", "content": system_message},
                {"role": "user", "content": _bundle_for_prompt(wk)}]
    reply = provider.chat(model=model, messages=messages, temperature=READ_TEMPERATURE)
    data = _extract_json(reply)
    data["week"] = week
    return ConceptMap.model_validate(data)


def build_concept_map(path, provider, model: str, *, week: str = "", domain: str = "",
                      project_root=None) -> ConceptMap:
    """End-to-end for one week: read the sibling `knowledge.json` files → consolidate → `ConceptMap`.
    `path` is the week doc or its directory; save it with `concept_map.save_concept_map`."""
    wk = read_week_knowledge(path, week=week)
    return consolidate(wk, provider, model, week=week, domain=domain, project_root=project_root)
