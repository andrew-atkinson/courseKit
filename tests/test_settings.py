"""CORE-1.4 — the settings API. Every write is validated against the file's schema before it's saved,
so an interface (the CLI now, a GUI later) can't leave a `.vtconfig` file that fails `coursekit check`."""

import pytest

from coursekit import cli, schemas, settings
from coursekit.ingest import propose_expectations as pe
from coursekit.ingest import propose_grading as pg
from coursekit.outcomes import CoursekitError


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "course"
    (r / ".vtconfig").mkdir(parents=True)
    return r


def _file(root, name):
    return root / ".vtconfig" / name


def test_set_creates_the_file_and_get_reads_it_back(root):
    settings.set(root, "quiz.eu_question", True)
    settings.set(root, "style.theme", "terminal")
    assert settings.get(root, "quiz.eu_question") is True
    assert _file(root, "quiz.yaml").read_text() == "eu_question: true\n"
    assert settings.read(root, "style") == {"theme": "terminal"}


def test_named_list_items_are_addressed_by_name(root):
    settings.set(root, "grading.groups.Projects.weight", "20%")        # a percent reads as the number
    settings.set(root, "grading.groups.Quizzes.weight", 80)
    settings.set(root, "grading.placement.quiz", "Quizzes")
    assert settings.get(root, "grading.groups.Projects.weight") == 20.0
    settings.unset(root, "grading.groups.Projects")
    assert [g["name"] for g in settings.get(root, "grading.groups")] == ["Quizzes"]


@pytest.mark.parametrize("key, value, problem", [
    ("grading.groups.Projects.weight", "twenty", "weight"),
    ("grading.placement.quiz", "Quizes", "isn't declared"),
    ("expect.defaults", [{"scope": "weekly", "artifact": "page"}], "scope"),
    ("expect.defaults", [{"scope": "week", "artifact": "quiz", "count": "two"}], "count"),
    ("quiz.eu_questoin", True, "did you mean 'eu_question'"),
    ("style.theme", "bauhuas", "did you mean 'bauhaus'"),
    ("quiz.max_pass_chars", 40, "belongs in page.yaml"),
])
def test_an_invalid_value_is_refused_and_the_file_left_byte_identical(root, key, value, problem):
    settings.set(root, "grading.groups.Quizzes.weight", 100)            # something already on disk
    settings.set(root, "quiz.questions", 5)
    settings.set(root, "style.theme", "terminal")
    before = {n: _file(root, n).read_bytes() for n in ("structure.coursekit.yaml", "quiz.yaml", "style.yaml")}
    with pytest.raises(CoursekitError) as e:
        settings.set(root, key, value)
    assert any(problem in p for p in e.value.details["problems"])
    assert {n: _file(root, n).read_bytes() for n in before} == before
    assert not list((root / ".vtconfig").glob(".*.tmp"))                 # no half-written leftovers


def test_supplements_are_a_document_too(root):
    settings.set(root, "pages.week-3.references", [{"label": "p5 reference", "url": "https://p5js.org"}])
    assert settings.read(root, "pages/week-3")["references"][0]["url"] == "https://p5js.org"
    with pytest.raises(CoursekitError, match="alt"):
        settings.set(root, "pages.week-3.images", [{"url": "a.png"}])


def test_the_transcribers_file_and_unknown_documents_are_refused(root):
    with pytest.raises(CoursekitError, match="belongs to the transcriber"):
        settings.set(root, "context.course_title", "T")
    with pytest.raises(CoursekitError, match="no settings document 'qiuz'"):
        settings.set(root, "qiuz.questions", 5)
    with pytest.raises(CoursekitError, match="no setting"):
        settings.unset(root, "quiz.questions")                           # removing what isn't there


def test_files_hold_only_what_was_set_and_keep_a_header(root):
    settings.write(root, "structure", {"grading": {"groups": [{"name": "All", "weight": 100}]}},
                   header="# drafted by a proposer\n")
    text = _file(root, "structure.coursekit.yaml").read_text()
    assert text.startswith("# drafted by a proposer\n") and "weeks" not in text and "placement" not in text


def test_what_the_proposers_write_passes_check(root):
    (root / "quizzes" / "week-3").mkdir(parents=True)
    (root / "quizzes" / "week-3" / "bank.json").write_text("{}", encoding="utf-8")
    pg.write_grading(root, pg.propose_grading(root))
    expect, notes = pe.propose_expectations(root)
    pe.write_expectations(root, expect, notes)
    _, errors = schemas.check(root)
    assert errors == []
    assert settings.get(root, "grading.placement.quiz") == "Quizzes"


def test_the_config_command(root, capsys):
    assert cli.main(["config", "set", str(root), "quiz.eu_question", "true"]) == 0
    assert cli.main(["config", "set", str(root), "grading.groups.Projects.weight", "20%"]) == 0
    assert cli.main(["config", "get", str(root), "grading.groups.Projects.weight"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "20.0"
    assert cli.main(["config", "set", str(root), "style.theme", "bauhuas"]) == 1      # refused, exit 1
    assert "did you mean 'bauhaus'" in capsys.readouterr().err
    assert cli.main(["config", "show", str(root)]) == 0
    out = capsys.readouterr().out
    assert "# quiz\neu_question: true" in out and "# style" not in out              # nothing set there
    assert cli.main(["config", "unset", str(root), "quiz.eu_question"]) == 0
    assert cli.main(["config", "check", str(root)]) == 0
