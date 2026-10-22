import textwrap
from pathlib import Path
import pytest
from coursekit.discover import Unit, find_units, slugify


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
    assert units[0].week_num == "3"          # carried, so consumers don't re-derive it from the slug


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
    assert unit.week_num is None             # a non-week unit carries no number


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


# ------------------------------------------------------------- manifest-driven discovery (FLOW-7)

def _manifest_course(tmp_path, context_body: str) -> Path:
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    (root / ".vtconfig" / "context.yaml").write_text(context_body, encoding="utf-8")
    return root


def test_manifest_declared_weeks_drive_discovery_with_arbitrary_doc_names(tmp_path):
    # a DECLARED structure (doc/sources per week) is authoritative — so a week doc can be named
    # anything, not just week-N.md, and week identity/label/module come from the manifest.
    root = _manifest_course(tmp_path, textwrap.dedent("""
        course_title: Digital Photography
        weeks:
          "week 3":
            title: Exposure
            module: Unit 2
            doc: docs/exposure.md
            sources:
              - {path: readings/barrett.pdf, kind: reading}
          "week 4":
            title: Composition
            doc: docs/composition.md
    """))
    (root / "docs").mkdir()
    (root / "docs" / "exposure.md").write_text("exposure body", encoding="utf-8")
    (root / "docs" / "composition.md").write_text("composition body", encoding="utf-8")

    units = find_units(root)
    assert [u.week_slug for u in units] == ["week-3", "week-4"]
    u3 = units[0]
    assert u3.week_num == "3"
    assert u3.transcript_path == (root / "docs" / "exposure.md").resolve()   # arbitrary name works
    assert u3.week_label == "Week 3: Exposure" and u3.module == "Unit 2"
    assert u3.course_root == root.resolve()
    assert u3.output_dir == (root / "quizzes" / "week-3").resolve()


def test_manifest_week_with_sources_but_no_doc_uses_the_default_output_path(tmp_path):
    root = _manifest_course(tmp_path, textwrap.dedent("""
        weeks:
          "week 3":
            sources:
              - {path: readings/x.pdf, kind: reading}
    """))
    (root / "output").mkdir()
    (root / "output" / "week-3.md").write_text("consolidated", encoding="utf-8")
    units = find_units(root)
    assert len(units) == 1
    assert units[0].transcript_path == (root / "output" / "week-3.md").resolve()


def test_manifest_skips_a_declared_week_whose_doc_is_not_on_disk(tmp_path):
    # a declared-but-not-yet-ingested week is skipped, exactly as the glob skips a missing file
    root = _manifest_course(tmp_path, textwrap.dedent("""
        weeks:
          "week 3": {doc: docs/w3.md}
          "week 5": {doc: docs/w5.md}
    """))
    (root / "docs").mkdir()
    (root / "docs" / "w3.md").write_text("body", encoding="utf-8")     # w5 intentionally absent
    assert [u.week_slug for u in find_units(root)] == ["week-3"]


def test_decoration_only_context_still_uses_the_glob(tmp_path):
    # title/module WITHOUT doc/sources must NOT trigger manifest discovery — the glob still runs and
    # enrichment still applies (back-compat with today's transcriber courses).
    root = _manifest_course(tmp_path, textwrap.dedent("""
        course_title: C
        weeks:
          "week 3": {title: T, module: M}
    """))
    (root / "output").mkdir()
    (root / "output" / "week-3.md").write_text("body", encoding="utf-8")
    units = find_units(root)
    assert [u.week_slug for u in units] == ["week-3"]
    assert units[0].transcript_path == (root / "output" / "week-3.md").resolve()   # from the glob
    assert units[0].week_label == "Week 3: T"                                       # still enriched
