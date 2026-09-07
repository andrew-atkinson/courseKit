"""Prompt construction.

Pure in the way that matters: build_messages() takes a transcript (and optional course/week
metadata) and returns the chat messages. No env or file I/O at *import* — the caller supplies
the transcript, which is what lets one process handle many weeks of many courses.

The prompt text itself lives in `prompts/quiz/*.md` and is loaded through coursekit.prompts, so
an instructor or department can override the brief for a course without touching this code.
"""

from coursekit import courseconfig, prompts

QUIZ_CATEGORY = "quiz"


def _shape_directive(concept_map, questions=None) -> str:
    """How many question groups, and covering what — the quiz analog of the page's concept checklist.
    The number is FLEXIBLE, not a hardcoded five: an explicit `questions` (quiz.yaml) fixes it (the
    user's choice); otherwise the week's concept map suggests it — one group per teaching concept, its
    variants drawn from that concept's knowledge components, and a second group for a concept whose
    components clearly support more than one question (the model's suggestion, grounded in the map);
    otherwise the model chooses from the material. The enduring understanding FRAMES the questions but
    is never its own MC group — a transferable idea isn't a multiple-choice item (ASMT-1; a
    performance-task instrument for it is ASMT-3). Rides at the end of the brief, where a small model
    attends most."""
    concepts = getattr(concept_map, "concepts", None) if concept_map is not None else None
    eu = getattr(concept_map, "enduring_understanding", "") if concept_map is not None else ""

    def _concept_lines() -> list[str]:
        out = []
        for c in concepts:
            kcs = ", ".join(c.components) if getattr(c, "components", None) else ""
            out.append(f"  - {c.name}" + (f"  (aspects: {kcs})" if kcs else ""))
        if eu:
            out.append(f"\nThe week's enduring understanding — the transferable idea the questions "
                       f"should keep pointing at, but NOT its own MC group (multiple choice can't test "
                       f"a transferable understanding): {eu}")
        return out

    if questions and concepts:                     # a fixed count, still grounded in the map
        lines = [f"\n\n**How many groups: create EXACTLY {questions} question groups.** Cover the "
                 f"week's concepts, one group each:"] + _concept_lines()
        lines.append(f"\nIf {questions} is more than the concepts above, add a second group for the "
                     f"richest concepts; if fewer, cover the most important. Four variants per group.")
        d = "\n".join(lines)
    elif questions:
        d = (f"\n\n**How many groups.** Create EXACTLY {questions} question groups, one concept "
             f"each — the {questions} most important ideas the lecture teaches.")
    elif concepts:
        lines = ["\n\n**How many groups — build the quiz to cover the week's concept map, not a fixed "
                 "number.** The concepts this week teaches, each its own group:"] + _concept_lines()
        lines.append("\nMake ONE group per concept above, its variants testing different aspects of "
                     "it. Where a concept's aspects clearly support more than one distinct question, "
                     "add a second group for it. Do NOT add an MC group for the enduring understanding "
                     "itself — it frames the questions, but multiple choice can't test a transferable "
                     "idea. You choose the total; let the concept map decide it, not a fixed count.")
        d = "\n".join(lines)
    else:
        d = ("\n\n**How many groups — let the material decide.** Make one group for each of the most "
             "important ideas the lecture teaches (usually four to six), not a fixed count.")
    return d


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
                   task_prompt: str = "task", domain: str = "", voice: str = "",
                   concept_map=None, questions: int | None = None) -> list[dict]:
    """The chat messages for one lecture. Metadata is woven in only when supplied.

    `project_root` lets a course override either prompt from its own .vtconfig/prompts/quiz/. When a
    `concept_map` is present its concepts set the quiz's shape (one group each; the enduring
    understanding frames the questions but gets no group of its own), and an explicit `questions`
    count overrides that — so the number of questions is
    flexible and content-relative, not a hardcoded five. The leading/trailing newlines are restored
    here rather than stored in the files, so the prompt files stay clean readable Markdown.
    """
    system = prompts.load(QUIZ_CATEGORY, system_prompt, project_root=project_root)
    task = prompts.load(QUIZ_CATEGORY, task_prompt, project_root=project_root)

    body = system.body.format(
        context_line=_context_line(course_title, week_label, module),
        transcript=transcript,
    )
    system_message = ("\n" + courseconfig.domain_preface(domain)
                      + courseconfig.quiz_voice_preface(voice) + body + "\n")
    task_body = task.body + _shape_directive(concept_map, questions)
    return [{"role": "system", "content": system_message},
            {"role": "user", "content": "\n" + task_body + "\n"}]
