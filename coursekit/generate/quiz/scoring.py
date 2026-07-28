"""Scoring the critic against labelled synthetic questions.

Pure functions over verdict strings — no model, no I/O — so the reporting logic is unit-tested offline
and the model-in-the-loop harness (`evals/scorecard.py`) only has to gather the reads.

The metrics answer the questions Increment 10 raised, which a single aggregate recall number hides:

  * recall **by flaw type** — the critic may catch `wrong-answer` easily and `out-of-scope` rarely.
  * **false-flag rate** on the sound questions — recall means nothing if it flags everything.
  * **per-read vs union** — does a second or third cold read actually add catches, or is multi-read a
    no-op on this near-greedy QAT model? The read-disagreement rate makes that explicit: if the reads
    never disagree, the union can add nothing and multi-read is wasted calls.
"""

from __future__ import annotations

from dataclasses import dataclass

# The order flaw types are reported in (matches synthesize.FLAWS / expected.json).
FLAW_ORDER = ("wrong-answer", "missing-context", "garbled-syntax", "out-of-scope")


@dataclass(frozen=True)
class CaseResult:
    """One question's outcome: what it is, and how each cold read judged it."""
    domain: str
    group_id: str
    flaw: str | None            # None => a sound (PASS-expected) case
    reads: tuple[str, ...]      # per-read verdicts, each "PASS" | "FLAG" | "ERROR"

    @property
    def expected_flag(self) -> bool:
        return self.flaw is not None

    @property
    def union_flag(self) -> bool:
        """The critic's real verdict: FLAG if ANY read flagged (evaluate._union's rule)."""
        return any(r == "FLAG" for r in self.reads)

    def read_flag(self, i: int) -> bool:
        return i < len(self.reads) and self.reads[i] == "FLAG"

    @property
    def unanimous(self) -> bool:
        return len(set(self.reads)) <= 1


@dataclass(frozen=True)
class Ratio:
    """A count over a total, so the raw numbers survive alongside the percentage (n=2 vs n=200)."""
    num: int
    den: int

    @property
    def pct(self) -> float | None:
        return (self.num / self.den) if self.den else None

    def __str__(self) -> str:
        p = self.pct
        body = "  –  " if p is None else f"{p:>4.0%}"
        return f"{body} ({self.num}/{self.den})"


def _recall(cases: list[CaseResult], flag_fn) -> Ratio:
    flaws = [c for c in cases if c.expected_flag]
    return Ratio(sum(1 for c in flaws if flag_fn(c)), len(flaws))


def _fpr(cases: list[CaseResult], flag_fn) -> Ratio:
    sound = [c for c in cases if not c.expected_flag]
    return Ratio(sum(1 for c in sound if flag_fn(c)), len(sound))


@dataclass
class Scorecard:
    model: str
    n_reads: int
    n_cases: int
    recall_union: Ratio
    fpr_union: Ratio
    by_flaw: dict[str, Ratio]                       # union recall per flaw type
    by_domain: dict[str, tuple[Ratio, Ratio]]       # domain -> (recall, fpr), union
    per_read_recall: list[Ratio]                    # single-read recall, one entry per read index
    per_read_fpr: list[Ratio]
    disagreement: Ratio                             # cases whose reads were not unanimous / all cases


def build_scorecard(cases: list[CaseResult], *, model: str = "", n_reads: int | None = None) -> Scorecard:
    n_reads = n_reads if n_reads is not None else (max((len(c.reads) for c in cases), default=0))

    union = lambda c: c.union_flag
    flaws = sorted({c.flaw for c in cases if c.flaw}, key=lambda f: (FLAW_ORDER.index(f)
                   if f in FLAW_ORDER else len(FLAW_ORDER), f))
    by_flaw = {f: _recall([c for c in cases if c.flaw == f], union) for f in flaws}

    domains = sorted({c.domain for c in cases})
    by_domain = {d: (_recall([c for c in cases if c.domain == d], union),
                     _fpr([c for c in cases if c.domain == d], union))
                 for d in domains}

    per_read_recall = [_recall(cases, lambda c, i=i: c.read_flag(i)) for i in range(n_reads)]
    per_read_fpr = [_fpr(cases, lambda c, i=i: c.read_flag(i)) for i in range(n_reads)]

    disagree = Ratio(sum(1 for c in cases if not c.unanimous), len(cases))

    return Scorecard(
        model=model, n_reads=n_reads, n_cases=len(cases),
        recall_union=_recall(cases, union),
        fpr_union=_fpr(cases, union),
        by_flaw=by_flaw, by_domain=by_domain,
        per_read_recall=per_read_recall, per_read_fpr=per_read_fpr,
        disagreement=disagree,
    )


def case_verdict(c: CaseResult) -> str:
    """The union verdict as a label: FLAG if any read flagged, else PASS, else ERROR (all reads errored)."""
    if c.union_flag:
        return "FLAG"
    return "PASS" if any(r == "PASS" for r in c.reads) else "ERROR"


def render_cases(cases: list[CaseResult]) -> str:
    """A per-question table so a saved run shows exactly which questions flagged, missed, or false-
    flagged — 'ok' is whether the union verdict matched what the label expected."""
    lines = ["| domain | group | expected | reads | verdict | ok |",
             "|---|---|---|---|---|---|"]
    for c in cases:
        exp = c.flaw or "sound"
        ok = "✓" if (c.union_flag == c.expected_flag) else "✗ MISS" if c.expected_flag else "✗ FALSE-FLAG"
        lines.append(f"| {c.domain} | {c.group_id} | {exp} | {' '.join(c.reads)} | "
                     f"{case_verdict(c)} | {ok} |")
    return "\n".join(lines) + "\n"


def parse_cases_table(text: str) -> dict[tuple[str, str], dict]:
    """Inverse of render_cases: pull {(domain, group): {'expected', 'verdict'}} back out of a saved
    scorecard's per-question table, so two runs can be compared without re-running the model."""
    rows: dict[tuple[str, str], dict] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 6 or cells[0] == "domain":
            continue
        domain, group, expected, _reads, verdict, _ok = cells
        rows[(domain, group)] = {"expected": expected, "verdict": verdict}
    return rows


def summarize_rows(rows: dict[tuple[str, str], dict]) -> tuple[Ratio, Ratio]:
    """(recall, false-flag rate) over parsed rows — 'sound' rows are the negatives, all else flaws."""
    flaws = [r for r in rows.values() if r["expected"] != "sound"]
    sound = [r for r in rows.values() if r["expected"] == "sound"]
    return (Ratio(sum(r["verdict"] == "FLAG" for r in flaws), len(flaws)),
            Ratio(sum(r["verdict"] == "FLAG" for r in sound), len(sound)))


def render(sc: Scorecard) -> str:
    L = [
        f"=== critic scorecard · model={sc.model or '?'} · {sc.n_reads} read(s)/question · "
        f"{sc.n_cases} cases ===",
        "",
        f"  UNION recall (flaws caught):   {sc.recall_union}",
        f"  UNION false-flag rate (sound): {sc.fpr_union}",
        "",
        "  recall by flaw type (union):",
    ]
    for flaw, r in sc.by_flaw.items():
        L.append(f"    {flaw:16} {r}")
    L += ["", "  by domain (union):", f"    {'domain':10} {'recall':>16}   {'false-flag':>16}"]
    for d, (rec, fpr) in sc.by_domain.items():
        L.append(f"    {d:10} {str(rec):>16}   {str(fpr):>16}")

    L += ["", "  per-read vs union (does an extra read add catches?):",
          f"    {'read':10} {'recall':>16}   {'false-flag':>16}"]
    for i, (rec, fpr) in enumerate(zip(sc.per_read_recall, sc.per_read_fpr)):
        L.append(f"    read {i:<5} {str(rec):>16}   {str(fpr):>16}")
    L.append(f"    {'UNION':10} {str(sc.recall_union):>16}   {str(sc.fpr_union):>16}")
    L += ["",
          f"  read disagreement: {sc.disagreement}  "
          f"(0/N ⇒ reads never differ ⇒ multi-read is a no-op on this model)", ""]
    return "\n".join(L)
