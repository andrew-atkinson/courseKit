import json

import pytest

from coursekit.generate.page import page as P
from coursekit.generate.page.page import ValidationError


@pytest.fixture
def fresh():
    P.reset()
    yield
    P.reset()


# ------------------------------------------------------------- builders

def test_build_each_block_kind(fresh):
    assert P.build_block("heading", block_id="h", text="REVIEW").kind == "heading"
    assert P.build_block("paragraph", block_id="p", text="A recap.").kind == "paragraph"
    assert P.build_block("bullets", block_id="b", items=["one", "two"]).items == ["one", "two"]
    assert P.build_block("code", block_id="c", code="for (;;){}", language="js").language == "js"
    g = P.build_block("glossary", block_id="g",
                      entries=[{"term": "loop", "definition": "repeat"}])
    assert g.entries[0].term == "loop"
    assert P.build_block("callout", block_id="w", text="don't panic", tone="warning").tone == "warning"


def test_unknown_kind_rejected(fresh):
    with pytest.raises(ValueError, match="unknown block kind"):
        P.build_block("video", block_id="v", src="x")


def test_bullets_needs_a_nonempty_item(fresh):
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
def test_urls_rejected_in_model_prose(fresh, kind, kwargs):
    # The model must never author a link; references/embeds come from the supplements file.
    with pytest.raises(ValidationError, match="links are not allowed"):
        P.build_block(kind, block_id="x", **kwargs)


def test_glossary_url_rejected(fresh):
    with pytest.raises(ValidationError, match="links are not allowed"):
        P.build_block("glossary", block_id="g",
                      entries=[{"term": "t", "definition": "see https://x.io"}])


def test_code_may_contain_a_url(fresh):
    # A URL inside code is literal text rendered escaped, not a clickable link — allowed.
    b = P.build_block("code", block_id="c", code="fetch('https://api.example.com')")
    assert "https://api.example.com" in b.code


# --------------------------------------------------- overwrite + autosave

def test_put_block_appends_then_overwrites_in_place(fresh):
    P.put_block(P.build_block("heading", block_id="review", text="REVIEW"))
    P.put_block(P.build_block("paragraph", block_id="intro", text="first"))
    # revise the intro — same id overwrites, keeps its position
    P.put_block(P.build_block("paragraph", block_id="intro", text="second"))

    page = P.get()
    assert list(page.blocks) == ["review", "intro"]      # order preserved, no pile-up
    assert page.blocks["intro"].text == "second"          # latest wins


def test_autosave_writes_page_json(fresh, tmp_path):
    P.init("wk3", tmp_path, title="Week 3: Repetition", slug="week-3-repetition")
    P.put_block(P.build_block("heading", block_id="h", text="REVIEW"))

    saved = json.loads((tmp_path / "page.json").read_text())
    assert saved["title"] == "Week 3: Repetition"
    assert saved["blocks"]["h"]["text"] == "REVIEW"
    assert saved["finalized"] is False


# --------------------------------------------------------- finalize

def test_finalize_requires_a_heading(fresh):
    P.put_block(P.build_block("paragraph", block_id="p", text="just prose"))
    assert "no heading" in "; ".join(P.validate_final())
    assert P.finalize().startswith("ERROR")
    assert not P.is_finalized()


def test_finalize_succeeds_with_a_heading(fresh):
    P.put_block(P.build_block("heading", block_id="h", text="REVIEW"))
    assert P.validate_final() == []
    assert P.finalize().startswith("OK")
    assert P.is_finalized()


def test_empty_page_is_not_finalizable(fresh):
    assert "no blocks" in "; ".join(P.validate_final())
