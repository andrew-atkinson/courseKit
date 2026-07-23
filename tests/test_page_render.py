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
    import re as _re
    assert _re.search(r"<h4[^>]*>.*REVIEW.*</h4>", body, _re.S)   # styled now; structure + text hold


def test_bullets_use_li_span(fresh):
    body = render_body(_page_with(dict(kind="bullets", block_id="b", items=["one", "two"])))
    assert "<ul" in body and "<span>one</span>" in body   # li/ul carry theme styles now


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
    import re as _re
    m = _re.search(r"<pre[^>]*><span>(.*?)</span></pre>", body, _re.S)
    assert m, "styled pre/span block present"
    # and it round-trips: strip <br>, unescape entities, recover the original text
    recovered = htmllib.unescape(m.group(1).replace("<br>", "\n"))
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
    assert 'href="https://example.com/reas"' in body
    assert ">Reas — Process</a>" in body   # link styled in theme accent now
    assert ">References</h4>" in body   # heading weight is font-weight now, not <strong>


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
    import re as _re
    assert _re.search(r"<h4[^>]*>.*REVIEW.*</h4>", doc, _re.S)


# ------------------------------- supplements matched by week identity

def test_supplements_matched_by_week_number_not_exact_name(tmp_path):
    # File is named for the Canvas page, but we look it up by the bare week ref — both must work.
    d = tmp_path / ".vtconfig" / "pages"
    d.mkdir(parents=True)
    (d / "week-3-repetition.yaml").write_text(
        "references:\n  - label: R\n    url: https://x.io\n", encoding="utf-8")

    assert load_supplements(tmp_path, "week-3")["references"][0]["label"] == "R"
    assert load_supplements(tmp_path, "3")["references"][0]["label"] == "R"
    assert load_supplements(tmp_path, "week-9") == {}   # different week, no match


# ----------------------------------------- model-free re-render (--to-html)

def test_reemit_rerenders_page_json_with_current_supplements(tmp_path):
    from coursekit.emit.html import reemit
    # a course tree: a committed page.json under pages/, supplements under .vtconfig/
    course = tmp_path / "course"
    (course / ".vtconfig" / "pages").mkdir(parents=True)
    (course / ".vtconfig" / "pages" / "week-3.yaml").write_text(
        "references:\n  - label: Later Ref\n    url: https://late.io\n", encoding="utf-8")
    pdir = course / "pages" / "week-3"
    pdir.mkdir(parents=True)
    P.reset()
    P.init("c-week-3", pdir, title="Week 3", slug="week-3", week_ref="week-3")
    P.put_block(P.build_block(kind="heading", block_id="h", text="REVIEW", level=4))
    # (page.json now on disk via autosave)

    results = reemit(course)

    assert len(results) == 1
    html = (pdir / "week-3.html").read_text()
    import re as _re
    assert _re.search(r"<h4[^>]*>.*REVIEW.*</h4>", html, _re.S)   # the model's block, styled
    assert '<a href="https://late.io"' in html                 # supplement merged at re-render


# ------------------------------- pasted <iframe> snippets (slideshows etc.)

def test_pasted_iframe_snippet_is_parsed_and_re_emitted(fresh):
    page = _page_with(dict(kind="heading", block_id="h", text="X"))
    supp = {"examples": [{
        "label": "Lecture slides",
        "iframe": '<iframe src="https://docs.google.com/presentation/d/e/ABC/embed?start=false" '
                  'frameborder="0" width="960" height="569" allowfullscreen></iframe>',
    }]}
    body = render_body(page, supp)
    # our clean iframe, with the extracted src + dimensions, not the pasted attributes
    assert '<iframe src="https://docs.google.com/presentation/d/e/ABC/embed?start=false"' in body
    assert 'width="960"' in body and 'height="569"' in body
    assert "allowfullscreen" not in body and "frameborder" not in body


def test_pasted_iframe_from_disallowed_host_degrades_to_link(fresh):
    page = _page_with(dict(kind="heading", block_id="h", text="X"))
    supp = {"examples": [{"label": "sketchy",
                          "iframe": '<iframe src="https://evil.example.com/x" width="600"></iframe>'}]}
    body = render_body(page, supp)
    assert "<iframe" not in body
    assert '<a href="https://evil.example.com/x"' in body


def test_malformed_iframe_snippet_is_dropped(fresh):
    page = _page_with(dict(kind="heading", block_id="h", text="X"))
    body = render_body(page, {"examples": [{"label": "broken", "iframe": "<iframe no src here>"}]})
    assert "broken" not in body   # nothing usable, so nothing emitted
