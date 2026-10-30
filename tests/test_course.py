"""CORE-2 step 1 — the course model. Units have their own identity and a STORED order; artifacts are
owned by one rule that prefers their own `week_ref` — so a GUI can reorder units and move artifacts
by writing data, never by renaming things (agent/core-2-design.md §4a)."""

import json

import pytest

from coursekit import outcomes, settings
from coursekit.course import Course, owner
from coursekit.outcomes import CoursekitError


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "course"
    (r / ".vtconfig").mkdir(parents=True)
    return r


def _doc(root, num):
    p = root / "output" / f"week {num}" / f"week-{num}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"unit {num}", encoding="utf-8")
    return p


def _ir(root, folder, slug, name, data):
    p = root / folder / slug / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_without_a_declared_order_units_sort_by_number_not_by_path(root):
    for n in (10, 3, 9):                                   # "week 10" sorts before "week 3" as text
        _doc(root, n)
    c = Course.load(root)
    assert [(u.id, u.order) for u in c.units] == [("3", 0), ("9", 1), ("10", 2)]


def test_a_declared_order_is_stored_and_reordering_keeps_ids(root):
    settings.write(root, "structure", {"weeks": {"week 2": {"sources": [{"path": "b.pdf"}]},
                                                 "week 1": {"sources": [{"path": "a.pdf"}]}}})
    assert [u.id for u in Course.load(root).units] == ["2", "1"]          # declared, not numeric
    data = settings.read(root, "structure")                              # what a GUI would do:
    data["weeks"] = dict(reversed(list(data["weeks"].items())))         # rewrite the order…
    settings.write(root, "structure", data)
    units = Course.load(root).units                                      # …and reload
    assert [(u.id, u.order) for u in units] == [("1", 0), ("2", 1)]


def test_a_unit_without_a_number_keeps_its_key_as_its_id(root):
    (root / "intro.md").write_text("orientation", encoding="utf-8")
    settings.write(root, "structure", {"weeks": {"intro": {"doc": "intro.md", "title": "Start here"},
                                                 "week 1": {"sources": [{"path": "a.pdf"}]}}})
    _ir(root, "pages", "intro", "page.json", {"week_ref": "intro"})
    c = Course.load(root)
    intro = c.unit("intro")
    assert (intro.order, intro.label, intro.doc.name) == (0, "Start here", "intro.md")
    assert c.artifacts_for(kind="page", unit="intro")[0].slug == "intro"


def test_an_artifacts_own_reference_wins_over_its_folder(root):
    # Moving a page to another unit is one field (`week_ref`), not a folder rename.
    for n in (3, 5):
        _doc(root, n)
    _ir(root, "pages", "week-3", "page.json", {"week_ref": "week-5"})
    _ir(root, "quizzes", "week-3-essay", "bank.json", {})               # a targeted quiz: owned by its folder
    c = Course.load(root)
    assert c.artifacts_for(kind="page")[0].unit == "5"
    assert c.artifacts_for(kind="quiz")[0].unit == "3"


def test_the_ownership_rule(root):
    ids = {"3", "intro"}
    assert owner("week-5", "week-3", ids) == "5"                         # its own reference first
    assert owner(None, "week-3-essay", ids) == "3"                       # then its folder's unit
    assert owner("intro", "x", ids) == "intro"                           # a non-numeric unit matches itself
    assert owner(None, "module-2-overview", ids) is None                 # course/module scope


def test_overviews_and_concept_maps_are_indexed(root):
    _doc(root, 3)
    (root / ".vtconfig" / "concepts").mkdir()
    (root / ".vtconfig" / "concepts" / "week-3.yaml").write_text("week: '3'\n", encoding="utf-8")
    _ir(root, "overview", "", "week-3-overview.json", {"week_ref": "week-3"})
    _ir(root, "overview", "", "module-2-overview.json", {"page_type": "module_overview"})
    c = Course.load(root)
    assert c.artifacts_for(kind="concept_map", unit="3")
    assert {a.slug: a.unit for a in c.artifacts_for(kind="overview")} == {"week-3-overview": "3",
                                                                          "module-2-overview": None}


def test_strays_unreadable_and_undeclared_units_are_surfaced_not_dropped(root):
    _doc(root, 3)
    stray = _ir(root, "quizzes", "old/week-3", "bank.json", {})          # an unexpected depth
    broken = root / "pages" / "week-3" / "page.json"
    broken.parent.mkdir(parents=True)
    broken.write_text("{not json", encoding="utf-8")
    _ir(root, "quizzes", "week-7-reading", "bank.json", {})              # a unit nobody declared
    with outcomes.capture(sink=lambda n: None) as report:
        c = Course.load(root)
    assert c.strays == [stray] and [w.code for w in report.warnings] == ["course.stray_artifact"]
    assert c.unreadable == [broken] and c.artifacts_for(kind="page")[0].unit == "3"   # still owned, by folder
    assert c.undeclared_units == ["7"]


def test_an_unknown_unit_is_an_error_and_loading_writes_nothing(root):
    _doc(root, 3)
    before = sorted(p for p in root.rglob("*"))
    c = Course.load(root)
    assert sorted(p for p in root.rglob("*")) == before                  # read-only
    with pytest.raises(CoursekitError, match="no unit '4'"):
        c.unit("4")


def test_a_declared_unit_finds_its_doc_in_the_transcribers_folder_layout(root):
    # Declared units default to output/week-N.md; the transcriber writes output/week N/week-N.md.
    settings.write(root, "structure", {"weeks": {"week 3": {"sources": [{"path": "a.pdf"}]}}})
    doc = _doc(root, 3)                                                  # output/week 3/week-3.md
    assert Course.load(root).unit("3").doc == doc.resolve()


def test_a_doc_for_an_undeclared_unit_is_reported_and_reaches_the_census(root):
    from coursekit import census
    settings.write(root, "structure", {"weeks": {"week 1": {"sources": [{"path": "a.pdf"}]}}})
    (root / "output").mkdir()
    (root / "output" / "week-9.md").write_text("unit 9", encoding="utf-8")   # nobody declared unit 9
    c = Course.load(root)
    assert [u.id for u in c.units] == ["1"] and c.undeclared_units == ["9"]
    w9 = next(w for w in census.build_census(root).weeks if w.week == "9")
    assert [m.kind for m in w9.materials] == ["week doc"]                # material, nothing generated: a gap
