"""Targeted quizzes (ASMT-17) — a quiz scoped to ONE document, not the whole week.

Offline: the scoping logic (distinct slug, extracted material, unit construction) is what ASMT-17
adds; the generation itself is the ordinary quiz engine, exercised elsewhere. `run_unit` is
monkeypatched so these run without a model.
"""

from pathlib import Path

import pytest

from coursekit.generate.quiz import targeted


def test_targeted_slug_carries_the_week_and_the_doc():
    assert targeted.targeted_slug(Path("/c/course/week-5/slides/Exposure.pptx")) == "week-5-exposure"
    assert targeted.targeted_slug(
        Path("/c/course/week-12/readings/Barrett Reading.pdf")) == "week-12-barrett-reading"
    assert targeted.targeted_slug(Path("/c/loose/Some Reading.md")) == "some-reading"   # no week ancestor


def _course(tmp_path):
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    src = root / "week-3" / "readings" / "The Nature of Photographs.md"
    src.parent.mkdir(parents=True)
    src.write_text("Photographs describe the world in a particular way.", encoding="utf-8")
    return root, src


def test_generate_targeted_quiz_scopes_to_a_distinct_slug(tmp_path, monkeypatch):
    root, src = _course(tmp_path)
    seen = {}
    import coursekit.pipeline as pl
    monkeypatch.setattr(pl, "run_unit", lambda unit, *a, **k: seen.setdefault("unit", unit))

    targeted.generate_targeted_quiz(src, provider=None, model="m")
    u = seen["unit"]
    # a DISTINCT slug — never collides with the plain week-3 quiz or another element's
    assert u.week_slug == "week-3-the-nature-of-photographs"
    assert u.output_dir.name == "week-3-the-nature-of-photographs" and u.output_dir.parent.name == "quizzes"
    # the extracted text is persisted as the unit's material (also a record of what was quizzed)
    assert u.transcript_path == u.output_dir / "source.md"
    assert (u.output_dir / "source.md").read_text().startswith("Photographs describe")
    # the course root is found, so domain.md / quiz.yaml resolve from it
    assert u.course_root == root.resolve()


def test_unsupported_source_is_rejected(tmp_path):
    root, _ = _course(tmp_path)
    bad = root / "week-3" / "photo.jpg"          # an image — coursekit is text-only
    bad.write_text("not really a jpeg", encoding="utf-8")
    with pytest.raises(SystemExit):
        targeted.generate_targeted_quiz(bad, None, "m")


def test_missing_source_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        targeted.generate_targeted_quiz(tmp_path / "nope.md", None, "m")


def test_cli_targeted_handler_runs_end_to_end(monkeypatch, tmp_path):
    # Exercise the CLI handler body (not just arg parsing) — the layer where a `Path` NameError hid.
    import types
    from coursekit import cli
    monkeypatch.setenv("MODEL_NAME", "m")
    monkeypatch.setattr(cli, "_build_provider", lambda: object())
    seen = {}

    def _fake(source, provider, model, **kw):
        seen["source"] = source
        return types.SimpleNamespace(finalized=True, n_groups=3, n_variants=12,
                                     output_dir=tmp_path, problems=[])

    monkeypatch.setattr(targeted, "generate_targeted_quiz", _fake)
    args = types.SimpleNamespace(pages=False, dry_run=False, source="/c/week-3/reading.pdf",
                                 output_root=None, max_iters=80)
    assert cli._cmd_generate_targeted(args) == 0
    assert seen["source"] == "/c/week-3/reading.pdf"
