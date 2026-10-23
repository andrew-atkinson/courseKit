"""The structure proposer (FLOW-7 Phase 2). Offline: it scans a tree and writes coursekit's own
overlay — no model. The round-trip test confirms what it writes is what the reader then composes."""

import pytest

from coursekit.coursestructure import CourseStructure
from coursekit.ingest import propose as P
from coursekit.outcomes import CoursekitError


def _course(tmp_path):
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    return root


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")


def test_propose_groups_folder_per_week_and_surfaces_unassigned(tmp_path):
    root = _course(tmp_path)
    _touch(root / "week-3" / "readings" / "Barrett.pdf")
    _touch(root / "week-3" / "slides" / "ISO.pptx")
    _touch(root / "week-4" / "Composition.md")
    _touch(root / "syllabus.pdf")                       # root-level, no week -> unassigned

    prop = P.propose(root)
    assert list(prop.weeks) == ["week 3", "week 4"]     # numeric order
    assert prop.root == root.resolve()
    # a file with no keyable week is surfaced, not dropped
    assert [p.name for p in prop.unassigned] == ["syllabus.pdf"]


def test_propose_classifies_kind_and_framing(tmp_path):
    root = _course(tmp_path)
    _touch(root / "week-3" / "overview.md")             # framing (an outline/overview)
    _touch(root / "week-3" / "Barrett.pdf")             # reading
    _touch(root / "week-3" / "ISO.pptx")                # slides

    srcs = P.propose(root).weeks["week 3"]["sources"]
    assert srcs[0]["role"] == "framing" and srcs[0]["path"].endswith("overview.md")   # framing first
    kinds = {s["path"].split("/")[-1]: s["kind"] for s in srcs}
    assert kinds == {"overview.md": "notes", "Barrett.pdf": "reading", "ISO.pptx": "slides"}


def test_propose_excludes_generated_trees(tmp_path):
    root = _course(tmp_path)
    _touch(root / "week-3" / "reading.md")
    _touch(root / "output" / "week-3.md")               # generated week text
    _touch(root / "quizzes" / "week-3" / "source.md")   # generated artifact
    _touch(root / ".vtconfig" / "notes.md")             # config tree

    srcs = P.propose(root).weeks["week 3"]["sources"]
    assert [s["path"] for s in srcs] == ["week-3/reading.md"]   # only the real source


def test_write_overlay_then_reader_composes_it(tmp_path):
    root = _course(tmp_path)
    _touch(root / "week-3" / "Barrett.pdf")
    dest = P.write_overlay(P.propose(root))
    assert dest == root / ".vtconfig" / "structure.coursekit.yaml"

    # what it wrote is what the reader reads back
    s = CourseStructure.load(root)
    assert s.has_declared_structure()
    got = s.sources_for("3")
    assert len(got) == 1 and got[0].kind == "reading"
    assert got[0].resolve(root) == root / "week-3" / "Barrett.pdf"   # root-relative path resolves


def test_write_overlay_refuses_overwrite_without_force(tmp_path):
    root = _course(tmp_path)
    _touch(root / "week-3" / "a.pdf")
    P.write_overlay(P.propose(root))
    with pytest.raises(CoursekitError, match="already declares `weeks:`") as e:
        P.write_overlay(P.propose(root))
    assert e.value.code == "overlay.section_exists"                # a second run must not clobber edits
    P.write_overlay(P.propose(root), force=True)        # ...unless forced


def test_write_overlay_without_a_root_errors(tmp_path):
    # no .vtconfig anywhere -> nowhere to put the overlay
    _touch(tmp_path / "loose" / "week-3.md")
    with pytest.raises(CoursekitError, match="course root") as e:
        P.write_overlay(P.propose(tmp_path / "loose"))
    assert e.value.code == "course.no_root" and e.value.category == "config"


def test_force_redrafts_the_weeks_but_keeps_grading_and_expectations(tmp_path):
    # Regression: write_overlay used to write a fresh file holding only `weeks:`, so
    # `propose --force` silently deleted the faculty's grading weights and expectations.
    from coursekit import settings
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    _touch(root / "week-3" / "a.pdf")
    P.write_overlay(P.propose(root))
    settings.set(root, "grading.groups.Projects.weight", 60)
    settings.set(root, "expect.defaults", [{"scope": "week", "artifact": "page"}])
    P.write_overlay(P.propose(root), force=True)
    data = settings.read(root, "structure")
    assert data["grading"]["groups"] == [{"name": "Projects", "weight": 60.0}]
    assert data["expect"]["defaults"] == [{"scope": "week", "artifact": "page"}]
    assert data["weeks"]
