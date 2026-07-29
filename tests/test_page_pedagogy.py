"""The page pedagogy rubric — offline, with a fake critic (no model)."""

from coursekit.generate.page import pedagogy as ped
from coursekit.generate.page.pedagogy_fixtures import (
    DIMENSION_BLOCKS,
    deficient_page,
    good_page,
)

_GOOD_REPLY = (
    "Reasoning about the page…\n\n"
    "SCANNABILITY: 3 | labelled sections and a clear hierarchy\n"
    "SIGNALING: 2 | a pull-quote foregrounds the key idea\n"
    "ENGAGEMENT: 1 | opens cold with a definition\n"
    "WORKED_EXAMPLES: 3 | a worked example and a side-by-side contrast\n"
    "RETRIEVAL: 0 | no recall prompt and no recap\n")


class _FakeRubric:
    def __init__(self, reply=_GOOD_REPLY):
        self.reply = reply

    def chat(self, *, model, messages, temperature=None, max_tokens=None, seed=None):
        return self.reply


def test_parse_rubric_reads_scores_and_notes():
    parsed = ped._parse_rubric(_GOOD_REPLY)
    assert parsed["SCANNABILITY"] == (3, "labelled sections and a clear hierarchy")
    assert parsed["RETRIEVAL"][0] == 0
    assert set(parsed) == set(ped.CRITERIA)


def test_evaluate_returns_all_five_criteria():
    rub = ped.evaluate_page_pedagogy(good_page(), "loops material", _FakeRubric(), "m")
    assert set(rub.scores) == set(ped.CRITERIA)
    assert rub.scores["SCANNABILITY"].score == 3 and rub.scores["RETRIEVAL"].score == 0
    assert rub.total == 3 + 2 + 1 + 3 + 0


def test_a_missing_or_unreadable_criterion_becomes_minus_one():
    partial = "SCANNABILITY: 2 | ok\nSIGNALING: 1 | flat\n"     # three criteria omitted
    rub = ped.evaluate_page_pedagogy(good_page(), "m", _FakeRubric(partial), "x")
    assert rub.scores["SCANNABILITY"].score == 2
    assert rub.scores["ENGAGEMENT"].score == -1                # absent -> not scored, not a crash


def test_evaluate_survives_a_dead_critic():
    class _Boom:
        def chat(self, **kw):
            raise RuntimeError("model offline")
    rub = ped.evaluate_page_pedagogy(good_page(), "m", _Boom(), "x")
    assert all(s.score == -1 for s in rub.scores.values())


def test_good_page_carries_every_dimension_and_variants_drop_theirs():
    g = good_page()
    for crit, block_ids in DIMENSION_BLOCKS.items():
        assert set(block_ids) <= set(g.blocks)                 # the good page has these blocks
        variant = deficient_page(crit)
        assert set(block_ids) & set(variant.blocks) == set()   # the variant has none of them
        # and it removed ONLY those
        assert set(g.blocks) - set(variant.blocks) == set(block_ids)


def test_render_rubric_is_readable():
    out = ped.render_rubric(ped.evaluate_page_pedagogy(good_page(), "m", _FakeRubric(), "x"))
    assert "Page pedagogy" in out and "**SCANNABILITY** 3/3" in out and "**RETRIEVAL** 0/3" in out


def test_evaluate_course_pedagogy_writes_a_report(tmp_path):
    course = tmp_path / "course"
    (course / "output").mkdir(parents=True)
    (course / "output" / "week-3.md").write_text("loops material", encoding="utf-8")
    pd = course / "pages" / "week-3"
    pd.mkdir(parents=True)
    (pd / "page.json").write_text(good_page().model_dump_json(), encoding="utf-8")

    rubrics, out = ped.evaluate_course_pedagogy(course, provider=_FakeRubric(), model="m")
    assert len(rubrics) == 1 and out is not None and out.exists()
    assert rubrics[0].page_id == "week-3"          # labelled by week for the course report
    assert "Page pedagogy" in out.read_text()
