"""Groundedness (EVAL-15) — offline, BLOCK-ANCHORED, with a fake critic (no model). Every content
block is examined (the denominator is the page's structure, not the model's whim), and each block's
claims are tagged grounded / tension / model."""

from coursekit.generate.page import groundedness as gnd
from coursekit.generate.page.page import Page, build_block


def _page(*paras):
    blocks = [build_block("heading", block_id="h", text="Heading", level=2, role="concept")]
    blocks += [build_block("paragraph", block_id=f"p{i}", text=t) for i, t in enumerate(paras)]
    return Page(page_id="t", title="T", blocks={b.block_id: b for b in blocks})


def _claims(*tags):
    return "CLAIMS:\n" + "\n".join(f"- claim {i}: {t} | note" for i, t in enumerate(tags)) + "\n"


class _SeqCritic:
    """One queued reply per call (one call per content block); records the call count."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def chat(self, *, model, messages, temperature=None, max_tokens=None, seed=None):
        r = self.replies[self.calls] if self.calls < len(self.replies) else "CLAIMS:\n"
        self.calls += 1
        return r


def test_parse_and_tag_normalise():
    reply = "CLAIMS:\n- a: GROUNDED | x\n- b: MODEL-SUPPLIED | y\n- c: in-tension | z\n"
    assert [c.tag for c in gnd._parse_claims(reply)] == ["grounded", "model", "tension"]
    assert gnd._tag("NOVEL") == "model" and gnd._tag("Grounded") == "grounded"


def test_parse_strips_echoed_angle_brackets_but_keeps_code():
    reply = ("CLAIMS:\n"
             "- <looks like marble>: MODEL | not in material\n"    # echoed <claim> template — strip
             "- the loop runs while `i < 5`: GROUNDED | material says so\n")  # real < kept
    claims = gnd._parse_claims(reply)
    assert claims[0].text == "looks like marble"
    assert "i < 5" in claims[1].text


def test_block_anchored_examines_every_content_block():
    page = _page("aaa", "bbb", "ccc")
    critic = _SeqCritic([_claims("GROUNDED"), _claims("MODEL"), _claims("TENSION")])
    pg = gnd.evaluate_page_groundedness(page, "material", critic, "m")
    assert critic.calls == 3                          # one call per paragraph; the heading is skipped
    assert pg.total == 3
    assert pg.engaging == 2 and pg.coverage == 2 / 3  # grounded + tension engage; model does not
    assert len(pg.tensions) == 1 and len(pg.model_supplied) == 1
    assert {c.block_id for c in pg.claims} == {"p0", "p1", "p2"}   # each claim carries its block


def test_multiple_claims_per_block_all_counted():
    # the whole-page v1 bug was under-extraction — here a block's several claims all land
    critic = _SeqCritic([_claims("GROUNDED", "MODEL", "MODEL")])
    pg = gnd.evaluate_page_groundedness(_page("one para, several claims"), "m", critic, "x")
    assert pg.total == 3 and pg.coverage == 1 / 3     # 1 grounded of 3


def test_a_block_critic_error_costs_only_that_block():
    class _Boom:
        def __init__(self):
            self.calls = 0

        def chat(self, **kw):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("down")
            return _claims("GROUNDED")
    pg = gnd.evaluate_page_groundedness(_page("a", "b", "c"), "m", _Boom(), "x")
    assert pg.total == 2                               # the errored block drops out; the others survive


def test_render_shows_split_flags_tension_and_lists_all_claims():
    critic = _SeqCritic([_claims("GROUNDED"), _claims("MODEL"), _claims("TENSION")])
    pg = gnd.evaluate_page_groundedness(_page("a", "b", "c"), "m", critic, "x")
    out = gnd.render_groundedness(pg)
    assert "67% engage the material" in out           # 2 of 3 engage
    assert "In tension" in out and "Model-supplied" in out
    assert "all 3 claims" in out                       # full transparency — every claim listed


def test_evaluate_course_groundedness_writes_one_report(tmp_path):
    course = tmp_path / "course"
    (course / "output").mkdir(parents=True)
    (course / "output" / "week-3.md").write_text("loops material", encoding="utf-8")
    pd = course / "pages" / "week-3"
    pd.mkdir(parents=True)
    page = _page("a", "b")
    (pd / "page.json").write_text(page.model_dump_json(), encoding="utf-8")

    critic = _SeqCritic([_claims("GROUNDED"), _claims("MODEL")])
    results, out = gnd.evaluate_course_groundedness(course, provider=critic, model="m")
    assert results and out == course / "pages" / "page-groundedness.md" and out.exists()
    assert "engage the material" in out.read_text(encoding="utf-8")


def test_calibration_fixtures_build_valid_pages():
    from coursekit.generate.page import groundedness_fixtures as fx
    for make in (fx.grounded_page, fx.model_supplied_page, fx.near_miss_page, fx.tension_page):
        assert make().blocks
