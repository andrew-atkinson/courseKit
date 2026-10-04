"""Course census (FLOW-9 Phase 1) — offline, deterministic. Build a fixture course (declared weeks +
some generated artifacts + deliberate gaps) and assert the inventory + the two presence-gap senses."""

import json

from coursekit import census as cen


def _course(tmp_path):
    """4 declared weeks: wk1/wk2 complete (page+quiz), wk3 page-only (modal gap: no quiz),
    wk4 declared-with-material-but-nothing-generated (sense-1 gap). A grading scheme whose
    'Assignments' group gets no items (there are no assignments)."""
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    (root / ".vtconfig" / "context.yaml").write_text(
        'course_title: Creative Coding\n'
        'weeks:\n  "week 1": {title: Intro}\n  "week 2": {title: Loops}\n'
        '  "week 3": {title: Functions}\n  "week 4": {title: Data}\n', encoding="utf-8")
    (root / ".vtconfig" / "structure.coursekit.yaml").write_text(
        'weeks:\n'
        '  "week 1": {sources: [{path: w1.pdf, kind: reading}]}\n'
        '  "week 2": {sources: [{path: w2.pdf, kind: reading}]}\n'
        '  "week 3": {sources: [{path: w3.pdf, kind: reading}]}\n'
        '  "week 4": {sources: [{path: w4.pdf, kind: reading}]}\n'
        'grading:\n  groups: [{name: Assignments, weight: 50}, {name: Quizzes, weight: 50}]\n'
        '  placement: {assignment: Assignments, quiz: Quizzes}\n', encoding="utf-8")

    def page(wk):
        d = root / "pages" / wk
        d.mkdir(parents=True)
        (d / "page.json").write_text(json.dumps({"week_ref": wk}), encoding="utf-8")

    def quiz(wk):
        d = root / "quizzes" / wk
        d.mkdir(parents=True)
        (d / "bank.json").write_text("{}", encoding="utf-8")   # census keys quizzes off the dir name

    page("week-1"); quiz("week-1")
    page("week-2"); quiz("week-2")
    page("week-3")                                             # no quiz → modal gap
    # week-4: declared material, nothing generated
    return root


def test_inventory_counts(tmp_path):
    c = cen.build_census(_course(tmp_path))
    assert c.course_title == "Creative Coding"
    t = c.totals
    assert t == {"weeks": 4, "pages": 3, "quizzes": 2, "assignments": 0}
    wk1 = next(w for w in c.weeks if w.week == "1")
    assert wk1.pages == 1 and wk1.quizzes == 1 and len(wk1.materials) == 1


def test_sense1_declared_but_nothing_generated(tmp_path):
    c = cen.build_census(_course(tmp_path))
    wk4 = next(w for w in c.weeks if w.week == "4")
    assert any("nothing generated" in g for g in wk4.gaps)
    # and a week that produced nothing is NOT also spammed with per-type modal gaps
    assert not any("no quiz" in g for g in wk4.gaps)


def test_sense3_modal_outlier(tmp_path):
    c = cen.build_census(_course(tmp_path))
    wk3 = next(w for w in c.weeks if w.week == "3")
    assert any("no quiz" in g for g in wk3.gaps)       # 2/3 real-generating weeks have a quiz; wk3 doesn't
    assert not any("no page" in g for g in wk3.gaps)   # pages are universal → no page gap


def test_grading_group_with_no_items_is_flagged(tmp_path):
    c = cen.build_census(_course(tmp_path))
    assert c.grading_groups == ["Assignments", "Quizzes"]
    assert any("Assignments" in g for g in c.gaps)     # declared but no assignment items exist
    assert not any("Quizzes" in g for g in c.gaps)     # Quizzes has items


def test_coverage_line_surfaces_a_sparse_type_even_when_no_gaps(tmp_path):
    # 3 weeks with a page+quiz, none with an assignment: no gap (assignments aren't the norm), but
    # the coverage line must still show assignments 0/3 so "no gaps" isn't mistaken for "complete".
    root = tmp_path / "c"
    (root / ".vtconfig").mkdir(parents=True)
    for wk in ("week-1", "week-2", "week-3"):
        for kind, fn, body in (("pages", "page.json", json.dumps({"week_ref": wk})),
                               ("quizzes", "bank.json", "{}")):
            d = root / kind / wk; d.mkdir(parents=True)
            (d / fn).write_text(body, encoding="utf-8")
    c = cen.build_census(root)
    assert c.coverage == {"weeks": 3, "pages": 3, "quizzes": 3, "assignments": 0, "concept maps": 0}
    md = cen.render_report(c)
    assert "pages 3/3" in md and "assignments 0/3" in md
    assert "No gaps found." in md                          # still no gaps — coverage is the honest signal


def test_report_renders_grid_and_gaps(tmp_path):
    c = cen.build_census(_course(tmp_path))
    md = cen.render_report(c)
    assert "# Course census — Creative Coding" in md
    assert "| Week | Materials | Pages | Quizzes | Assignments | Concept map |" in md
    assert "Week 3: Functions" in md and "## Gaps" in md
    assert "no quiz" in md and "nothing generated" in md


def test_write_census_emits_ir_and_report(tmp_path):
    root = _course(tmp_path)
    c, jp, mp = cen.write_census(root)
    assert jp.name == "census.json" and mp.name == "census.md"
    reloaded = cen.Census.model_validate_json(jp.read_text())   # the IR round-trips
    assert reloaded.totals == c.totals


def test_no_declared_structure_degrades_to_artifacts(tmp_path):
    # A course with artifacts but no .vtconfig overlay: weeks are still discovered from the outputs.
    root = tmp_path / "bare"
    (root / "quizzes" / "week-2").mkdir(parents=True)
    (root / "quizzes" / "week-2" / "bank.json").write_text("{}", encoding="utf-8")
    c = cen.build_census(root)
    assert [w.week for w in c.weeks] == ["2"] and c.weeks[0].quizzes == 1


# ============================================================ hardening (edge cases + robustness)

def test_targeted_and_whole_week_quizzes_both_count_under_the_week(tmp_path):
    root = tmp_path / "c"
    (root / ".vtconfig").mkdir(parents=True)
    for slug in ("week-3", "week-3-barrett"):               # whole-week + a targeted quiz
        d = root / "quizzes" / slug; d.mkdir(parents=True)
        (d / "bank.json").write_text("{}", encoding="utf-8")
    wk3 = next(w for w in cen.build_census(root).weeks if w.week == "3")
    assert wk3.quizzes == 2


def test_sibling_pages_count_under_the_same_week(tmp_path):
    root = tmp_path / "c"
    (root / ".vtconfig").mkdir(parents=True)
    for slug in ("week-3", "week-3-glossary", "week-3-recap"):
        d = root / "pages" / slug; d.mkdir(parents=True)
        (d / "page.json").write_text(json.dumps({"week_ref": "week-3"}), encoding="utf-8")
    assert next(w for w in cen.build_census(root).weeks if w.week == "3").pages == 3


def test_malformed_artifact_json_is_skipped_not_fatal(tmp_path):
    root = tmp_path / "c"
    (root / ".vtconfig").mkdir(parents=True)
    d = root / "pages" / "week-3"; d.mkdir(parents=True)
    (d / "page.json").write_text("{ not valid json", encoding="utf-8")   # garbage → _load_json → {}
    c = cen.build_census(root)                                            # must not raise
    assert next(w for w in c.weeks if w.week == "3").pages == 1           # keyed off the dir name


def test_empty_course_yields_empty_census(tmp_path):
    root = tmp_path / "c"; (root / ".vtconfig").mkdir(parents=True)
    c = cen.build_census(root)
    assert c.weeks == [] and c.totals["weeks"] == 0
    assert "No gaps found." in cen.render_report(c)


def test_week_doc_folder_per_week_layout_with_space(tmp_path):
    # the transcriber layout: output/<folder with a space>/week-N.md
    root = tmp_path / "c"; (root / ".vtconfig").mkdir(parents=True)
    d = root / "output" / "week 3"; d.mkdir(parents=True)
    (d / "week-3.md").write_text("material", encoding="utf-8")
    wk3 = next(w for w in cen.build_census(root).weeks if w.week == "3")
    assert any(m.kind == "week doc" for m in wk3.materials)


def test_week_doc_counted_once_across_locations(tmp_path):
    root = tmp_path / "c"; (root / ".vtconfig").mkdir(parents=True)
    (root / "output").mkdir()
    (root / "output" / "week-3.md").write_text("x", encoding="utf-8")     # flat
    d = root / "output" / "week 3"; d.mkdir()
    (d / "week-3.md").write_text("x", encoding="utf-8")                   # + a folder-per-week copy
    wk3 = next(w for w in cen.build_census(root).weeks if w.week == "3")
    assert sum(1 for m in wk3.materials if m.kind == "week doc") == 1     # deduped


def test_modal_exactly_half_is_not_a_majority(tmp_path):
    # 4 generating weeks, quiz in exactly 2 → not a strict majority → no "no quiz" gap
    root = tmp_path / "c"; (root / ".vtconfig").mkdir(parents=True)
    for wk in ("week-1", "week-2", "week-3", "week-4"):
        d = root / "pages" / wk; d.mkdir(parents=True)
        (d / "page.json").write_text(json.dumps({"week_ref": wk}), encoding="utf-8")
    for wk in ("week-1", "week-2"):
        d = root / "quizzes" / wk; d.mkdir(parents=True); (d / "bank.json").write_text("{}", encoding="utf-8")
    c = cen.build_census(root)
    assert not any("no quiz" in g for w in c.weeks for g in w.gaps)


def test_single_generating_week_has_no_modal_noise(tmp_path):
    root = tmp_path / "c"; (root / ".vtconfig").mkdir(parents=True)
    d = root / "pages" / "week-1"; d.mkdir(parents=True)
    (d / "page.json").write_text(json.dumps({"week_ref": "week-1"}), encoding="utf-8")
    assert cen.build_census(root).weeks[0].gaps == []


def test_grading_slug_override_marks_group_used(tmp_path):
    # a quiz placed in Projects via a SLUG override must count Projects as used (not flagged) — the
    # bug the per-item resolution fixes (kind-default alone would have missed it).
    root = tmp_path / "c"; (root / ".vtconfig").mkdir(parents=True)
    (root / ".vtconfig" / "structure.coursekit.yaml").write_text(
        'grading:\n  groups: [{name: Projects, weight: 100}]\n  placement: {week-3-barrett: Projects}\n',
        encoding="utf-8")
    d = root / "quizzes" / "week-3-barrett"; d.mkdir(parents=True)
    (d / "bank.json").write_text("{}", encoding="utf-8")
    c = cen.build_census(root)
    assert c.grading_groups == ["Projects"] and not any("Projects" in g for g in c.gaps)


def test_declared_but_empty_week_is_excluded_from_the_grid(tmp_path):
    # a week with only a title in context.yaml (no sources, no doc, no artifacts) is not "real"
    root = tmp_path / "c"; (root / ".vtconfig").mkdir(parents=True)
    (root / ".vtconfig" / "context.yaml").write_text(
        'course_title: C\nweeks:\n  "week 1": {title: Intro}\n', encoding="utf-8")
    c = cen.build_census(root)
    assert all(w.week != "1" for w in c.weeks if w.is_real())
    assert "Week 1" not in cen.render_report(c)


def test_title_falls_back_to_folder_name(tmp_path):
    root = tmp_path / "Photo 101"; (root / ".vtconfig").mkdir(parents=True)   # no course_title declared
    d = root / "pages" / "week-1"; d.mkdir(parents=True)
    (d / "page.json").write_text(json.dumps({"week_ref": "week-1"}), encoding="utf-8")
    assert cen.build_census(root).course_title == "Photo 101"


def test_build_is_deterministic(tmp_path):
    root = _course(tmp_path)
    a = cen.build_census(root).model_dump_json(indent=2)
    b = cen.build_census(root).model_dump_json(indent=2)
    assert a == b                                            # byte-identical across runs
