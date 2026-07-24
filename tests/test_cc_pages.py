"""Offline tests for the Common Cartridge page emitter (emit/cc.py).

Mirrors the QTI tests' strategy — no Canvas, no model: every XML file parses, every manifest
reference resolves to a packaged file, the namespaces match the real export verbatim, hostile text
survives, and the zip is a well-formed `.imscc`. The one thing these cannot check is whether Canvas
accepts the package; that is the manual import acceptance gate.
"""

import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from pathlib import Path

import pytest


def _parses_as_html(doc: str) -> bool:
    """A Canvas wiki page is HTML5, not XML — it carries void `<br>` and entities like `&nbsp;`,
    exactly as Canvas's own exported pages do (so ET.fromstring would wrongly reject it). We only
    need it to parse as HTML without error and bracket the body in the envelope."""
    HTMLParser().feed(doc)   # raises only on genuinely broken markup
    tags = [doc.index(t) for t in ("<html>", "<head>", "</head>", "<body>", "</body>", "</html>")]
    return tags == sorted(tags)   # the six envelope tags appear, in order

from coursekit.emit import cc
from coursekit.generate.page import page as P


@pytest.fixture
def fresh():
    P.reset()
    yield
    P.reset()


def _page(page_id="c-week-3", title="Week 3: Repetition", slug="week-3-repetition",
          week_ref="week-3", blocks=None):
    P.reset()
    P.init(page_id, title=title, slug=slug, week_ref=week_ref)
    for b in blocks or (dict(kind="heading", block_id="h", text="REVIEW", level=4),):
        P.put_block(P.build_block(**b))
    return P.get()


# --------------------------------------------------------- the wiki page html

def test_page_html_has_the_canvas_meta_header(fresh):
    page = _page()
    doc = cc.render_page(page)
    # the exact head the real export carries
    assert '<meta name="editing_roles" content="teachers"/>' in doc
    assert '<meta name="workflow_state" content="active"/>' in doc
    assert "<title>Week 3: Repetition</title>" in doc
    # the identifier meta MUST match the resource id (Canvas ties them together)
    assert f'<meta name="identifier" content="{cc.page_ident(page)}"/>' in doc


def test_page_html_parses_and_brackets_the_body(fresh):
    doc = cc.render_page(_page(
        page_id="c", title="X", slug="x", week_ref=None,
        blocks=[dict(kind="heading", block_id="h", text="A", level=4),
                dict(kind="bullets", block_id="b", items=["one", "two"])]))
    assert _parses_as_html(doc)


def test_page_body_carries_the_rendered_blocks_not_the_title_as_h1(fresh):
    doc = cc.render_page(_page(
        page_id="c", title="My Title", slug="s", week_ref=None,
        blocks=[dict(kind="heading", block_id="h", text="REVIEW", level=4)]))
    import re
    assert re.search(r"<h4[^>]*>.*REVIEW.*</h4>", doc, re.S)
    # the page title is the <title>/page name, never repeated as a body <h1> (matches real pages)
    assert "<h1" not in doc


def test_hostile_text_survives_into_the_page(fresh):
    doc = cc.render_page(_page(
        page_id="c", title="A < B & C", slug="s", week_ref=None,
        blocks=[dict(kind="heading", block_id="h", text="x < y & z", level=4)]))
    assert _parses_as_html(doc)              # still structurally sound HTML
    assert "A &lt; B &amp; C" in doc         # title escaped
    assert "&lt; y &amp; z" in doc           # body escaped by the renderer


# -------------------------------------------------------------- the manifest

def test_manifest_namespaces_match_the_export(fresh):
    body = cc.emit_manifest([_page()], "A Course")
    assert 'xmlns="http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1"' in body
    assert 'xmlns:lomimscc="http://ltsc.ieee.org/xsd/imsccv1p1/LOM/manifest"' in body
    assert "<schema>IMS Common Cartridge</schema>" in body
    assert "<schemaversion>1.1.0</schemaversion>" in body
    ET.fromstring(body)


def test_manifest_has_a_webcontent_resource_per_page(fresh):
    p1 = _page(page_id="c-w1", title="W1", slug="week-1", week_ref="week-1")
    p2 = _page(page_id="c-w2", title="W2", slug="week-2", week_ref="week-2")
    body = cc.emit_manifest([p1, p2], "A Course")
    root = ET.fromstring(body)
    ns = {"cp": "http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1"}
    webcontent = [r for r in root.findall(".//cp:resource", ns) if r.get("type") == "webcontent"]
    assert len(webcontent) == 2   # one per page (plus the course_settings resource, filtered out)
    for r in webcontent:
        assert r.get("href").startswith("wiki_content/")


def test_manifest_course_title_is_escaped(fresh):
    body = cc.emit_manifest([_page()], "Art & Design < 101 >")
    assert "Art &amp; Design &lt; 101 &gt;" in body
    ET.fromstring(body)


# --------------------------------------------- reference integrity + packaging

def test_every_resource_href_is_a_packaged_file(fresh):
    entries = [(_page(page_id="c-w1", title="W1", slug="week-1", week_ref="week-1"), {}, None),
               (_page(page_id="c-w2", title="W2", slug="week-2", week_ref="week-2"), {}, None)]
    files = cc.package_files(entries, "A Course")

    manifest = ET.fromstring(files["imsmanifest.xml"])
    ns = {"cp": "http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1"}
    # every <file href> AND every <resource href> must resolve to a packaged file
    refs = ([f.get("href") for f in manifest.findall(".//cp:file", ns)]
            + [r.get("href") for r in manifest.findall(".//cp:resource", ns)])
    assert refs, "manifest references at least one file"
    for href in refs:
        assert href in files, f"manifest points at {href}, which is not in the package"


# ------------------------------------------- the Canvas-importer trigger + modules

def test_package_ships_the_canvas_export_marker(fresh):
    # the presence of this file is what makes Canvas import wiki_content as Pages, not Files
    files = cc.package_files([(_page(), {}, None)], "A Course")
    assert "course_settings/canvas_export.txt" in files
    # and the manifest declares it via the course_settings resource
    assert 'href="course_settings/canvas_export.txt"' in files["imsmanifest.xml"]


def test_module_meta_lists_each_page_as_a_wikipage(fresh):
    p1 = _page(page_id="c-w1", title="Week 1", slug="week-1", week_ref="week-1")
    p2 = _page(page_id="c-w2", title="Week 2", slug="week-2", week_ref="week-2")
    body = cc.emit_module_meta([p1, p2], "A Course")
    root = ET.fromstring(body)
    ns = {"c": "http://canvas.instructure.com/xsd/cccv1p0"}
    items = root.findall(".//c:module/c:items/c:item", ns)
    assert len(items) == 2
    for item, page in zip(items, (p1, p2)):
        assert item.find("c:content_type", ns).text == "WikiPage"
        # the module item points at the page's webcontent resource
        assert item.find("c:identifierref", ns).text == cc.page_ident(page)


def test_organizations_reference_every_page_resource(fresh):
    p1 = _page(page_id="c-w1", title="W1", slug="week-1", week_ref="week-1")
    p2 = _page(page_id="c-w2", title="W2", slug="week-2", week_ref="week-2")
    manifest = ET.fromstring(cc.emit_manifest([p1, p2], "A Course"))
    ns = {"cp": "http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1"}
    refs = {i.get("identifierref") for i in manifest.findall(".//cp:organizations//cp:item", ns)
            if i.get("identifierref")}
    assert refs == {cc.page_ident(p1), cc.page_ident(p2)}


def test_no_course_settings_xml_is_shipped(fresh):
    # shipping course_settings.xml would mutate the target course's title/settings — never do it
    files = cc.package_files([(_page(), {}, None)], "A Course")
    assert "course_settings/course_settings.xml" not in files


def test_resource_identifier_matches_the_page_meta(fresh):
    page = _page(page_id="c-w1", title="W1", slug="week-1", week_ref="week-1")
    files = cc.package_files([(page, {}, None)], "A Course")
    manifest = ET.fromstring(files["imsmanifest.xml"])
    ns = {"cp": "http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1"}
    webcontent = next(r for r in manifest.findall(".//cp:resource", ns)
                      if r.get("type") == "webcontent")
    res_id = webcontent.get("identifier")
    # the id in the manifest resource == the id inside the wiki page's <meta name="identifier">
    assert f'content="{res_id}"' in files["wiki_content/week-1.html"]


def test_a_slug_collision_is_rejected_not_silently_dropped(fresh):
    same = [(_page(page_id="c-a", title="A", slug="dup", week_ref="week-1"), {}, None),
            (_page(page_id="c-b", title="B", slug="dup", week_ref="week-2"), {}, None)]
    with pytest.raises(ValueError, match="same file"):
        cc.package_files(same, "A Course")


# ------------------------------------------------- write_imscc over a course tree

def _course_tree(tmp_path):
    """A course with two committed page.json files under pages/, and a .vtconfig root."""
    course = tmp_path / "course"
    (course / ".vtconfig" / "pages").mkdir(parents=True)
    (course / ".vtconfig" / "pages" / "week-3.yaml").write_text(
        "references:\n  - label: Reas\n    url: https://example.com/reas\n", encoding="utf-8")
    for wk, slug in (("week-1", "week-1-intro"), ("week-3", "week-3-repetition")):
        pdir = course / "pages" / wk
        pdir.mkdir(parents=True)
        P.reset()
        P.init(f"c-{wk}", pdir, title=f"{wk.title()}", slug=slug, week_ref=wk)
        P.put_block(P.build_block(kind="heading", block_id="h", text="REVIEW", level=4))
    P.reset()
    return course


def test_write_imscc_bundles_every_page(tmp_path):
    course = _course_tree(tmp_path)
    out = cc.write_imscc(course)
    assert out is not None and out.suffix == ".imscc"

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "imsmanifest.xml" in names
        assert "course_settings/canvas_export.txt" in names   # the Pages-not-Files trigger
        assert "course_settings/module_meta.xml" in names
        assert "wiki_content/week-1-intro.html" in names
        assert "wiki_content/week-3-repetition.html" in names
        # manifest parses and every file it names exists in the zip
        manifest = ET.fromstring(z.read("imsmanifest.xml"))
        ns = {"cp": "http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1"}
        for f in manifest.findall(".//cp:file", ns):
            assert f.get("href") in names


def test_write_imscc_merges_supplements_at_package_time(tmp_path):
    course = _course_tree(tmp_path)
    out = cc.write_imscc(course)
    with zipfile.ZipFile(out) as z:
        page = z.read("wiki_content/week-3-repetition.html").decode("utf-8")
    # the week-3 supplements file's reference lands in the packaged page
    assert 'href="https://example.com/reas"' in page


def test_write_imscc_none_when_no_pages(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert cc.write_imscc(empty) is None
