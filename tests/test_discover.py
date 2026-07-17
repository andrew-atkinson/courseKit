import textwrap
from pathlib import Path

import pytest

from discover import Unit, find_units, slugify


# ------------------------------------------------------------- slugify

@pytest.mark.parametrize("raw,expected", [
    ("Week 3", "week-3"),
    ("CC101_01FA00 SPECIAL TOPICS-ART AND DESIGN", "cc101-01fa00-special-topics-art-and-design"),
    ("  spaced  out  ", "spaced-out"),
    ("Module 2 – Chaos", "module-2-chaos"),  # en dash
    ("!!!", "untitled"),
    ("", "untitled"),
])
def test_slugify(raw, expected):
    assert slugify(raw) == expected


# ------------------------------------------------------- single file

def test_single_file_yields_one_unit(tmp_path):
    f = tmp_path / "week-3.md"
    f.write_text("body", encoding="utf-8")
    units = find_units(f)
    assert len(units) == 1
    assert units[0].transcript_path == f.resolve()
    assert units[0].week_slug == "week-3"


def test_single_file_without_vtconfig_anchors_output_beside_it(tmp_path):
    f = tmp_path / "week-3.md"
    f.write_text("body", encoding="utf-8")
    unit = find_units(f)[0]
    assert unit.course_root is None
    assert unit.output_dir == (tmp_path / "quizzes" / "week-3").resolve()


def test_non_week_filename_still_works(tmp_path):
    f = tmp_path / "lecture-notes.md"
    f.write_text("body", encoding="utf-8")
    unit = find_units(f)[0]
    assert unit.week_slug == "lecture-notes"
    assert unit.week_label == "lecture-notes"


# ------------------------------------------------------- directory

def test_directory_finds_combined_week_docs_only(tmp_path):
    # Combined docs, plus a per-video file that must be excluded.
    (tmp_path / "week 3").mkdir()
    (tmp_path / "week 3" / "week-3.md").write_text("w3", encoding="utf-8")
    (tmp_path / "week 3" / "1 hand coding repeats.md").write_text("vid", encoding="utf-8")
    (tmp_path / "week 4").mkdir()
    (tmp_path / "week 4" / "week-4.md").write_text("w4", encoding="utf-8")

    units = find_units(tmp_path)
    slugs = sorted(u.week_slug for u in units)
    assert slugs == ["week-3", "week-4"]  # the per-video .md is excluded


def test_directory_without_vtconfig_anchors_output_under_the_directory(tmp_path):
    (tmp_path / "week 3").mkdir()
    (tmp_path / "week 3" / "week-3.md").write_text("w3", encoding="utf-8")
    unit = find_units(tmp_path)[0]
    assert unit.output_dir == (tmp_path / "quizzes" / "week-3").resolve()


# --------------------------------------------------- .vtconfig enrichment

def _make_course(tmp_path) -> Path:
    """A course root with a .vtconfig/context.yaml and one week transcript."""
    root = tmp_path / "CC101" / "course export"
    (root / ".vtconfig").mkdir(parents=True)
    (root / ".vtconfig" / "context.yaml").write_text(textwrap.dedent("""\
        course_title: CC101_01FA00 SPECIAL TOPICS-ART AND DESIGN
        weeks:
          week 3:
            title: Repetition
            module: Module 2 - Chaos and Control
            folder: week 3
    """), encoding="utf-8")
    (root / "output" / "week 3").mkdir(parents=True)
    (root / "output" / "week 3" / "week-3.md").write_text("transcript body", encoding="utf-8")
    return root


def test_vtconfig_enriches_course_and_week(tmp_path):
    root = _make_course(tmp_path)
    unit = find_units(root / "output" / "week 3" / "week-3.md")[0]
    assert unit.course_root == root.resolve()
    assert unit.course_title == "CC101_01FA00 SPECIAL TOPICS-ART AND DESIGN"
    assert unit.week_label == "Week 3: Repetition"
    assert unit.module == "Module 2 - Chaos and Control"


def test_vtconfig_output_is_sibling_quizzes_tree_under_course_root(tmp_path):
    root = _make_course(tmp_path)
    unit = find_units(root / "output" / "week 3" / "week-3.md")[0]
    # Beside the transcriber's output/, not inside the app.
    assert unit.output_dir == (root / "quizzes" / "week-3").resolve()


def test_course_root_found_by_walking_up_from_a_directory_scan(tmp_path):
    root = _make_course(tmp_path)
    # Point at the course root itself; the week doc is nested under output/.
    units = find_units(root)
    assert len(units) == 1
    assert units[0].course_root == root.resolve()
    assert units[0].output_dir == (root / "quizzes" / "week-3").resolve()


def test_missing_pyyaml_degrades_gracefully(tmp_path, monkeypatch):
    root = _make_course(tmp_path)
    # Simulate pyyaml being unavailable.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    unit = find_units(root / "output" / "week 3" / "week-3.md")[0]
    # No enrichment, but still a valid unit anchored at the course root.
    assert unit.course_title is None
    assert unit.week_label == "Week 3"  # falls back to number-only, no title
    assert unit.course_root == root.resolve()


# ----------------------------------------------------- output_root override

def test_output_root_override_uses_course_slug(tmp_path):
    root = _make_course(tmp_path)
    out = tmp_path / "scratch"
    unit = find_units(root / "output" / "week 3" / "week-3.md", output_root=out)[0]
    assert unit.output_dir == (out / unit.course_slug / "week-3").resolve()


# --------------------------------------------------------------- errors

def test_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_units(tmp_path / "nope")


# ------------------------------------------------ stray-file exclusion

def test_media_tree_week_docs_are_excluded_when_output_exists(tmp_path):
    root = _make_course(tmp_path)
    # A stray combined-looking doc in media/ that must NOT be collected.
    (root / "media" / "week 4").mkdir(parents=True)
    (root / "media" / "week 4" / "week-4.md").write_text("stray", encoding="utf-8")
    (root / "output" / "week 4").mkdir(parents=True)
    (root / "output" / "week 4" / "week-4.md").write_text("real", encoding="utf-8")

    units = find_units(root)
    paths = sorted(str(u.transcript_path) for u in units)
    assert all("/media/" not in p for p in paths)
    assert any(p.endswith("output/week 4/week-4.md") for p in paths)


def test_output_collision_raises_rather_than_clobbering(tmp_path):
    # Two week-3 docs under output/ resolving to the same quizzes/week-3 dir.
    d = tmp_path / "docs"
    (d / "a").mkdir(parents=True)
    (d / "b").mkdir(parents=True)
    (d / "a" / "week-3.md").write_text("one", encoding="utf-8")
    (d / "b" / "week-3.md").write_text("two", encoding="utf-8")
    with pytest.raises(ValueError, match="same output directory"):
        find_units(d)
