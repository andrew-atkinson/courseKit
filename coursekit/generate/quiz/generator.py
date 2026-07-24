"""The quiz generator: the reference implementation of the Generator seam.

Wraps the quiz IR (`bank`), its tools, and its prompt assembly (`context`) behind the protocol the
driver speaks. Nothing here is new behaviour — it is the logic that used to live inline in
`pipeline.run_unit` and `pipeline.loop`, moved behind the seam so a second generator can reuse the
driver without copying it.
"""

from pathlib import Path

from coursekit.discover import Unit
from coursekit.generate.base import RunResult
from coursekit.generate.quiz import bank, tools
from coursekit.generate.quiz.context import build_messages


class QuizGenerator:
    category = "quiz"
    artifacts_subdir = "quizzes"

    def reset(self, unit: Unit, out_dir: Path) -> None:
        # Fresh per-unit state. The module-level singletons in bank.py and tools.py would
        # otherwise carry one week's groups, checklist, and call-log into the next.
        bank.init(run_id=f"{unit.course_slug}-{unit.week_slug}", out_dir=out_dir,
                  title=unit.week_label, source=unit.transcript_path.name)
        tools.reset_state()
        tools.set_call_log(out_dir / "calls.jsonl")

    def tool_specs(self) -> list:
        return tools.TOOL_SPECS

    def run_tool_calls(self, calls):
        return tools.run_tool_calls(calls)

    def build_messages(self, unit: Unit, transcript: str, cfg) -> list[dict]:
        # A course selects its prompts by name (system_prompt/task_prompt in quiz.yaml) and by
        # file (a .vtconfig/prompts/quiz/ override, reached via project_root).
        return build_messages(
            transcript, course_title=unit.course_title, week_label=unit.week_label,
            module=unit.module, project_root=unit.course_root,
            system_prompt=cfg.prompt_name("system_prompt", default="system"),
            task_prompt=cfg.prompt_name("task_prompt", default="task"),
            domain=cfg.domain,
            n_questions=int(cfg.value("questions", 5) or 5),
            n_variants=int(cfg.value("variants", 4) or 4),
        )

    def is_finalized(self) -> bool:
        return bank.is_finalized()

    def nudge(self, *, stalled: bool) -> str:
        # Report real bank state so the model has ground truth, not its own sense of progress.
        b = bank.get()
        n_groups = len(b.groups)
        n_variants = sum(len(g.variants) for g in b.groups.values())
        problems = bank.validate_final()

        head = ("Several tool calls in a row failed; stop repeating the same call. "
                if stalled else
                "You stopped before the bank was finalized. ")
        state = f"Recorded so far: {n_groups} group(s), {n_variants} variant(s). "
        if problems:
            state += "Still to fix: " + "; ".join(problems[:3]) + ". "
        tail = ("Keep going with tool calls only: work through your checklist, add any missing "
                "variants, then call finalize_bank. Do not reply in prose.")
        return head + state + tail

    def result(self, unit: Unit, out_dir: Path, reply: str) -> RunResult:
        b = bank.get()
        return RunResult(
            unit=unit, finalized=bank.is_finalized(), output_dir=out_dir,
            counts={"groups": len(b.groups),
                    "variants": sum(len(g.variants) for g in b.groups.values())},
            problems=bank.validate_final(), reply=reply,
        )
