import html as htmllib
import json

import pytest

from coursekit.emit import html as html_emit
from coursekit.generate.page import page as P
from coursekit.generate.page.renderer import load_supplements, render_body


@pytest.fixture
def fresh():
    P.reset()
    yield
    P.reset()


def _page_with(*blocks):
    P.reset()
    for b in blocks:
        P.put_block(P.build_block(**b))
    return P.get()


# ------------------------------------------------------------- block HTML

def test_heading_matches_canvas_grammar(fresh):
    body = render_body(_page_with(dict(kind="heading", block_id="h", text="REVIEW", level=4)))
    assert "<h4><strong>REVIEW</strong></h4>" in body


def test_bullets_use_li_span(fresh):
    body = render_body(_page_with(dict(kind="bullets", block_id="b", items=["one", "two"])))
    assert "<ul>" in body and "<li><span>one</span></li>" in body


def test_inline_markdown_in_prose(fresh):
    body = render_body(_page_with(
        dict(kind="paragraph", block_id="p", text="a **bold** and `code` and *em*")))
    assert "<strong>bold</strong>" in body
    assert "<code>code</code>" in body
    assert "<em>em</em>" in body


# --------------------------------------------- the escaping round-trip

def test_hostile_code_is_escaped_and_survives(fresh):
    code = "for (let x = 0; x < 10 && y > 2; x++){\n  print(a & b);\n}"
    body = render_body(_page_with(dict(kind="code", block_id="c", code=code, language="js")))
    # angle brackets and ampersands escaped, newlines become <br> — the Canvas <pre> convention
    assert "&lt; 10 &amp;&amp; y &gt; 2" in body
    assert "<br>" in body
    assert "<pre><span>" in body
    # and it round-trips: strip <br>, unescape entities, recover the original text
    recovered = htmllib.unescape(body.split("<pre><span>")[1].split("</span></pre>")[0]
                                 .replace("<br>", "\n"))
    assert recovered == code


def test_text_is_escaped_not_injected(fresh):
    body = render_body(_page_with(
        dict(kind="heading", block_id="h", text="a < b & c > d", level=2)))
    assert "&lt; b &amp; c &gt;" in body
    assert "<b " not in body  # not interpreted as a tag


# ------------------------------------------------------- supplements

def test_references_render_as_links(fresh):
    page = _page_with(dict(kind="heading", block_id="h", text="X"))
    supp = {"references": [{"label": "Reas — Process", "url": "https://example.com/reas"}]}
    body = render_body(page, supp)
    assert '<a href="https://example.com/reas" target="_blank">Reas — Process</a>' in body
    assert "<strong>References</strong>" in body


def test_allowlisted_embed_becomes_iframe(fresh):
    page = _page_with(dict(kind="heading", block_id="h", text="X"))
    supp = {"examples": [{"label": "sketch", "url": "https://editor.p5js.org/a/full/xyz",
                          "embed": True}]}
    body = render_body(page, supp)
    assert '<iframe src="https://editor.p5js.org/a/full/xyz"' in body


def test_non_allowlisted_embed_degrades_to_link(fresh):
    page = _page_with(dict(kind="heading", block_id="h", text="X"))
    supp = {"examples": [{"label": "sketchy", "url": "https://evil.example.com/x", "embed": True}]}
    body = render_body(page, supp)
    assert "<iframe" not in body
    assert '<a href="https://evil.example.com/x"' in body   # rendered as a plain link instead


def test_no_supplements_renders_only_blocks(fresh):
    body = render_body(_page_with(dict(kind="heading", block_id="h", text="X")))
    assert "References" not in body and "Examples" not in body


# ------------------------------------------------- supplements loader

def test_load_supplements_reads_the_course_file(tmp_path):
    d = tmp_path / ".vtconfig" / "pages"
    d.mkdir(parents=True)
    (d / "week-3.yaml").write_text(
        "references:\n  - label: R\n    url: https://x.io\n", encoding="utf-8")
    supp = load_supplements(tmp_path, "week-3")
    assert supp["references"][0]["label"] == "R"


def test_load_supplements_absent_is_empty(tmp_path):
    assert load_supplements(tmp_path, "week-9") == {}
    assert load_supplements(None, "week-9") == {}


# --------------------------------------- standalone document + emitter

def test_write_html_produces_a_document(fresh, tmp_path):
    page = _page_with(dict(kind="heading", block_id="h", text="REVIEW", level=4))
    path = html_emit.write_html(page, tmp_path)
    assert path.name == "page.html"    # default slug
    doc = path.read_text()
    assert doc.startswith("<!doctype html>")
    assert "<h4><strong>REVIEW</strong></h4>" in doc
