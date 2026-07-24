"""Prompt construction.

Pure in the way that matters: build_messages() takes a transcript (and optional course/week
metadata) and returns the chat messages. No env or file I/O at *import* — the caller supplies
the transcript, which is what lets one process handle many weeks of many courses.

The prompt text itself lives in `prompts/quiz/*.md` and is loaded through coursekit.prompts, so
an instructor or department can override the brief for a course without touching this code.
"""

from coursekit import courseconfig, prompts

QUIZ_CATEGORY = "quiz"


def _context_line(course_title, week_label, module) -> str:
    """A single factual line placing the lecture, or '' when nothing is known.

    Kept plain and unambiguous rather than fluent — it is orienting metadata for the model,
    not prose it should imitate.
    """
    parts = []
    if week_label:
        parts.append(week_label)
    if module:
        parts.append(module)
    if course_title:
        parts.append(f"course: {course_title}")
    if not parts:
        return ""
    return "\nLecture context — " + "; ".join(parts) + ".\n"


def build_messages(transcript: str, *, course_title: str | None = None,
                   week_label: str | None = None, module: str | None = None,
                   project_root=None, system_prompt: str = "system",
                   task_prompt: str = "task", domain: str = "",
                   n_questions: int = 5, n_variants: int = 4) -> list[dict]:
    """The chat messages for one lecture. Metadata is woven in only when supplied.

    `project_root` lets a course override either prompt from its own .vtconfig/prompts/quiz/.
    `n_questions`/`n_variants` size the bank (from the course's quiz.yaml). The leading/trailing
    newlines are restored here rather than stored in the files, so the prompt files stay clean
    readable Markdown.
    """
    system = prompts.load(QUIZ_CATEGORY, system_prompt, project_root=project_root)
    task = prompts.load(QUIZ_CATEGORY, task_prompt, project_root=project_root)

    # Counts are substituted by a plain replace, NOT str.format — so a course's prompt override may
    # contain literal { } freely. {n_variants} in the system prompt is resolved before .format()
    # runs its own {context_line}/{transcript} fields.
    def _counts(text: str) -> str:
        return text.replace("{n_questions}", str(n_questions)).replace("{n_variants}", str(n_variants))

    body = _counts(system.body).format(
        context_line=_context_line(course_title, week_label, module),
        transcript=transcript,
    )
    system_message = "\n" + courseconfig.domain_preface(domain) + body + "\n"
    return [{"role": "system", "content": system_message},
            {"role": "user", "content": "\n" + _counts(task.body) + "\n"}]
