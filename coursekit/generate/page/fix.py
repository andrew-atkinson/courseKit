"""Targeted regeneration for PAGES — fix each flagged section in place.

The pages analog of `quiz/fix.py`. For every FLAGged block the page critic reports, hand the model the
material, the flawed section, and the reviewer's concern, and ask for a correction committed through
the SAME tool with the SAME `block_id` — so `put_block` overwrites just that block and leaves the rest
of the page untouched. Each fix is cold-read once more to confirm it now passes, then the page HTML is
re-rendered. Handles the code-bug class of flags (undeclared variables, wrong lifecycle calls, property
names that disagree with the material).

Reuses the quiz `FixOutcome`/`render_outcomes` (a fix outcome is the same shape for both artifacts).
"""

from pathlib import Path

from coursekit import courseconfig, prompts
from coursekit.generate.page import evaluate as pev
from coursekit.generate.page import page as pageir
from coursekit.generate.page import tools
from coursekit.generate.quiz.evaluate import _critic_body
from coursekit.generate.quiz.fix import FixOutcome, render_outcomes  # noqa: F401 (re-exported)
from coursekit.providers.base import Reply

FIX_CATEGORY = "page"

# Only the add_* block tools — never get_page_report or finalize_page (the fixer revises one block).
FIX_TOOL_SPECS = [s for s in tools.TOOL_SPECS if s["name"].startswith("add_")]


def _fixer_body(project_root) -> str:
    cfg = courseconfig.load(project_root) if project_root else None
    domain, voice = (cfg.domain, cfg.voice) if cfg else ("", "")
    return (courseconfig.domain_preface(domain) + courseconfig.voice_preface(voice)
            + prompts.load(FIX_CATEGORY, "fix", project_root=project_root).body)


def fix_one_block(finding, material: str, provider, model: str, *, critic: str,
                  project_root=None, max_turns: int = 4) -> FixOutcome:
    """Correct ONE flagged block in the loaded page (the singleton), then verify. The block must
    already be present in `pageir.get()` (the caller loads the page first)."""
    block_id, kind = finding.group_id, finding.label      # page Findings carry (block_id, kind)
    b = pageir.get().blocks.get(block_id)
    if b is None:
        return FixOutcome(finding.week, block_id, kind, finding.concern, False, None)

    before_dump = b.model_dump()
    tool_name = f"add_{kind}"
    system = _fixer_body(project_root)
    user = (f"The week's teaching material:\n<material>\n{material}\n</material>\n\n"
            f"A reviewer flagged this page section:\n{pev._format_block(b)}\n\n"
            f"The reviewer's concern:\n{finding.concern or '(the section is wrong or its code will not run)'}\n\n"
            f"Correct it: call {tool_name} with block_id '{block_id}' (the same id, so it REPLACES "
            f"the flawed section).")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    replaced = False
    for _ in range(max(1, max_turns)):
        try:
            reply = provider.chat_with_tools(model=model, messages=messages, tools=FIX_TOOL_SPECS)
        except Exception:
            break
        if reply.wants_tools:
            provider.append_assistant(messages, reply)
            results = tools.run_tool_calls(reply.tool_calls)
            provider.append_tool_results(messages, results)
            now = pageir.get().blocks.get(block_id)
            committed = any(not c.startswith("ERROR") for _, c in results)
            if committed and now is not None and now.model_dump() != before_dump:
                replaced = True
                break
        else:
            provider.append_assistant(messages, Reply(finish_reason=reply.finish_reason,
                                                      content=reply.content))
            provider.append_user(messages, f"Call {tool_name} with block_id '{block_id}' to replace "
                                           f"the flawed section. Do not reply in prose, no links.")

    now_passes = None
    if replaced:
        now = pageir.get().blocks.get(block_id)
        verdict, _, _ = pev._one_read(critic, material, now, provider, model)
        now_passes = verdict == "PASS"
    return FixOutcome(finding.week, block_id, kind, finding.concern, replaced, now_passes)


def fix_course_pages(path, *, weeks=None, provider, model, reads: int = pev.DEFAULT_READS,
                     max_turns: int = 4, findings=None, progress=None) -> list[FixOutcome]:
    """Correct each flagged page section in place and re-render the HTML. Returns the per-item
    outcomes. When `findings` is given (parsed from an existing `page-review.md`), fix exactly those —
    no re-audit; otherwise cold-read every page to find the flags first. `progress(msg)` gives a live
    heartbeat. page.json is autosaved on each fix."""
    from coursekit.discover import find_units
    from coursekit.generate.page.page import Page
    from coursekit.pipeline import _week_matches
    from coursekit.generate.quiz.fix import _outcome_word

    units = find_units(path, subdir="pages")
    if weeks:
        units = [u for u in units if any(_week_matches(w, u) for w in weeks)]

    outcomes: list[FixOutcome] = []
    for u in units:
        pj = Path(u.output_dir) / "page.json"
        if not pj.exists():
            continue
        page_obj = Page.model_validate_json(pj.read_text(encoding="utf-8"))
        material = Path(u.transcript_path).read_text(encoding="utf-8")
        if findings is not None:
            flagged = [f for f in findings if f.flagged and f.week == u.week_slug]
        else:
            fnd = pev.evaluate_page(page_obj, material, provider, model, week=u.week_slug,
                                    project_root=u.course_root, reads=reads, progress=progress)
            flagged = [f for f in fnd if f.flagged]
        if not flagged:
            continue
        pageir.load(page_obj, out_dir=u.output_dir)       # adopt this page; put_block autosaves it
        critic = _critic_body(pev.PAGE_CATEGORY, u.course_root)
        for f in flagged:
            if progress:
                progress(f"fixing {u.week_slug} {f.group_id} ({f.label})…")
            o = fix_one_block(f, material, provider, model, critic=critic,
                              project_root=u.course_root, max_turns=max_turns)
            if progress:
                progress(f"  → {_outcome_word(o)}")
            outcomes.append(o)
        _rerender(u)
    return outcomes


def _rerender(unit) -> None:
    """Re-render the page HTML after the fixes, merging supplements + theme (mirrors the generator).
    Best-effort: a render hiccup must not lose the fixes, which are already saved to page.json."""
    try:
        from coursekit.emit import html as html_emit
        from coursekit.generate.page.renderer import load_supplements
        from coursekit.generate.page.style import load_style
        supplements = load_supplements(unit.course_root, unit.week_slug)
        html_emit.write_html(pageir.get(), Path(unit.output_dir), supplements,
                             load_style(unit.course_root))
    except Exception:
        pass
