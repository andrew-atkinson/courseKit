"""Prompt construction for the page generator.

Mirrors the quiz `context.py`: a pure function that loads `prompts/page/*.md` through
`coursekit.prompts` (so a course can override the brief) and weaves in optional week metadata. No
env or file I/O at import.
"""

from coursekit import courseconfig, prompts
from coursekit.generate import catalog

PAGE_CATEGORY = "page"

# NOTE (2026-08-06): the page `--detail brief|medium|full` knob was REMOVED. Length is a FUNCTION,
# not a dial (overview/glossary are the short artifacts; a shorter teaching page is the depth-planner),
# and the choice of monolithic vs decompose is now the program's (see generate/page/route.py). The
# page's length is grounded by the concept map's one-section-per-concept checklist below.


def _concept_directive(concept_map) -> str:
    """Turn a consolidated concept map into an explicit, un-skippable teaching checklist for the
    model — the whole point of the map. It grounds page length in the concept COUNT (one section
    each), names the concrete material each concept must carry, and hands the pullquote its enduring
    understanding. Empty string when there is no map (the page falls back to inline derivation)."""
    if concept_map is None or not concept_map.concepts:
        return ""
    lines = ["\n\nThe week teaches these concepts — give EACH its own section with a real explanation "
             "and, where the material supports it, a worked example. Cover every one; skip none:"]
    for i, c in enumerate(concept_map.concepts, 1):
        gist = f" — {c.gist}" if c.gist else ""
        kinds = list(dict.fromkeys(m.kind for m in c.key_material))
        needs = f"  [include its {', '.join(kinds)}]" if kinds else ""
        lines.append(f"  {i}. {c.name}{gist}{needs}")
        if c.components:
            lines.append(f"       covering: {', '.join(c.components)}")
    lines.append("\nThe parts under each concept are what its section must actually cover. Where a "
                 "part is a method, an operation, or a named term, INTRODUCE it the first time it "
                 "appears — show and name it — rather than only using it in later code.")
    if concept_map.enduring_understanding:
        lines.append(f'\nForeground this one idea as the page\'s pullquote: '
                     f'"{concept_map.enduring_understanding}"')
    return "\n".join(lines)


def _context_line(course_title, week_label, module) -> str:
    """A single factual line placing the week, or '' when nothing is known."""
    parts = []
    if week_label:
        parts.append(week_label)
    if module:
        parts.append(module)
    if course_title:
        parts.append(f"course: {course_title}")
    if not parts:
        return ""
    return "\nWeek context — " + "; ".join(parts) + ".\n"


def build_messages(transcript: str, *, course_title: str | None = None,
                   week_label: str | None = None, module: str | None = None,
                   project_root=None, system_prompt: str = "system",
                   task_prompt: str = "task", domain: str = "", voice: str = "",
                   concept_map=None) -> list[dict]:
    """The chat messages for one page. A course overrides either prompt from its own
    .vtconfig/prompts/page/, and its domain profile is prepended when present. When a consolidated
    `concept_map` is present, its concepts become an explicit teaching checklist that grounds the
    page's length and sections (one section per concept)."""
    system = prompts.load(PAGE_CATEGORY, system_prompt, project_root=project_root)
    task = prompts.load(PAGE_CATEGORY, task_prompt, project_root=project_root)

    body = system.body.format(
        context_line=_context_line(course_title, week_label, module),
        transcript=transcript,
        palette=catalog.render_palette("page"),
    )
    system_message = ("\n" + courseconfig.domain_preface(domain)
                      + courseconfig.voice_preface(voice) + body + "\n")
    task_body = task.body + _concept_directive(concept_map)
    return [{"role": "system", "content": system_message},
            {"role": "user", "content": "\n" + task_body + "\n"}]
