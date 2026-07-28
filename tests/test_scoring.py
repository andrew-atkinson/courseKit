"""Offline tests for the critic scoring math. No model: fabricated per-read verdicts in, metrics out.

These pin the numbers a live scorecard reports, so the reporting logic is trustworthy before any model
call — the model run only supplies the verdict strings."""

from coursekit.generate.quiz.scoring import (
    CaseResult, Ratio, build_scorecard, case_verdict, parse_cases_table, render,
    render_cases, summarize_rows,
)

# A hand-computed fixture (2 reads each):
#   1  A  wrong-answer     (FLAG, PASS)  -> union FLAG   (caught)
#   2  A  out-of-scope     (PASS, PASS)  -> union PASS   (missed)
#   3  A  sound            (PASS, PASS)  -> union PASS   (ok)
#   4  A  sound            (FLAG, PASS)  -> union FLAG   (false flag)
#   5  B  missing-context  (PASS, FLAG)  -> union FLAG   (caught)
CASES = [
    CaseResult("A", "c1", "wrong-answer", ("FLAG", "PASS")),
    CaseResult("A", "c2", "out-of-scope", ("PASS", "PASS")),
    CaseResult("A", "c3", None, ("PASS", "PASS")),
    CaseResult("A", "c4", None, ("FLAG", "PASS")),
    CaseResult("B", "c5", "missing-context", ("PASS", "FLAG")),
]


def _r(ratio: Ratio) -> tuple[int, int]:
    return (ratio.num, ratio.den)


def test_case_flags():
    assert CASES[0].union_flag and not CASES[1].union_flag
    assert CASES[2].expected_flag is False and CASES[0].expected_flag is True
    assert CASES[0].read_flag(0) and not CASES[0].read_flag(1)
    assert CASES[1].unanimous and not CASES[0].unanimous


def test_union_recall_and_fpr():
    sc = build_scorecard(CASES, model="m")
    assert sc.n_reads == 2 and sc.n_cases == 5
    assert _r(sc.recall_union) == (2, 3)     # caught 2 of 3 planted flaws
    assert _r(sc.fpr_union) == (1, 2)        # 1 of 2 sound questions falsely flagged


def test_recall_by_flaw_type():
    sc = build_scorecard(CASES)
    assert _r(sc.by_flaw["wrong-answer"]) == (1, 1)
    assert _r(sc.by_flaw["out-of-scope"]) == (0, 1)
    assert _r(sc.by_flaw["missing-context"]) == (1, 1)
    # ordering follows FLAW_ORDER, and garbled-syntax (absent here) is not invented
    assert list(sc.by_flaw) == ["wrong-answer", "missing-context", "out-of-scope"]


def test_by_domain():
    sc = build_scorecard(CASES)
    rec_a, fpr_a = sc.by_domain["A"]
    rec_b, fpr_b = sc.by_domain["B"]
    assert _r(rec_a) == (1, 2) and _r(fpr_a) == (1, 2)
    assert _r(rec_b) == (1, 1)
    assert _r(fpr_b) == (0, 0) and fpr_b.pct is None    # no sound questions in B -> undefined, not 0%


def test_per_read_vs_union_and_disagreement():
    sc = build_scorecard(CASES)
    assert [_r(x) for x in sc.per_read_recall] == [(1, 3), (1, 3)]  # each single read catches 1/3
    assert _r(sc.recall_union) == (2, 3)                            # union catches more -> multi-read helps
    assert [_r(x) for x in sc.per_read_fpr] == [(1, 2), (0, 2)]
    assert _r(sc.disagreement) == (3, 5)                            # 3 cases where the reads differed


def test_disagreement_zero_when_reads_never_differ():
    cases = [CaseResult("A", "c1", "wrong-answer", ("FLAG", "FLAG")),
             CaseResult("A", "c2", None, ("PASS", "PASS"))]
    sc = build_scorecard(cases)
    assert _r(sc.disagreement) == (0, 2)   # the multi-read-is-a-no-op signal


def test_case_verdict_and_per_case_table():
    assert case_verdict(CASES[0]) == "FLAG"           # a read flagged
    assert case_verdict(CASES[2]) == "PASS"           # all reads passed
    assert case_verdict(CaseResult("A", "cX", "wrong-answer", ("ERROR", "ERROR"))) == "ERROR"

    table = render_cases(CASES)
    assert "| domain | group | expected | reads | verdict | ok |" in table
    assert "wrong-answer" in table and "sound" in table
    assert "✗ MISS" in table          # c2: expected FLAG, union PASS -> a missed flaw
    assert "✗ FALSE-FLAG" in table    # c4: expected PASS, union FLAG -> a false flag


def test_parse_round_trips_render_cases():
    """The per-question table a run saves must read back with the same recall/FPR — that is what lets
    compare.py diff two runs without re-running the model."""
    rows = parse_cases_table(render_cases(CASES))
    assert len(rows) == len(CASES)
    rec, fpr = summarize_rows(rows)
    sc = build_scorecard(CASES)
    assert (rec.num, rec.den) == (sc.recall_union.num, sc.recall_union.den)
    assert (fpr.num, fpr.den) == (sc.fpr_union.num, sc.fpr_union.den)


def test_render_is_readable_text():
    out = render(build_scorecard(CASES, model="m"))
    assert "UNION recall" in out
    assert "wrong-answer" in out and "read disagreement" in out
    assert "(2/3)" in out                  # the raw counts survive next to the percentage
