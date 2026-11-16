"""CORE-6.1 — who set each overlay section. A proposer's draft is `proposed`; only `accept` or `config
set`/`unset` make a section `declared`, recording who and when; an edit made any other way is `edited`
until accepted; a section with no history is `unknown` (agent/core-6-design.md)."""

import json

import pytest
import yaml

from coursekit import cli, settings
from coursekit.ingest import propose as proposer
from coursekit.ingest import propose_expectations as pe
from coursekit.ingest import propose_grading as pg
from coursekit.outcomes import CoursekitError

GRADING = {"groups": [{"name": "Assignments", "weight": 50}, {"name": "Quizzes", "weight": 50}],
           "placement": {"assignment": "Assignments", "quiz": "Quizzes"}}


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.getpass, "getuser", lambda: "login-name")
    r = tmp_path / "course"
    (r / ".vtconfig").mkdir(parents=True)
    return r


def _overlay(root):
    return root / ".vtconfig" / "structure.coursekit.yaml"


def _history(root):
    return json.loads((root / ".vtconfig" / settings.AUTHORITY).read_text(encoding="utf-8"))


def _edit(root, fn):
    data = yaml.safe_load(_overlay(root).read_text(encoding="utf-8"))
    fn(data)
    _overlay(root).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")   # an editor, not the API


def test_every_proposer_records_a_proposal(root):
    pg.write_grading(root, GRADING)
    pe.write_expectations(root, {"defaults": [{"scope": "unit", "artifact": "quiz", "count": 1}]}, [])
    proposer.write_overlay(proposer.Proposal(weeks={"week 1": {"sources": [{"path": "a.pdf"}]}}, root=root))
    for section in ("grading", "expect", "units"):
        status, last = settings.authority(root, section)
        assert status == "proposed" and (last["step"], last["by"]) == ("proposed", "coursekit")
        assert last["at"] and last["coursekit"] and last["section"]


def test_an_edit_reads_edited_and_reformatting_does_not(root):
    pg.write_grading(root, GRADING)
    data = yaml.safe_load(_overlay(root).read_text(encoding="utf-8"))
    _overlay(root).write_text(yaml.safe_dump({"grading": {"placement": data["grading"]["placement"],
                                                          "groups": data["grading"]["groups"]}},
                                             sort_keys=True, indent=4), encoding="utf-8")   # same values, new layout
    assert settings.authority(root, "grading")[0] == "proposed"
    _edit(root, lambda d: d["grading"]["groups"][1].update(weight="30%"))
    assert settings.authority(root, "grading")[0] == "edited"


def test_accept_records_who_and_shows_what_changed(root):
    pg.write_grading(root, GRADING)
    _edit(root, lambda d: d["grading"]["groups"][1].update(weight=30))
    [r] = settings.accept(root, ["grading"], by="co-teacher")
    assert (r["was"], r["accepted"]) == ("edited", True)
    assert r["changes"] == ["grading.groups.Quizzes.weight: 50.0 → 30.0"]
    status, last = settings.authority(root, "grading")
    assert (status, last["step"], last["by"]) == ("declared", "accepted", "co-teacher")
    assert [e["step"] for e in _history(root)["grading"]] == ["proposed", "accepted"]   # a history, not a slot
    [again] = settings.accept(root, ["grading"])
    assert not again["accepted"] and len(_history(root)["grading"]) == 2             # declared + unchanged: nothing


def test_accept_with_no_section_takes_every_section_and_defaults_to_the_login_name(root):
    settings.write(root, "structure", {"grading": GRADING, "units": {"intro": {"doc": "intro.md"}}})
    assert [settings.authority(root, s)[0] for s in ("grading", "units", "expect")] == ["unknown", "unknown", None]
    results = settings.accept(root)
    assert [(r["section"], r["was"]) for r in results] == [("units", "unknown"), ("grading", "unknown")]
    assert {settings.authority(root, s)[1]["by"] for s in ("grading", "units")} == {"login-name"}


def test_accept_refuses_an_invalid_overlay_and_writes_nothing(root):
    pg.write_grading(root, GRADING)
    before = (root / ".vtconfig" / settings.AUTHORITY).read_bytes()
    _edit(root, lambda d: d["grading"]["placement"].update(quiz="Nowhere"))
    with pytest.raises(CoursekitError):
        settings.accept(root, ["grading"])
    assert (root / ".vtconfig" / settings.AUTHORITY).read_bytes() == before


@pytest.mark.parametrize("section, code", [("rubric", "authority.unknown_section"), ("expect", "authority.no_section")])
def test_accept_names_a_section_it_cannot_accept(root, section, code):
    pg.write_grading(root, GRADING)
    with pytest.raises(CoursekitError) as e:
        settings.accept(root, [section])
    assert e.value.code == code


def test_config_set_and_unset_make_their_section_declared(root):
    pg.write_grading(root, GRADING)
    settings.set(root, "grading.groups.Quizzes.weight", 40)
    assert settings.authority(root, "grading")[0] == "declared"
    assert settings.authority(root, "grading")[1]["by"] == "login-name"
    _edit(root, lambda d: d["grading"]["groups"][0].update(weight=60))
    settings.unset(root, "grading.placement.quiz", by="co-teacher")
    status, last = settings.authority(root, "grading")
    assert (status, last["by"]) == ("declared", "co-teacher")
    settings.set(root, "unit_noun", "session")                          # not a section: no history
    assert set(_history(root)) == {"grading"}


def test_a_key_coursekit_does_not_know_changes_nothing(root):
    pg.write_grading(root, GRADING)
    history = _history(root)
    history["grading"][-1]["account"] = "acct-123"                      # e.g. a later account beside `by`
    (root / ".vtconfig" / settings.AUTHORITY).write_text(json.dumps(history), encoding="utf-8")
    assert settings.authority(root, "grading")[0] == "proposed"


def test_an_overlay_under_the_old_name_weeks_is_the_units_section(root):
    settings.write(root, "structure", {"weeks": {"week 3": {"doc": "w3.md"}}})
    settings.accept(root, ["weeks"])
    assert settings.authority(root, "units") == ("declared", _history(root)["units"][-1])


def test_an_unreadable_history_is_an_error_naming_the_file(root):
    pg.write_grading(root, GRADING)
    (root / ".vtconfig" / settings.AUTHORITY).write_text("{not json", encoding="utf-8")
    with pytest.raises(CoursekitError) as e:
        settings.authority(root, "grading")
    assert e.value.code == "authority.unreadable" and settings.AUTHORITY in e.value.message


def test_the_accept_hint_can_be_pasted_for_a_path_with_spaces(tmp_path, capsys):
    root = tmp_path / "My Course"
    (root / ".vtconfig").mkdir(parents=True)
    pg.write_grading(root, GRADING)
    assert cli.main(["check", str(root)]) == 0
    assert f"`coursekit accept '{root}' grading`" in capsys.readouterr().out


def test_check_says_who_set_each_section_and_accept_prints_the_change(root, capsys):
    pg.write_grading(root, GRADING)
    settings.write(root, "structure", {**settings.read(root, "structure"),
                                       "expect": {"defaults": [{"scope": "unit", "artifact": "quiz"}]}})
    assert cli.main(["check", str(root)]) == 0
    out = capsys.readouterr().out
    assert "grading  proposed by coursekit on " in out and f"`coursekit accept {root} grading`" in out
    assert "expect   unknown — no record of who set it" in out
    _edit(root, lambda d: d["grading"]["groups"][1].update(weight=30))
    assert cli.main(["accept", str(root), "grading", "--by", "co-teacher"]) == 0
    assert "grading.groups.Quizzes.weight: 50.0 → 30.0" in capsys.readouterr().out
    assert cli.main(["check", str(root)]) == 0
    assert "grading  declared — accepted by co-teacher on " in capsys.readouterr().out
