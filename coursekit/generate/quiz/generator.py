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

# The brief asks for four variants per group (prompts/quiz/task.md); auto_finalize treats a group as
# complete only at that count. ASMT-18 will make it configurable — read the same setting here then.
VARIANTS_PER_GROUP = 4


class QuizGenerator:
    category = "quiz"
    artifacts_subdir = "quizzes"

    def __init__(self, *, concept_shape: bool = True):
        # concept_shape=False: shape the quiz by the material alone, not the unit's concept map — for a
        # single-document (targeted) quiz, whose unit's concept list is the wrong grain (ASMT-19). The
        # unit's map is still read for its enduring understanding (postprocess).
        self.concept_shape = concept_shape

    def reset(self, unit: Unit, out_dir: Path) -> None:
        # Fresh per-unit state. The module-level singletons in bank.py and tools.py would
        # otherwise carry one week's groups, checklist, and call-log into the next.
        bank.init(run_id=f"{unit.course_slug}-{unit.week_slug}", out_dir=out_dir,
                  title=unit.week_label, source=unit.transcript_path.name)
        tools.reset_state()
        tools.set_call_log(out_dir / "calls.jsonl")
        self._expected_groups = None   # set by build_messages from this unit's brief

    def tool_specs(self) -> list:
        return tools.TOOL_SPECS

    def run_tool_calls(self, calls):
        return tools.run_tool_calls(calls)

    def build_messages(self, unit: Unit, transcript: str, cfg) -> list[dict]:
        # A course selects its prompts by name (system_prompt/task_prompt in quiz.yaml) and by
        # file (a .vtconfig/prompts/quiz/ override, reached via project_root). The number of question
        # groups is content-relative: the week's concept map suggests it (one per concept + the
        # enduring understanding), and quiz.yaml's `questions:` overrides that with a fixed count.
        from coursekit.generate.page.concept_map import load_for_unit
        cm = load_for_unit(unit) if self.concept_shape else None
        # Per-week wins over per-course: a `questions` on THIS week's concept map beats quiz.yaml's.
        q = (cm.questions if cm is not None and cm.questions else cfg.value("questions"))
        # The brief's group target, kept so auto_finalize can tell COMPLETE from merely consistent:
        # `questions:` fixes it exactly; else one group per concept (the model may add extras); with
        # neither, the model picks the count and there is nothing to verify against.
        concepts = getattr(cm, "concepts", None) if cm is not None else None
        self._expected_groups = int(q) if q else (len(concepts) if concepts else None)
        return build_messages(
            transcript, course_title=unit.course_title, week_label=unit.week_label,
            module=unit.module, project_root=unit.course_root,
            system_prompt=cfg.prompt_name("system_prompt", default="system"),
            task_prompt=cfg.prompt_name("task_prompt", default="task"),
            domain=cfg.domain, voice=cfg.voice,
            concept_map=cm,
            questions=int(q) if q else None,
        )

    def postprocess(self, unit, provider, model, cfg, transcript) -> None:
        """ASMT-3 (opt-in `eu_question: true`): add the enduring-understanding transfer task through
        the DETERMINISTIC EU pass — the program fixes the type to open_response, the model writes only
        the content — then re-finalize so it lands in bank.json/quiz.json/gift. Only runs on a bank the
        main loop actually finalized; a failed pass leaves the bank untouched. Switched on, it either adds
        the question or records why not — never a silent no-op (CORE-1.5)."""
        if not cfg.value("eu_question"):
            return
        from coursekit import outcomes
        from coursekit.generate.page.concept_map import load_for_unit
        from coursekit.generate.quiz import eu as eu_pass
        where = unit.week_slug
        if not bank.is_finalized():
            outcomes.warn("eu.skipped", f"  {where}: no EU question — the quiz itself didn't finish.",
                          unit=where, reason="quiz_not_finalized")
            return
        cm = load_for_unit(unit)
        eu = cm.enduring_understanding if cm is not None else ""
        if not eu:
            why = ("it has no concept map — run `coursekit analyze` first" if cm is None
                   else "its concept map has no enduring understanding — add one, or re-run `analyze`")
            outcomes.warn("eu.skipped", f"  {where}: eu_question is on but no EU question was added — {why}.",
                          unit=where, reason="no_concept_map" if cm is None else "no_enduring_understanding")
            return
        if eu_pass.generate_eu_question(provider, model, transcript, eu, unit.course_root):
            bank.finalize()   # same deterministic seed → re-writes cleanly with the EU group included
        else:
            outcomes.warn("eu.not_added", f"  {where}: the model didn't write the EU question — the quiz is "
                                          f"saved without it; re-run to try again.", unit=where)

    def is_finalized(self) -> bool:
        return bank.is_finalized()

    def auto_finalize(self) -> bool:
        """The model stopped without calling finalize_bank (e.g. it leaked `<tool_call|>` as prose and
        the nudges ran out). The PROGRAM may finish the bank — but only when it is COMPLETE against what
        the brief asked for. `validate_final` is a consistency check: it passes a bank that gave up
        halfway (3 of 7 groups, one variant of four), and finalizing that would turn an honest
        INCOMPLETE into a false success. Complete = at least the target number of groups (unknown →
        don't guess) and the full set of variants in each (an open-response EU group is single by
        design). `bank.finalize` still validates on top of this."""
        target = getattr(self, "_expected_groups", None)
        if target is None:
            return False
        groups = [g for g in bank.get().groups.values() if g.question_type != "open_response"]
        if len(groups) < target or any(len(g.variants) < VARIANTS_PER_GROUP for g in groups):
            return False
        bank.finalize()
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
