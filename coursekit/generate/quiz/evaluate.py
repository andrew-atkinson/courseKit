"""A cold-read critic pass over generated quiz questions.

The generators commit whatever the local model produces; this is the quality gate that reads each
finished question back — in a FRESH context (no generation history), against the week's actual
material — and flags ones that drift out of scope, lack the context to be answerable, mark the wrong
answer, or show garbled notation. v1 only *reports*: it never edits or regenerates, so a human stays
in the loop. Auto-regeneration of flagged questions is a deliberate later increment.

The critic is the same local model by default (a fresh conversation is what makes it a cold read, not
the generator grading its own homework); a course can point it at a different model via
`evaluate.yaml`'s `model:` key.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from coursekit import prompts

EVALUATE_CATEGORY = "quiz"


# The critic reads at a moderate temperature ON PURPOSE: multi-read only helps if the reads vary, and
# a local model catches a *different* subset of flaws each pass. Union across N reads recovers most.
READ_TEMPERATURE = 0.4
DEFAULT_READS = 3


@dataclass
class Finding:
    week: str
    group_id: str
    label: str
    stem: str
    verdict: str        # "PASS" | "FLAG" | "ERROR"
    concern: str = ""
    fix: str = ""
    n_flag: int = 0     # how many of the reads flagged it (a confidence signal)
    n_reads: int = 1

    @property
    def flagged(self) -> bool:
        return self.verdict == "FLAG"


def _answer_line(v) -> str:
    """A compact rendering of the marked answer, per question kind, so the critic can judge #3."""
    kind = getattr(v, "kind", "")
    if kind == "multiple_choice":
        return "\n".join(f"  {'*' if i == v.correct_index else ' '} {o}"
                         for i, o in enumerate(v.options)) + "\n(* = the marked-correct option)"
    if kind == "true_false":
        return f"  Marked answer: {v.correct_answer}"
    if kind == "multiple_answer":
        marked = {i for i in v.correct_indices}
        return "\n".join(f"  {'*' if i in marked else ' '} {o}" for i, o in enumerate(v.options))
    if kind == "short_answer":
        return f"  Accepted answers: {', '.join(v.accepted_answers)}"
    if kind == "numerical":
        return f"  Answer: {v.answer} (± {v.tolerance})"
    if kind == "matching":
        return "\n".join(f"  {p.left} -> {p.right}" for p in v.pairs)
    return "  (answer shape not rendered)"


def _format_question(v) -> str:
    return f"[{getattr(v, 'kind', '?')}] {v.question_text}\n{_answer_line(v)}"


_VERDICT = re.compile(r"VERDICT:\s*(PASS|FLAG)", re.IGNORECASE)
_CONCERN = re.compile(r"CONCERN:\s*(.*)")
_FIX = re.compile(r"FIX:\s*(.*)")


def _parse_verdict(reply: str) -> tuple[str, str, str]:
    """Lenient parse of the critic's reply into (verdict, concern, fix). An unreadable reply is an
    ERROR finding rather than a crash — a flaky local model must not sink the whole review."""
    m = _VERDICT.search(reply or "")
    if not m:
        return "ERROR", "could not read a VERDICT from the critic's reply", ""
    verdict = m.group(1).upper()
    concern = (c.group(1).strip() if (c := _CONCERN.search(reply)) else "")
    fix = (f.group(1).strip() if (f := _FIX.search(reply)) else "")
    return verdict, concern, fix


def _one_read(critic: str, transcript: str, v, provider, model: str) -> tuple[str, str, str]:
    user = (f"The week's teaching material:\n<material>\n{transcript}\n</material>\n\n"
            f"The question to review:\n{_format_question(v)}\n\nEvaluate this question.")
    messages = [{"role": "system", "content": critic}, {"role": "user", "content": user}]
    try:
        reply = provider.chat(model=model, messages=messages, temperature=READ_TEMPERATURE)
        return _parse_verdict(reply)
    except Exception as e:   # a provider hiccup on one read shouldn't abort the review
        return "ERROR", f"critic call failed: {e}"[:160], ""


def _union(reads: list[tuple[str, str, str]]) -> tuple[str, str, str, int]:
    """Combine N cold reads: FLAG if *any* read flagged (a local model catches a different subset each
    pass, so the union recovers most), keeping the distinct concerns. Only all-ERROR stays ERROR."""
    flags = [(c, f) for (verdict, c, f) in reads if verdict == "FLAG"]
    if flags:
        concern = " | ".join(dict.fromkeys(c for c, _ in flags if c))
        fix = next((f for _, f in flags if f), "")
        return "FLAG", concern, fix, len(flags)
    if any(verdict == "PASS" for verdict, _, _ in reads):
        return "PASS", "", "", 0
    return "ERROR", "every read failed", "", 0


def evaluate_bank(bank, transcript: str, provider, model: str, *, week: str = "",
                  project_root=None, reads: int = DEFAULT_READS) -> list[Finding]:
    """Cold-read every variant `reads` times and union the verdicts — several independent fresh reads,
    flag if any flags. That is what turns a noisy local critic ('a different 3 of 4 each run') into a
    dependable one."""
    critic = prompts.load(EVALUATE_CATEGORY, "critic", project_root=project_root).body
    findings = []
    for g in bank.groups.values():
        for v in g.variants.values():
            results = [_one_read(critic, transcript, v, provider, model) for _ in range(max(1, reads))]
            verdict, concern, fix, n_flag = _union(results)
            findings.append(Finding(week, g.group_id, v.label, v.question_text.strip(),
                                    verdict, concern, fix, n_flag=n_flag, n_reads=len(results)))
    return findings


def evaluate_course(path, *, weeks=None, provider, model, out_path=None,
                    reads: int = DEFAULT_READS) -> tuple[list[Finding], Path | None]:
    """Discover a course's weeks, pair each `bank.json` with its transcript, cold-read every
    question `reads` times, and write one `quiz-review.md`. Returns (findings, review_path_or_None)."""
    from coursekit.discover import find_units
    from coursekit.generate.quiz.bank import Bank
    from coursekit.pipeline import _week_matches

    units = find_units(path)
    if weeks:
        units = [u for u in units if any(_week_matches(w, u) for w in weeks)]

    findings: list[Finding] = []
    for u in units:
        bj = Path(u.output_dir) / "bank.json"
        if not bj.exists():
            continue
        bank = Bank.model_validate_json(bj.read_text(encoding="utf-8"))
        transcript = Path(u.transcript_path).read_text(encoding="utf-8")
        findings += evaluate_bank(bank, transcript, provider, model,
                                  week=u.week_slug, project_root=u.course_root, reads=reads)

    if not findings:
        return [], None
    if out_path is None:
        base = Path(units[0].output_dir).parent   # the course's quizzes/ tree
        out_path = base / "quiz-review.md"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_review(findings), encoding="utf-8")
    return findings, out_path


def render_review(findings: list[Finding]) -> str:
    """A Markdown review of the flagged (and errored) questions — the passing ones are omitted."""
    review = [f for f in findings if f.verdict != "PASS"]     # FLAG + ERROR both want a look
    lines = [f"# Quiz review — {len(review)} of {len(findings)} question(s) flagged", ""]
    if not review:
        lines.append("Every question passed the cold read. Nothing to review.")
        return "\n".join(lines) + "\n"
    for f in review:
        stem = f.stem if len(f.stem) <= 140 else f.stem[:137] + "…"
        conf = f" ({f.n_flag}/{f.n_reads} reads)" if (f.verdict == "FLAG" and f.n_reads > 1) else ""
        lines += [f"## {f.week} · {f.group_id}/{f.label} — {f.verdict}{conf}",
                  f"> {stem}", ""]
        if f.concern:
            lines.append(f"- **Concern:** {f.concern}")
        if f.fix:
            lines.append(f"- **Fix:** {f.fix}")
        lines.append("")
    return "\n".join(lines) + "\n"
