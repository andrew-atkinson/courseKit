"""The page generator: the second implementation of the Generator seam.

Same shape as the quiz generator — wraps the page IR (`page`), its tools, and its prompt assembly
(`context`) behind the protocol the driver speaks. Building it required no change to the driver,
which is the whole point of the seam.
"""

from pathlib import Path

from coursekit.discover import Unit
from coursekit.generate.base import RunResult
from coursekit.generate.page import page, tools
from coursekit.generate.page.context import build_messages


class PageGenerator:
    category = "page"
    artifacts_subdir = "pages"

    def reset(self, unit: Unit, out_dir: Path) -> None:
        page.init(page_id=f"{unit.course_slug}-{unit.week_slug}", out_dir=out_dir,
                  title=unit.week_label or unit.week_slug, page_type="week_intro",
                  week_ref=unit.week_slug, slug=unit.week_slug)
        tools.reset_state()
        tools.set_call_log(out_dir / "calls.jsonl")

    def tool_specs(self) -> list:
        return tools.TOOL_SPECS

    def run_tool_calls(self, calls):
        return tools.run_tool_calls(calls)

    def build_messages(self, unit: Unit, transcript: str, cfg) -> list[dict]:
        return build_messages(
            transcript, course_title=unit.course_title, week_label=unit.week_label,
            module=unit.module, project_root=unit.course_root,
            system_prompt=cfg.prompt_name("system_prompt", default="system"),
            task_prompt=cfg.prompt_name("task_prompt", default="task"),
        )

    def is_finalized(self) -> bool:
        return page.is_finalized()

    def nudge(self, *, stalled: bool) -> str:
        pg = page.get()
        n_blocks = len(pg.blocks)
        problems = page.validate_final()
        head = ("Several tool calls in a row failed; stop repeating the same call. "
                if stalled else
                "You stopped before the page was finalized. ")
        state = f"Recorded so far: {n_blocks} block(s). "
        if problems:
            state += "Still to fix: " + "; ".join(problems[:3]) + ". "
        tail = ("Keep going with tool calls only: add the remaining sections, then call "
                "finalize_page. Do not reply in prose, and do not add links.")
        return head + state + tail

    def result(self, unit: Unit, out_dir: Path, reply: str) -> RunResult:
        pg = page.get()
        # Emit the reviewable standalone HTML beside page.json, merging the course's supplements
        # (references, examples, embeds) at render time. Local import keeps the generator decoupled
        # from the emitter at module load — the same way bank.finalize reaches gift.
        from coursekit.emit import html as html_emit
        from coursekit.generate.page.renderer import load_supplements
        supplements = load_supplements(unit.course_root, unit.week_slug)
        html_emit.write_html(pg, out_dir, supplements)

        return RunResult(
            unit=unit, finalized=page.is_finalized(), output_dir=out_dir,
            counts={"blocks": len(pg.blocks)},
            problems=page.validate_final(), reply=reply,
        )
