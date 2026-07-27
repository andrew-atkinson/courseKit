"""Prompt construction for the page generator.

Mirrors the quiz `context.py`: a pure function that loads `prompts/page/*.md` through
`coursekit.prompts` (so a course can override the brief) and weaves in optional week metadata. No
env or file I/O at import.
"""

from coursekit import courseconfig, prompts

PAGE_CATEGORY = "page"

# How much of the week a page covers. Each level appends a steering line to the task brief. A course
# sets it in page.yaml (`detail: full`) or a run overrides it (`--detail brief`); an unknown value
# falls back to medium. Kept here, not in a prompt file, because it is generation logic — the task
# brief itself stays discipline-neutral.
DETAIL_LEVELS = ("brief", "medium", "full")
_DETAIL_DIRECTIVES = {
    "brief": ("Keep this page BRIEF. One tight paragraph, or a short bulleted list of only the most "
              "essential concepts — favour the few key ideas over completeness. Still include the "
              "recap and glossary if the material calls for them, but keep every section short."),
    # `medium` is a real, named level — the calibrated middle — that deliberately adds NO directive:
    # the shipped task brief already IS the medium page, so its depth is the brief's own. This empty
    # string is the level's definition, not a missing entry; changing the brief redefines `medium`.
    "medium": "",
    "full": ("Make this page THOROUGH. Cover every concept the material teaches, with fuller bullets "
             "and a worked example next to each concept the material supports. Aim for near-complete "
             "coverage rather than a summary."),
}


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
                   task_prompt: str = "task", domain: str = "", detail: str = "medium") -> list[dict]:
    """The chat messages for one page. A course overrides either prompt from its own
    .vtconfig/prompts/page/, its domain profile is prepended when present, and `detail`
    (brief|medium|full) tunes how much of the week the page covers."""
    system = prompts.load(PAGE_CATEGORY, system_prompt, project_root=project_root)
    task = prompts.load(PAGE_CATEGORY, task_prompt, project_root=project_root)

    body = system.body.format(
        context_line=_context_line(course_title, week_label, module),
        transcript=transcript,
    )
    system_message = "\n" + courseconfig.domain_preface(domain) + body + "\n"
    # The detail directive rides at the end of the brief, where a small model attends most.
    task_body = task.body
    directive = _DETAIL_DIRECTIVES.get(detail, "")
    if directive:
        task_body = task_body + "\n\n" + directive
    return [{"role": "system", "content": system_message},
            {"role": "user", "content": "\n" + task_body + "\n"}]
