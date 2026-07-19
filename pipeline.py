"""Driver: turn discovered units into finalized banks.

The reusable surface a larger course-maker imports. `run_unit` handles one week; `run_course`
handles a path (one file or a whole course). The LLM client is injected, so the whole pipeline
is testable with a fake and carries no env or network assumptions of its own.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import bank
import tools
from context import build_messages
from coursekit.providers import Reply
from discover import Unit, find_units
from tools import show


class ModelLoadError(RuntimeError):
    """LM Studio could not load/serve the requested model (usually out of RAM)."""


_LOAD_MARKERS = ("failed to load model", "insufficient system resources",
                 "model_not_found", "no models loaded")


def _looks_like_model_error(exc: Exception) -> bool:
    if any(mk in str(exc).lower() for mk in _LOAD_MARKERS):
        return True
    return getattr(exc, "status_code", None) == 404


def _model_error_message(provider, model: str, exc: Exception) -> str:
    lines = [f"Could not use model '{model}'."]
    verdict, msg = provider.check_fit(model)
    if verdict is False:
        lines.append(msg)
    lines.append(f"The endpoint said: {exc}")
    lines.append("Fix: free memory (eject other models), pick a smaller model, "
                 "or correct MODEL_NAME.")
    return "\n".join(lines)


@dataclass
class RunResult:
    unit: Unit
    finalized: bool
    n_groups: int
    n_variants: int
    output_dir: Path
    problems: list[str] = field(default_factory=list)
    reply: str = ""


DEFAULT_MAX_ITERS = 80


def _nudge(stalled: bool) -> str:
    """The text of a corrective user turn. Reports real bank state so the model has ground
    truth rather than its own (possibly confused) sense of progress.

    Returns content, not a message: shaping it into a turn is the provider's job.
    """
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


def loop(messages, provider, model, *, max_iters: int = DEFAULT_MAX_ITERS,
         max_nudges: int = 4, stall_limit: int = 4) -> str:
    """Drive one conversation to a finalized bank.

    The local model is an unreliable driver. Two observed failure modes (see the run of
    2026-07-17): it stops calling tools before finalizing — often emitting a stray token
    like `<tool_call|>` as prose — and it spins on a rejected call until the turn budget
    is gone. Neither means the work is done, so instead of trusting finish_reason we check
    the bank itself and nudge the model back on track within a bounded budget.

    `provider` is a coursekit Provider: it owns how a turn is represented in the conversation,
    which is what lets this same loop drive a vendor whose tool-result shape differs.
    """
    reply = None
    nudges = 0
    error_streak = 0

    for _ in range(max_iters):
        try:
            reply = provider.chat_with_tools(
                model=model, messages=messages, tools=tools.TOOL_SPECS
            )
        except Exception as exc:
            # Translate LM Studio's opaque model-load failure into an actionable message,
            # and abort the whole batch rather than failing identically on every unit.
            if _looks_like_model_error(exc):
                raise ModelLoadError(_model_error_message(provider, model, exc)) from exc
            raise

        if reply.wants_tools:
            provider.append_assistant(messages, reply)
            results = tools.run_tool_calls(reply.tool_calls)
            provider.append_tool_results(messages, results)
            if bank.is_finalized():
                break

            # Runaway-rejection loop: a whole turn's calls all failed. A few in a row means
            # the model is stuck (it burned 31 turns on rejected mark_complete once).
            if results and all(content.startswith("ERROR") for _, content in results):
                error_streak += 1
            else:
                error_streak = 0
            if error_streak >= stall_limit:
                if nudges >= max_nudges:
                    show("[red]Bailing: tool calls kept failing.[/red]")
                    break
                nudges += 1
                error_streak = 0
                provider.append_user(messages, _nudge(stalled=True))
            continue

        # The model stopped calling tools. Not the same as finishing the bank.
        if bank.is_finalized():
            break
        if nudges >= max_nudges:
            show("[yellow]Model stopped without finalizing; nudge budget spent.[/yellow]")
            break
        nudges += 1
        # Re-append without raw_message on purpose: the provider then synthesises a plain
        # assistant dict, avoiding the null-tool_calls object some servers reject on a
        # stop turn. Then correct it.
        provider.append_assistant(messages, Reply(finish_reason=reply.finish_reason,
                                                  content=reply.content))
        provider.append_user(messages, _nudge(stalled=False))
    else:
        show(f"[yellow]Reached the {max_iters}-turn limit without finalizing.[/yellow]")

    # LM Studio returns content=None after a tool-heavy run; downstream writes need a str.
    return (reply.content or "") if reply else ""


def run_unit(unit: Unit, provider, model, *, max_iters: int = DEFAULT_MAX_ITERS) -> RunResult:
    """Generate and finalize one week's bank, writing artifacts to unit.output_dir."""
    out = Path(unit.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Fresh per-week state. The module-level singletons in bank.py and tools.py would
    # otherwise carry week N's groups, checklist, and call-log into week N+1.
    bank.init(run_id=f"{unit.course_slug}-{unit.week_slug}", out_dir=out,
              title=unit.week_label, source=unit.transcript_path.name)
    tools.reset_state()
    tools.set_call_log(out / "calls.jsonl")

    transcript = unit.transcript_path.read_text(encoding="utf-8")
    # course_root is what makes a course's own .vtconfig/prompts/quiz/ override reachable.
    # Without it the override mechanism exists but nothing can get to it.
    messages = build_messages(transcript, course_title=unit.course_title,
                              week_label=unit.week_label, module=unit.module,
                              project_root=unit.course_root)
    reply = loop(messages, provider, model, max_iters=max_iters)
    (out / "reply.txt").write_text(reply, encoding="utf-8")

    b = bank.get()
    return RunResult(
        unit=unit,
        finalized=bank.is_finalized(),
        n_groups=len(b.groups),
        n_variants=sum(len(g.variants) for g in b.groups.values()),
        output_dir=out,
        problems=bank.validate_final(),
        reply=reply,
    )


def _week_key(w) -> str:
    """Normalise a week reference so '3', 'week-3', 'week 3' all match."""
    m = re.search(r"\d+", str(w))
    return m.group(0) if m else str(w).strip().lower()


def run_course(path, *, weeks=None, output_root=None, provider=None, model=None,
               dry_run: bool = False, max_iters: int = DEFAULT_MAX_ITERS) -> list[RunResult]:
    """Discover units under `path`, optionally filter to `weeks`, and run each.

    `dry_run` returns the planned units (with resolved output dirs) without calling the model.
    """
    units = find_units(path, output_root=output_root)
    if weeks:
        wanted = {_week_key(w) for w in weeks}
        units = [u for u in units if _week_key(u.week_slug) in wanted]

    if dry_run:
        return [RunResult(u, finalized=False, n_groups=0, n_variants=0, output_dir=u.output_dir)
                for u in units]

    return [run_unit(u, provider, model, max_iters=max_iters) for u in units]
