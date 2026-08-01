"""The versioned evaluation run-store — snapshots each run, never overwrites."""

import json

from coursekit.evalstore import archive_evaluation


def test_archive_snapshots_reviews_summary_and_ledger(tmp_path):
    course = tmp_path / "course"
    course.mkdir()
    q = course / "quizzes" / "quiz-review.md"
    q.parent.mkdir(parents=True)
    q.write_text("# Quiz review — 4 flagged\n")
    metrics = {"quiz": {"reviewed": 192, "flagged": 4}, "page": {"reviewed": 190, "flagged": 1}}

    run_dir = archive_evaluation(course, model="fake-model", reviews=[q], metrics=metrics)

    assert run_dir is not None and run_dir.parent == course / "evals"
    assert (run_dir / "quiz-review.md").read_text().startswith("# Quiz review")   # copied, immutable
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["model"] == "fake-model" and summary["metrics"] == metrics
    assert "coursekit_commit" in summary
    ledger = (course / "evals" / "log.jsonl").read_text().strip().splitlines()
    assert len(ledger) == 1
    row = json.loads(ledger[0])
    assert row["quiz_flagged"] == 4 and row["page_reviewed"] == 190 and row["model"] == "fake-model"


def test_none_course_root_is_a_noop(tmp_path):
    assert archive_evaluation(None, model="m", reviews=[], metrics={}) is None


def test_two_runs_append_two_ledger_rows_and_distinct_dirs(tmp_path):
    course = tmp_path / "c"
    course.mkdir()
    d1 = archive_evaluation(course, model="m", reviews=[], metrics={"quiz": {"flagged": 4}})
    d2 = archive_evaluation(course, model="m", reviews=[], metrics={"quiz": {"flagged": 2}})
    assert d1 != d2                                                   # each run its own dir (collision-safe)
    rows = (course / "evals" / "log.jsonl").read_text().strip().splitlines()
    assert len(rows) == 2                                             # accumulates, never overwrites
    assert [json.loads(r)["quiz_flagged"] for r in rows] == [4, 2]    # a readable trend
