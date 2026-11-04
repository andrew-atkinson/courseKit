import json

import pytest

from coursekit.generate.page import page as P
from coursekit.generate.page.page import ValidationError


@pytest.fixture
def d():
    return P.PageDraft.new("test")


# ------------------------------------------------------------- builders

def test_build_each_block_kind():
    assert P.build_block("heading", block_id="h", text="REVIEW").kind == "heading"
    assert P.build_block("paragraph", block_id="p", text="A recap.").kind == "paragraph"
    assert P.build_block("bullets", block_id="b", items=["one", "two"]).items == ["one", "two"]
    assert P.build_block("code", block_id="c", code="for (;;){}", language="js").language == "js"
    g = P.build_block("glossary", block_id="g",
                      entries=[{"term": "loop", "definition": "repeat"}])
    assert g.entries[0].term == "loop"
    assert P.build_block("callout", block_id="w", text="don't panic", tone="warning").tone == "warning"


def test_unknown_kind_rejected():
    with pytest.raises(ValueError, match="unknown block kind"):
        P.build_block("video", block_id="v", src="x")


def test_bullets_needs_a_nonempty_item():
    with pytest.raises(ValidationError):
        P.build_block("bullets", block_id="b", items=["  ", ""])


# --------------------------------------------------- the URL guardrail

@pytest.mark.parametrize("kind,kwargs", [
    ("heading", {"text": "See https://example.com"}),
    ("paragraph", {"text": "Read more at www.example.com"}),
    ("paragraph", {"text": "A [link](http://x.io) in markdown"}),
    ("bullets", {"items": ["fine", "bad https://x.io"]}),
    ("callout", {"text": "visit https://x"}),
])
def test_urls_rejected_in_model_prose(kind, kwargs):
    # The model must never author a link; references/embeds come from the supplements file.
    with pytest.raises(ValidationError, match="links are not allowed"):
        P.build_block(kind, block_id="x", **kwargs)


def test_glossary_url_rejected():
    with pytest.raises(ValidationError, match="links are not allowed"):
        P.build_block("glossary", block_id="g",
                      entries=[{"term": "t", "definition": "see https://x.io"}])


def test_code_may_contain_a_url():
    # A URL inside code is literal text rendered escaped, not a clickable link — allowed.
    b = P.build_block("code", block_id="c", code="fetch('https://api.example.com')")
    assert "https://api.example.com" in b.code


# --------------------------------------------------- overwrite + autosave

def test_put_block_appends_then_overwrites_in_place(d):
    d.put_block(P.build_block("heading", block_id="review", text="REVIEW"))
    d.put_block(P.build_block("paragraph", block_id="intro", text="first"))
    # revise the intro — same id overwrites, keeps its position
    d.put_block(P.build_block("paragraph", block_id="intro", text="second"))

    page = d.page
    assert list(page.blocks) == ["review", "intro"]      # order preserved, no pile-up
    assert page.blocks["intro"].text == "second"          # latest wins


def test_autosave_writes_the_in_progress_page(tmp_path):
    d = P.PageDraft.new("wk3", tmp_path, title="Week 3: Repetition", slug="week-3-repetition")
    d.put_block(P.build_block("heading", block_id="h", text="REVIEW"))

    assert not (tmp_path / "page.json").exists()          # only a finalized build is promoted
    saved = json.loads((tmp_path / "page.partial.json").read_text())
    assert saved["title"] == "Week 3: Repetition"
    assert saved["blocks"]["h"]["text"] == "REVIEW"
    assert saved["finalized"] is False


# --------------------------------------------------------- finalize

def test_finalize_requires_a_heading(d):
    d.put_block(P.build_block("paragraph", block_id="p", text="just prose"))
    assert "no heading" in "; ".join(d.validate_final())
    assert d.finalize().startswith("ERROR")
    assert not d.is_finalized()


def test_finalize_requires_a_retrieval_prompt(d):
    # a heading is no longer enough — the page must ask the student to retrieve (a details foldout)
    d.put_block(P.build_block("heading", block_id="h", text="REVIEW"))
    assert "retrieval prompt" in "; ".join(d.validate_final())
    assert d.finalize().startswith("ERROR")
    assert not d.is_finalized()


def test_finalize_succeeds_with_a_heading_and_retrieval(d):
    d.put_block(P.build_block("heading", block_id="h", text="REVIEW"))
    d.put_block(P.build_block("details", block_id="predict",
                              summary="Predict: how many times does the loop run?", text="Ten."))
    assert d.validate_final() == []
    assert d.finalize().startswith("OK")
    assert d.is_finalized()


def _finishable_page(out_dir, page_id):
    d = P.PageDraft.new(page_id, out_dir, title="Week 3", slug="week-3")
    d.put_block(P.build_block("heading", block_id="h", text="REVIEW"))
    d.put_block(P.build_block("details", block_id="predict", summary="Predict?", text="Ten."))
    return d


def test_a_rerun_that_fails_before_finalize_leaves_the_good_page_byte_identical(tmp_path):
    d = _finishable_page(tmp_path, "good")
    assert d.finalize().startswith("OK")
    before = (tmp_path / "page.json").read_bytes()
    d = _finishable_page(tmp_path, "rerun")                     # autosaves twice, then dies unfinalized
    assert (tmp_path / "page.json").read_bytes() == before
    assert json.loads((tmp_path / "page.partial.json").read_text())["page_id"] == "rerun"
    assert d.finalize().startswith("OK")                    # ...and a finished re-run is promoted
    assert json.loads((tmp_path / "page.json").read_text())["page_id"] == "rerun"
    assert not (tmp_path / "page.partial.json").exists()


def test_empty_page_is_not_finalizable(d):
    assert "no blocks" in "; ".join(d.validate_final())


def test_finalize_rejects_a_heading_with_no_content_under_it(d):
    # the crowding failure: content first, then a section heading appended last → an empty section
    d.put_block(P.build_block("heading", block_id="h", text="Loops"))
    d.put_block(P.build_block("details", block_id="d", summary="Predict?", text="Ten."))
    d.put_block(P.build_block("heading", block_id="trailing", text="Nested Loops"))  # nothing after it
    msg = "; ".join(d.validate_final())
    assert "no content under them" in msg and "Nested Loops" in msg
    assert d.finalize().startswith("ERROR")
    assert not d.is_finalized()


def test_finalize_accepts_a_heading_followed_by_its_content(d):
    d.put_block(P.build_block("heading", block_id="h1", text="Loops"))
    d.put_block(P.build_block("paragraph", block_id="p1", text="Loops repeat a block."))
    d.put_block(P.build_block("heading", block_id="h2", text="Nested"))
    d.put_block(P.build_block("details", block_id="d", summary="Predict?", text="Ten."))
    assert d.validate_final() == []


# ------------------------------- pedagogy devices (columns/pullquote/card/details)

def test_columns_needs_two_or_three():
    with pytest.raises(ValidationError):
        P.build_block("columns", block_id="c", columns=[{"title": "only one", "items": ["x"]}])
    ok = P.build_block("columns", block_id="c", columns=[
        {"title": "A", "items": ["a1"]}, {"title": "B", "items": ["b1"]}])
    assert len(ok.columns) == 2


def test_column_items_reject_urls():
    with pytest.raises(ValidationError, match="links are not allowed"):
        P.build_block("columns", block_id="c", columns=[
            {"title": "A", "items": ["fine"]},
            {"title": "B", "items": ["see https://x.io"]}])


def test_pullquote_optional_attribution_and_url_guard():
    b = P.build_block("pullquote", block_id="p", text="the key idea")
    assert b.attribution is None
    with pytest.raises(ValidationError, match="links are not allowed"):
        P.build_block("pullquote", block_id="p", text="idea at https://x.io")


def test_card_kind_and_url_guard():
    b = P.build_block("card", block_id="c", card_kind="takeaway", title="T", text="body")
    assert b.card_kind == "takeaway"
    with pytest.raises(ValidationError):
        P.build_block("card", block_id="c", card_kind="bogus", title="T", text="b")
    with pytest.raises(ValidationError, match="links are not allowed"):
        P.build_block("card", block_id="c", title="T", text="see www.x.io")


def test_details_prompt_and_body():
    b = P.build_block("details", block_id="d", summary="predict?", text="the answer")
    assert b.summary == "predict?" and b.text == "the answer"
    with pytest.raises(ValidationError, match="links are not allowed"):
        P.build_block("details", block_id="d", summary="q", text="a [link](http://x.io)")
