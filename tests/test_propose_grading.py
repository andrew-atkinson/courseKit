"""The grading-group proposer (STRC-2) — offline. Scans a course's generated artifacts and drafts a
`grading:` block of equal-weight placeholders into coursekit's overlay, preserving any `weeks` block."""

import pytest

from coursekit import courseconfig
from coursekit.ingest import propose_grading as pg


def _course(tmp_path, *, assignments=True, quizzes=True):
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    if assignments:
        d = root / "assignments" / "week-3"
        d.mkdir(parents=True)
        (d / "assignment.json").write_text("{}", encoding="utf-8")
    if quizzes:
        d = root / "quizzes" / "week-3"
        d.mkdir(parents=True)
        (d / "bank.json").write_text("{}", encoding="utf-8")
    return root


def test_proposes_a_group_per_kind_with_equal_placeholder_weights(tmp_path):
    g = pg.propose_grading(_course(tmp_path))
    assert [x["name"] for x in g["groups"]] == ["Assignments", "Quizzes"]
    assert sum(x["weight"] for x in g["groups"]) == 100.0        # equal placeholders, summing to 100
    assert g["groups"][0]["weight"] == 50.0
    assert g["placement"] == {"assignment": "Assignments", "quiz": "Quizzes"}


def test_only_the_kinds_present_are_proposed(tmp_path):
    g = pg.propose_grading(_course(tmp_path, quizzes=False))
    assert [x["name"] for x in g["groups"]] == ["Assignments"]
    assert g["groups"][0]["weight"] == 100.0


def test_no_graded_artifacts_yields_empty(tmp_path):
    assert pg.propose_grading(_course(tmp_path, assignments=False, quizzes=False)) == {}


def test_write_preserves_weeks_and_refuses_to_clobber(tmp_path):
    root = _course(tmp_path)
    overlay = root / ".vtconfig" / "structure.coursekit.yaml"
    overlay.write_text('weeks:\n  "week 3": {doc: output/week-3.md}\n', encoding="utf-8")

    dest = pg.write_grading(root, pg.propose_grading(root))
    data = courseconfig._read_yaml(dest)
    assert "week 3" in data["weeks"]                             # the weeks block survived the merge
    assert data["grading"]["groups"][0]["name"] == "Assignments"

    with pytest.raises(SystemExit):                             # a second write refuses without --force
        pg.write_grading(root, pg.propose_grading(root))
    pg.write_grading(root, pg.propose_grading(root), force=True)  # --force redrafts
