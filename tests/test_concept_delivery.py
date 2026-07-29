"""The concept-delivery rubric — offline, with a fake critic (no model)."""

from coursekit.generate.page import concept_delivery as cd
from coursekit.generate.page.concept_fixtures import (
    VARIANTS,
    good_page,
    no_examples_page,
    thin_page,
)

_REPLY = (
    "Reasoning about the concepts…\n\n"
    "CONCEPTS:\n"
    "- the for loop repeats a block: 3 | explained with a worked example\n"
    "- the condition controls the count: 2 | explained but no example\n"
    "- the counter changes each pass: 1 | only named, not explained\n")


class _FakeConceptCritic:
    def __init__(self, reply=_REPLY):
        self.reply = reply

    def chat(self, *, model, messages, temperature=None, max_tokens=None, seed=None):
        return self.reply


def test_parse_concepts_reads_each_line():
    parsed = cd._parse_concepts(_REPLY)
    assert len(parsed) == 3
    assert parsed[0] == ("the for loop repeats a block", 3, "explained with a worked example")
    assert parsed[2][1] == 1                     # score
    # the "CONCEPTS:" header line is not mistaken for a concept
    assert all(name.upper() != "CONCEPTS" for name, _, _ in parsed)


def test_evaluate_returns_scored_concepts_and_average():
    pc = cd.evaluate_page_concepts(good_page(), "loops material", _FakeConceptCritic(), "m")
    assert [c.score for c in pc.concepts] == [3, 2, 1]
    assert pc.average == 2.0                      # (3+2+1)/3


def test_evaluate_survives_a_dead_critic():
    class _Boom:
        def chat(self, **kw):
            raise RuntimeError("model offline")
    pc = cd.evaluate_page_concepts(good_page(), "m", _Boom(), "x")
    assert pc.concepts == [] and pc.average == 0.0     # reported empty, not a crash


def test_fixtures_differ_in_the_intended_way():
    good = good_page()
    # the good page carries the example blocks; no_examples drops exactly them
    assert {"code1", "ex1"} <= set(good.blocks)
    assert {"code1", "ex1"} & set(no_examples_page().blocks) == set()
    # thin page names concepts but has no explanatory prose/code
    assert not any(b.kind in ("code", "card") for b in thin_page().blocks.values())
    assert set(VARIANTS) == {"thin", "no_examples", "jargon"}


def test_render_concepts_is_readable():
    out = cd.render_concepts(cd.evaluate_page_concepts(good_page(), "m", _FakeConceptCritic(), "x"))
    assert "Concept delivery" in out and "avg 2.0/3" in out and "**the for loop repeats a block** 3/3" in out


def test_evaluate_course_concepts_writes_a_report(tmp_path):
    course = tmp_path / "course"
    (course / "output").mkdir(parents=True)
    (course / "output" / "week-3.md").write_text("loops material", encoding="utf-8")
    pd = course / "pages" / "week-3"
    pd.mkdir(parents=True)
    (pd / "page.json").write_text(good_page().model_dump_json(), encoding="utf-8")

    results, out = cd.evaluate_course_concepts(course, provider=_FakeConceptCritic(), model="m")
    assert len(results) == 1 and out is not None and out.exists()
    assert results[0].page_id == "week-3"          # labelled by week
    assert "Concept delivery" in out.read_text()
