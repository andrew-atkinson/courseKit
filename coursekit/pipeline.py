"""Driver: turn discovered units into finalized artifacts.

The reusable surface a larger course-maker imports. `run_unit` handles one unit (a week);
`run_course` handles a path (one file or a whole course). The driver is **generator-agnostic**: it
speaks the `Generator` seam (coursekit.generate.base) and knows nothing about quizzes or pages
specifically. That is what lets a second generator reuse the whole thing — the loop, the nudging,
the model-load handling, the per-unit reset — without copying it. The LLM client is injected, so the
pipeline is testable with a fake and carries no env or network assumptions of its own.
"""

from pathlib import Path

from coursekit import courseconfig
from coursekit.console import show
from coursekit.discover import Unit, find_units, slugify
from coursekit.generate.base import Generator, RunResult
from coursekit.providers import Reply


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


DEFAULT_MAX_ITERS = 80


def _default_generator() -> Generator:
    """The quiz generator is the default, so callers (and tests) that don't pass one keep driving
    quizzes. Imported lazily to keep the spine free of a compile-time dependency on any concrete
    generator — the seam points one way, generator → spine, never back."""
    from coursekit.generate.quiz.generator import QuizGenerator
    return QuizGenerator()


def loop(messages, provider, model, generator: Generator | None = None, *,
         max_iters: int = DEFAULT_MAX_ITERS, max_nudges: int = 4, stall_limit: int = 4) -> str:
    """Drive one conversation to a finalized artifact.

    The local model is an unreliable driver. Two observed failure modes (see the run of
    2026-07-17): it stops calling tools before finalizing — often emitting a stray token like
    `<tool_call|>` as prose — and it spins on a rejected call until the turn budget is gone.
    Neither means the work is done, so instead of trusting finish_reason we ask the generator
    whether its artifact is finalized and nudge the model back on track within a bounded budget.

    `provider` is a coursekit Provider (it owns how a turn is represented); `generator` is the
    Generator seam (it owns the tools, the finalized check, and the nudge vocabulary).
    """
    gen = generator or _default_generator()
    reply = None
    nudges = 0
    error_streak = 0

    for _ in range(max_iters):
        try:
            reply = provider.chat_with_tools(
                model=model, messages=messages, tools=gen.tool_specs()
            )
        except Exception as exc:
            # Translate LM Studio's opaque model-load failure into an actionable message,
            # and abort the whole batch rather than failing identically on every unit.
            if _looks_like_model_error(exc):
                raise ModelLoadError(_model_error_message(provider, model, exc)) from exc
            raise

        if reply.wants_tools:
            provider.append_assistant(messages, reply)
            results = gen.run_tool_calls(reply.tool_calls)
            provider.append_tool_results(messages, results)
            if gen.is_finalized():
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
                provider.append_user(messages, gen.nudge(stalled=True))
            continue

        # The model stopped calling tools. Not the same as finishing the artifact.
        if gen.is_finalized():
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
        provider.append_user(messages, gen.nudge(stalled=False))
    else:
        show(f"[yellow]Reached the {max_iters}-turn limit without finalizing.[/yellow]")

    # LM Studio returns content=None after a tool-heavy run; downstream writes need a str.
    return (reply.content or "") if reply else ""


def run_unit(unit: Unit, provider, model, generator: Generator | None = None, *,
             max_iters: int = DEFAULT_MAX_ITERS) -> RunResult:
    """Generate and finalize one unit's artifact, writing to unit.output_dir."""
    gen = generator or _default_generator()
    out = Path(unit.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    gen.reset(unit, out)
    # The course's own config for this generator (quiz.yaml, page.yaml, …) selects prompts by name
    # and supplies the project root for file overrides. Absent config degrades to defaults.
    cfg = unit.config or courseconfig.load(unit.transcript_path, config_name=f"{gen.category}.yaml")
    transcript = unit.transcript_path.read_text(encoding="utf-8")
    messages = gen.build_messages(unit, transcript, cfg)

    reply = loop(messages, provider, model, gen, max_iters=max_iters)
    (out / "reply.txt").write_text(reply, encoding="utf-8")

    return gen.result(unit, out, reply)


def _week_matches(ref, unit: Unit) -> bool:
    """Does a `--week` reference select this unit?

    Numeric references ('3', 'week-3', 'week 3', 3) match on the week number via the shared
    normaliser. A non-numeric reference (a slug like 'intro') has no week number, so it matches
    the unit's slug literally — never a bare `None == None`, which would select every
    non-numeric week at once.
    """
    k = courseconfig.week_key(ref)
    if k is not None:
        return courseconfig.week_key(unit.week_slug) == k
    return slugify(str(ref)) == unit.week_slug


def run_course(path, *, weeks=None, output_root=None, provider=None, model=None,
               dry_run: bool = False, max_iters: int = DEFAULT_MAX_ITERS,
               generator: Generator | None = None) -> list[RunResult]:
    """Discover units under `path`, optionally filter to `weeks`, and run each with `generator`
    (default: the quiz generator).

    `dry_run` returns the planned units (with resolved output dirs) without calling the model.
    """
    # The output tree (quizzes/, pages/, …) is the generator's, so a course can hold both.
    subdir = getattr(generator, "artifacts_subdir", "quizzes")
    units = find_units(path, output_root=output_root, subdir=subdir)
    if weeks:
        units = [u for u in units if any(_week_matches(w, u) for w in weeks)]

    if dry_run:
        return [RunResult(u, finalized=False, output_dir=u.output_dir) for u in units]

    return [run_unit(u, provider, model, generator, max_iters=max_iters) for u in units]
