"""CORE-1.3 — the settings files a faculty member edits are read through schemas. Absent means
defaults; present-but-broken or invalid is an error naming the file, the key, the value, and what's
allowed — each case below was a silent failure the CORE-1 audit found."""

import textwrap

import pytest

from coursekit import cli, courseconfig, schemas
from coursekit.coursestructure import CourseStructure
from coursekit.outcomes import CoursekitError


def _course(tmp_path, files: dict) -> object:
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    for name, text in files.items():
        p = root / ".vtconfig" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(text), encoding="utf-8")
    return root


def _problems(path, model):
    with pytest.raises(CoursekitError) as e:
        schemas.load(path, model)
    return e.value.details["problems"]


# ------------------------------------------------------------------ grading (the worst finding)
def test_a_percent_weight_reads_as_that_number_not_zero(tmp_path):
    root = _course(tmp_path, {"structure.coursekit.yaml": """
        grading:
          groups: [{name: Projects, weight: 20%}, {name: Quizzes, weight: 80}]
          placement: {quiz: Quizzes}
    """})
    assert CourseStructure.load(root).grading().groups == (("Projects", 20.0), ("Quizzes", 80.0))


def test_bad_grading_values_are_errors_not_dropped(tmp_path):
    root = _course(tmp_path, {"structure.coursekit.yaml": """
        grading:
          groups: [{name: Projects, weight: twenty}, {weight: 30}]
    """})
    found = _problems(root / ".vtconfig/structure.coursekit.yaml", schemas.StructureOverlay)
    assert any(p.startswith("grading.groups[0].weight") and "'twenty'" in p for p in found)
    assert any(p.startswith("grading.groups[1].name") for p in found)          # a nameless group
    with pytest.raises(CoursekitError):
        CourseStructure.load(root).grading()                                    # the real read path


def test_a_placement_must_name_a_declared_group(tmp_path):
    root = _course(tmp_path, {"structure.coursekit.yaml": """
        grading:
          groups: [{name: Quizzes, weight: 100}]
          placement: {quiz: Quizes}
    """})
    found = _problems(root / ".vtconfig/structure.coursekit.yaml", schemas.StructureOverlay)
    assert any("Quizes" in p and "groups: Quizzes" in p for p in found)


def test_bad_expectation_rules_are_errors_not_dropped(tmp_path):
    root = _course(tmp_path, {"structure.coursekit.yaml": """
        expect:
          defaults: [{scope: weekly, artifact: page}, {scope: week, artifact: quiz, count: two}]
          overrides: {week: {5: {page:glossary: 1}}}
    """})
    found = _problems(root / ".vtconfig/structure.coursekit.yaml", schemas.StructureOverlay)
    assert any("defaults[0].scope" in p and "'weekly'" in p and "'week', 'module' or 'course'" in p for p in found)
    assert any("defaults[1].count" in p and "'two'" in p for p in found)


# ------------------------------------------------------------------ settings files
def test_an_unknown_theme_suggests_the_nearest(tmp_path):
    root = _course(tmp_path, {"style.yaml": "theme: bauhuas\n"})
    (found,) = _problems(root / ".vtconfig/style.yaml", schemas.StyleSettings)
    assert "did you mean 'bauhaus'" in found and "available:" in found


def test_a_mistyped_key_is_an_error_with_a_suggestion(tmp_path):
    root = _course(tmp_path, {"quiz.yaml": "eu_questoin: true\n"})
    with pytest.raises(CoursekitError, match="did you mean 'eu_question'"):
        courseconfig.load(root, config_name="quiz.yaml")


def test_a_key_in_the_wrong_file_says_where_it_belongs(tmp_path):
    root = _course(tmp_path, {"quiz.yaml": "max_pass_chars: 40\n"})
    with pytest.raises(CoursekitError, match="max_pass_chars: belongs in page.yaml"):
        courseconfig.load(root, config_name="quiz.yaml")


def test_bad_yaml_names_the_file_and_line(tmp_path):
    root = _course(tmp_path, {"pages/week-3.yaml": "references:\n  - label: x\n    url: y\ncd"})
    with pytest.raises(CoursekitError) as e:
        schemas.load(root / ".vtconfig/pages/week-3.yaml", schemas.Supplements)
    assert e.value.code == "config.unreadable" and e.value.details["line"] == 4


def test_absent_files_still_mean_defaults(tmp_path):
    root = _course(tmp_path, {})
    assert courseconfig.load(root, config_name="quiz.yaml").config == {}
    assert schemas.load(root / ".vtconfig/style.yaml", schemas.StyleSettings) == {}


def test_supplements_that_used_to_vanish_are_errors(tmp_path):
    root = _course(tmp_path, {"pages/week-3.yaml": """
        examples:
          - label: no target
          - iframe: '<iframe width="3"></iframe>'
        images:
          - url: a.png
    """})
    found = _problems(root / ".vtconfig/pages/week-3.yaml", schemas.Supplements)
    assert any(p.startswith("examples[0]") and "url" in p for p in found)
    assert any(p.startswith("examples[1]") and "src" in p for p in found)
    assert any(p.startswith("images[0]") and "alt" in p for p in found)


# ------------------------------------------------------------------ check: every file at once
def test_check_reports_every_bad_file_and_passes_the_good_ones(tmp_path):
    root = _course(tmp_path, {
        "quiz.yaml": "eu_question: true\n",
        "style.yaml": "theme: bauhuas\n",
        "pages/week-3.yaml": "references: [{url: x}]\ncd",
        "context.yaml": "course_title: T\nanything_the_transcriber_writes: ok\n",   # parse-only
    })
    checked, errors = schemas.check(root)
    assert {p.name for p in checked} == {"quiz.yaml", "style.yaml", "week-3.yaml", "context.yaml"}
    assert sorted(e.details["path"].rsplit("/", 1)[-1] for e in errors) == ["style.yaml", "week-3.yaml"]


def test_check_validates_concept_maps(tmp_path):
    root = _course(tmp_path, {"concepts/week-3.yaml": "week: '3'\nconcepts: [{name: Loops, colour: red}]\n"})
    _, errors = schemas.check(root)
    assert len(errors) == 1 and "concepts[0].colour" in errors[0].message


def test_the_check_command_exits_1_on_problems_and_0_when_clean(tmp_path, capsys):
    root = _course(tmp_path, {"quiz.yaml": "questions: 0\n"})
    assert cli.main(["check", str(root)]) == 1
    out = capsys.readouterr().out
    assert "✗ quiz.yaml has 1 problem(s)" in out and "questions" in out
    (root / ".vtconfig" / "quiz.yaml").write_text("questions: 5\n", encoding="utf-8")
    assert cli.main(["check", str(root)]) == 0
    assert "All 1 file(s) are valid." in capsys.readouterr().out
