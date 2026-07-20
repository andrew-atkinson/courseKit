"""Prompt construction for the page generator.

Mirrors the quiz `context.py`: a pure function that loads `prompts/page/*.md` through
`coursekit.prompts` (so a course can override the brief) and weaves in optional week metadata. No
env or file I/O at import.
"""

from coursekit import prompts

PAGE_CATEGORY = "page"


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
                   task_prompt: str = "task") -> list[dict]:
    """The chat messages for one page. A course overrides either prompt from its own
    .vtconfig/prompts/page/."""
    system = prompts.load(PAGE_CATEGORY, system_prompt, project_root=project_root)
    task = prompts.load(PAGE_CATEGORY, task_prompt, project_root=project_root)

    system_message = "\n" + system.body.format(
        context_line=_context_line(course_title, week_label, module),
        transcript=transcript,
    ) + "\n"
    return [{"role": "system", "content": system_message},
            {"role": "user", "content": "\n" + task.body + "\n"}]
