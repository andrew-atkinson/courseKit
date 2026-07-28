"""The page cold-read evaluator — offline, with a fake critic (no model)."""

from coursekit.generate.page import evaluate as pev
from coursekit.generate.page import page as pagemod


class _FakeCritic:
    """FLAGs any section containing `marker`, else PASS (accepts seed, like the real provider)."""
    def __init__(self, marker=None):
        self.marker = marker

    def chat(self, *, model, messages, temperature=None, max_tokens=None, seed=None):
        section = messages[1]["content"]
        if self.marker and self.marker in section:
            return "VERDICT: FLAG\nCONCERN: not in the material\nFIX: ground it in the lecture"
        return "VERDICT: PASS\nCONCERN:\nFIX:"


def _page():
    pagemod.reset()
    pagemod.init("p1", None, title="Week 3", week_ref="week-3", slug="week-3")
    pagemod.put_block(pagemod.build_block("heading", block_id="h1", text="Loops", level=2))
    pagemod.put_block(pagemod.build_block(
        "paragraph", block_id="b1", text="A for loop repeats a block a set number of times."))
    pagemod.put_block(pagemod.build_block(
        "paragraph", block_id="b2", text="Recursion OUTOFSCOPE is the tool this week."))
    pagemod.put_block(pagemod.build_block(
        "glossary", block_id="b3", entries=[{"term": "loop", "definition": "a repeated block"}]))
    return pagemod.get()


def test_format_block_renders_content_per_kind():
    b = _page().blocks
    assert pev._format_block(b["b1"]).startswith("[paragraph]")
    assert "loop — a repeated block" in pev._format_block(b["b3"])


def test_evaluate_page_skips_the_heading_and_flags_the_match():
    findings = pev.evaluate_page(_page(), "loops and iteration", _FakeCritic("OUTOFSCOPE"), "m")
    ids = {f.group_id for f in findings}
    assert "h1" not in ids                       # a heading is a label, not a factual claim
    assert {"b1", "b2", "b3"} <= ids
    flagged = [f for f in findings if f.flagged]
    assert len(flagged) == 1 and flagged[0].group_id == "b2"
    assert "not in the material" in flagged[0].concern


def test_evaluate_page_survives_a_flaky_critic():
    class _Boom:
        def chat(self, **kw):
            raise RuntimeError("model offline")
    findings = pev.evaluate_page(_page(), "t", _Boom(), "m")
    assert findings and all(f.verdict == "ERROR" for f in findings)   # reported, not aborted


def test_evaluate_course_pages_writes_a_review(tmp_path):
    course = tmp_path / "course"
    (course / "output").mkdir(parents=True)
    (course / "output" / "week-3.md").write_text("loops and iteration", encoding="utf-8")
    pd = course / "pages" / "week-3"
    pd.mkdir(parents=True)
    (pd / "page.json").write_text(_page().model_dump_json(), encoding="utf-8")

    findings, review = pev.evaluate_course_pages(course, provider=_FakeCritic("OUTOFSCOPE"), model="m")
    assert findings and review is not None and review.exists()
    text = review.read_text()
    assert "Page review" in text and "section(s) flagged" in text and "b2/paragraph" in text
