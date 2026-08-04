"""Targeted regeneration: fix each flagged quiz question in place.

The cold-read critic (`evaluate.py`) only *reports*. This closes the loop: for every FLAGged variant
it hands the model the material, the flawed question, and the reviewer's concern, and asks for a
corrected version committed through the SAME tool with the SAME `group_id`/`variant_label` — so
`put_variant` overwrites just that variant and leaves the rest of the bank untouched. Each fix is then
cold-read once more to confirm it now passes, so a stubborn item is surfaced rather than silently kept.

This is the payoff of the whole evaluate layer: it turns "the audit found N errors" into "the audit
found and fixed N errors." Deliberately scoped to quizzes first (where most flags land and the
one-variant-one-tool-call mechanism is cleanest); page fixes are the parallel follow-up.
"""

from dataclasses import dataclass
from pathlib import Path

from coursekit import courseconfig, prompts
from coursekit.generate.quiz import bank, tools
from coursekit.generate.quiz import evaluate as ev
from coursekit.generate.quiz.bank import _KIND_TO_TOOL
from coursekit.providers.base import Reply

FIX_CATEGORY = "quiz"

# The fixer only ever revises one existing variant, so it sees ONLY the add_* tools — not the
# checklist, report, or finalize tools (which would let it wander off the single-item task).
FIX_TOOL_SPECS = [s for s in tools.TOOL_SPECS if s["name"].startswith("add_")]


@dataclass
class FixOutcome:
    week: str
    group_id: str
    label: str
    concern: str
    replaced: bool              # did the model overwrite the variant?
    now_passes: bool | None     # re-read verdict after the fix; None if never replaced


def _fixer_body(project_root) -> str:
    """The fix prompt, with the course's domain profile and voice prepended (generation-framed — the
    fixer is authoring a corrected question, so it knows the domain and writes in the instructor's
    voice, exactly like the generator)."""
    cfg = courseconfig.load(project_root) if project_root else None
    domain, voice = (cfg.domain, cfg.voice) if cfg else ("", "")
    return (courseconfig.domain_preface(domain) + courseconfig.quiz_voice_preface(voice)
            + prompts.load(FIX_CATEGORY, "fix", project_root=project_root).body)


def fix_one(finding, transcript: str, provider, model: str, *, critic: str,
            project_root=None, max_turns: int = 4) -> FixOutcome:
    """Correct ONE flagged variant in the loaded bank (the singleton), then verify. The variant must
    already be present in `bank.get()` (the caller loads the bank first)."""
    gid, label = finding.group_id, finding.label
    group = bank.get().groups.get(gid)
    before = group.variants.get(label) if group else None
    if before is None:                       # the bank changed under us; nothing to fix
        return FixOutcome(finding.week, gid, label, finding.concern, False, None)

    before_dump = before.model_dump()
    tool_name = _KIND_TO_TOOL[before.kind]
    system = _fixer_body(project_root)
    user = (f"The week's teaching material:\n<material>\n{transcript}\n</material>\n\n"
            f"A reviewer flagged this question:\n{ev._format_question(before)}\n\n"
            f"The reviewer's concern:\n{finding.concern or '(the marked answer or the question is wrong)'}\n\n"
            f"Correct it: call {tool_name} with group_id '{gid}' and variant_label '{label}' "
            f"(the same ids, so it REPLACES the flawed question).")
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
            now = bank.get().groups[gid].variants.get(label)
            committed = any(not c.startswith("ERROR") for _, c in results)
            if committed and now is not None and now.model_dump() != before_dump:
                replaced = True
                break
            # otherwise the ERROR ack (or an unchanged variant) is in the messages and steers the retry
        else:
            provider.append_assistant(messages, Reply(finish_reason=reply.finish_reason,
                                                      content=reply.content))
            provider.append_user(messages, f"Call {tool_name} with group_id '{gid}' and "
                                           f"variant_label '{label}' to replace the flawed question. "
                                           f"Do not reply in prose.")

    now_passes = None
    if replaced:
        now = bank.get().groups[gid].variants.get(label)
        verdict, _, _ = ev._one_read(critic, transcript, now, provider, model)
        now_passes = verdict == "PASS"
    return FixOutcome(finding.week, gid, label, finding.concern, replaced, now_passes)


def fix_course(path, *, weeks=None, provider, model, reads: int = ev.DEFAULT_READS,
               max_turns: int = 4, findings=None, progress=None) -> list[FixOutcome]:
    """Correct each flagged variant in place and re-emit. Returns the per-item outcomes.

    When `findings` is given (parsed from an existing `quiz-review.md`), fix exactly those — no
    re-audit, so "generate flagged 1 → fix it" is near-instant. Otherwise cold-read every week to find
    the flags first. `progress(msg)` gives a live heartbeat. The QTI/`.imscc` package is NOT re-emitted
    here — bank.json + GIFT are; re-run `emit qti`/`emit course` to refresh the Canvas package."""
    from coursekit.discover import find_units
    from coursekit.generate.quiz.bank import Bank
    from coursekit.pipeline import _week_matches

    units = find_units(path)
    if weeks:
        units = [u for u in units if any(_week_matches(w, u) for w in weeks)]

    outcomes: list[FixOutcome] = []
    for u in units:
        bj = Path(u.output_dir) / "bank.json"
        if not bj.exists():
            continue
        bank_obj = Bank.model_validate_json(bj.read_text(encoding="utf-8"))
        transcript = Path(u.transcript_path).read_text(encoding="utf-8")
        if findings is not None:
            flagged = [f for f in findings if f.flagged and f.week == u.week_slug]
        else:
            fnd = ev.evaluate_bank(bank_obj, transcript, provider, model, week=u.week_slug,
                                   project_root=u.course_root, reads=reads, progress=progress)
            flagged = [f for f in fnd if f.flagged]
        if not flagged:
            continue
        bank.load(bank_obj, out_dir=u.output_dir)         # adopt this bank; put_variant autosaves it
        critic = ev._critic_body(ev.EVALUATE_CATEGORY, u.course_root)
        for f in flagged:
            if progress:
                progress(f"fixing {u.week_slug} {f.group_id}/{f.label}…")
            o = fix_one(f, transcript, provider, model, critic=critic,
                        project_root=u.course_root, max_turns=max_turns)
            if progress:
                progress(f"  → {_outcome_word(o)}")
            outcomes.append(o)
        bank.finalize()                                   # re-emit GIFT + quiz.json (deterministic seed)
    return outcomes


def _outcome_word(o: "FixOutcome") -> str:
    return "fixed ✓" if o.now_passes else ("revised, still flagged" if o.replaced else "could not fix")


def render_outcomes(outcomes: list[FixOutcome]) -> str:
    fixed = [o for o in outcomes if o.replaced]
    passing = [o for o in fixed if o.now_passes]
    lines = [f"Fixed {len(fixed)} of {len(outcomes)} flagged question(s); "
             f"{len(passing)} now pass a fresh cold read.", ""]
    for o in outcomes:
        lines.append(f"  [{_outcome_word(o)}] {o.week} {o.group_id}/{o.label}")
    return "\n".join(lines) + "\n"
