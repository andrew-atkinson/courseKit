"""The declared course-structure reader (FLOW-7). Pure and offline: build a CourseConfig with a
context dict and read structure off it; the manifest generalizes the transcriber's `videos:` into a
typed `sources:` list, and its absence degrades to empty (callers then fall back to inference)."""

from pathlib import Path

from coursekit import courseconfig
from coursekit.coursestructure import CourseStructure, Source


def _struct(context: dict, root: Path | None = None) -> CourseStructure:
    cfg = courseconfig.CourseConfig(root=root, config={}, context=context,
                                    config_path=None, context_path=None)
    return CourseStructure(cfg)


def test_empty_context_degrades_to_empty():
    s = _struct({})
    assert s.iter_weeks() == []
    assert not s.has_declared_structure()
    assert s.sources_for("3") == []


def test_iter_weeks_sorts_numerically():
    s = _struct({"weeks": {"week 10": {}, "week 2": {}, "week 1": {}}})
    assert [n for n, _ in s.iter_weeks()] == ["1", "2", "10"]


def test_has_declared_structure_only_fires_on_doc_or_sources():
    # decoration-only (title/module) does NOT trigger manifest-driven discovery
    assert not _struct({"weeks": {"week 3": {"title": "Exposure", "module": "M2"}}}
                       ).has_declared_structure()
    # the transcriber's untyped videos also do NOT trigger it — existing courses keep the glob path
    assert not _struct({"weeks": {"week 3": {"videos": [{"filename": "a.mp4"}]}}}
                       ).has_declared_structure()
    # coursekit's own keys DO
    assert _struct({"weeks": {"week 3": {"doc": "output/week-3.md"}}}).has_declared_structure()
    assert _struct({"weeks": {"week 3": {"sources": [{"path": "r.pdf"}]}}}).has_declared_structure()


def test_week_doc_declared_default_and_rootless(tmp_path):
    # declared doc, resolved against the root
    s = _struct({"weeks": {"week 3": {"doc": "docs/w3.md"}}}, root=tmp_path)
    assert s.week_doc("3") == tmp_path / "docs" / "w3.md"
    # no declared doc but a known root -> the default consolidated path
    s2 = _struct({"weeks": {"week 4": {"title": "x"}}}, root=tmp_path)
    assert s2.week_doc("4") == tmp_path / "output" / "week-4.md"
    # no root -> None (caller must anchor it elsewhere)
    assert _struct({"weeks": {"week 4": {}}}, root=None).week_doc("4") is None


def test_typed_sources_are_parsed_with_kind_inference_and_role(tmp_path):
    s = _struct({"weeks": {"week 3": {"sources": [
        {"path": "readings/barrett.pdf", "title": "Barrett", "kind": "reading"},
        {"path": "slides/exposure.pptx"},                       # kind inferred from suffix
        {"path": "overview.md", "role": "framing"},
    ]}}}, root=tmp_path)
    srcs = s.sources_for("3")
    assert [(x.kind, x.role) for x in srcs] == [
        ("reading", "content"), ("slides", "content"), ("notes", "framing")]
    assert srcs[1].title == "exposure"                          # title defaults to the stem
    assert srcs[0].resolve(tmp_path) == tmp_path / "readings" / "barrett.pdf"


def test_source_without_a_path_is_dropped():
    s = _struct({"weeks": {"week 3": {"sources": [{"title": "no path"}, {"path": "ok.pdf"}]}}})
    assert [x.path for x in s.sources_for("3")] == ["ok.pdf"]


def test_videos_normalize_to_video_sources_joined_to_the_folder():
    # the transcriber's per-week `videos:` (filenames relative to `folder`) become kind=video sources
    s = _struct({"weeks": {"week 3": {"folder": "week 3 - loops",
                                      "videos": [{"filename": "2 for loops.mp4", "title": "For loops"}]}}})
    srcs = s.sources_for("3")
    assert len(srcs) == 1
    assert srcs[0].kind == "video" and srcs[0].title == "For loops"
    assert srcs[0].path == str(Path("week 3 - loops") / "2 for loops.mp4")


def test_declared_sources_win_over_videos():
    s = _struct({"weeks": {"week 3": {"videos": [{"filename": "a.mp4"}],
                                      "sources": [{"path": "r.pdf", "kind": "reading"}]}}})
    assert [x.kind for x in s.sources_for("3")] == ["reading"]


def test_load_reads_a_real_vtconfig(tmp_path):
    import textwrap
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    (root / ".vtconfig" / "context.yaml").write_text(textwrap.dedent("""
        course_title: Digital Photography
        weeks:
          "week 3":
            title: Exposure
            sources:
              - {path: readings/barrett.pdf, kind: reading}
    """), encoding="utf-8")
    s = CourseStructure.load(root)
    assert s.course_title == "Digital Photography"
    assert s.has_declared_structure()
    assert s.week_label("3") == "Week 3: Exposure"
    assert [x.kind for x in s.sources_for("3")] == ["reading"]


# --------------------------------------------------- overlay composition (FLOW-7 Phase 2)

def _course_with_files(tmp_path, context_yaml=None, overlay_yaml=None):
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    if context_yaml is not None:
        (root / ".vtconfig" / "context.yaml").write_text(context_yaml, encoding="utf-8")
    if overlay_yaml is not None:
        (root / ".vtconfig" / "structure.coursekit.yaml").write_text(overlay_yaml, encoding="utf-8")
    return root


def test_overlay_composes_with_context_yaml(tmp_path):
    import textwrap
    # context.yaml carries identity (title/module); the overlay adds typed sources
    root = _course_with_files(
        tmp_path,
        context_yaml=textwrap.dedent("""
            weeks:
              "week 3": {title: Exposure, module: Unit 2}
        """),
        overlay_yaml=textwrap.dedent("""
            weeks:
              "week 3":
                sources:
                  - {path: readings/barrett.pdf, kind: reading}
        """))
    s = CourseStructure.load(root)
    assert s.has_declared_structure()                     # the overlay's sources trigger it
    assert s.week_label("3") == "Week 3: Exposure"        # identity from context.yaml
    assert s.week_module("3") == "Unit 2"
    assert [x.kind for x in s.sources_for("3")] == ["reading"]   # sources from the overlay


def test_overlay_never_overrides_context_identity(tmp_path):
    import textwrap
    root = _course_with_files(
        tmp_path,
        context_yaml='weeks: {"week 3": {title: Canonical}}\n',
        overlay_yaml=textwrap.dedent("""
            weeks:
              "week 3": {title: SHOULD-NOT-WIN, sources: [{path: r.pdf}]}
        """))
    # context.yaml owns identity — the overlay's title is ignored, its sources are kept
    s = CourseStructure.load(root)
    assert s.week_label("3") == "Week 3: Canonical"
    assert [x.path for x in s.sources_for("3")] == ["r.pdf"]


def test_overlay_only_week_appears(tmp_path):
    # a week declared ONLY in the overlay (context.yaml doesn't mention it) still shows up
    root = _course_with_files(tmp_path, context_yaml="course_title: C\n",
                              overlay_yaml='weeks: {"week 4": {sources: [{path: x.pdf, kind: reading}]}}\n')
    s = CourseStructure.load(root)
    assert [n for n, _ in s.iter_weeks()] == ["4"]
    assert s.has_declared_structure()
