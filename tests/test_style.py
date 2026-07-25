"""The design-system guardrails: the Canvas-safe property allowlist and WCAG contrast.

The allowlist test is the styling analog of the no-URL rule: whatever a theme does, the renderer
cannot emit an inline CSS property Canvas's sanitizer would strip.
"""

import re

import pytest

from coursekit.generate.page import page as P
from coursekit.generate.page import style as S
from coursekit.generate.page.renderer import render_body


@pytest.fixture
def fresh():
    P.reset()
    yield
    P.reset()


def _full_page():
    P.reset()
    P.put_block(P.build_block(kind="heading", block_id="h", text="REVIEW", level=4))
    P.put_block(P.build_block(kind="paragraph", block_id="p", text="Some **prose** here."))
    P.put_block(P.build_block(kind="bullets", block_id="b", items=["one", "two"]))
    P.put_block(P.build_block(kind="code", block_id="c", code="let x = 0;\nx++;", language="js"))
    P.put_block(P.build_block(kind="glossary", block_id="g",
                              entries=[{"term": "loop", "definition": "repeats"}]))
    P.put_block(P.build_block(kind="callout", block_id="w", text="mind the gap", tone="warning"))
    return P.get()


_SUPP = {
    "references": [{"label": "R", "url": "https://x.io"}],
    "examples": [{"label": "E", "embed": True, "url": "https://editor.p5js.org/a/full/x"}],
}

_STYLE_ATTR = re.compile(r'style="([^"]*)"')


def _properties_used(html: str) -> set[str]:
    import html as htmllib
    props = set()
    for m in _STYLE_ATTR.finditer(html):
        # decode entities first (&#39; etc.), as a browser/sanitizer does before CSS parsing
        for decl in htmllib.unescape(m.group(1)).split(";"):
            decl = decl.strip()
            if decl:
                props.add(decl.split(":", 1)[0].strip().lower())
    return props


# ------------------------------------ the property-allowlist guardrail

@pytest.mark.parametrize("theme_name", ["terminal", "bauhaus", "plotter"])
def test_every_emitted_property_survives_canvas(fresh, theme_name):
    theme = S.load_theme(theme_name)
    theme["_name"] = theme_name
    html = render_body(_full_page(), _SUPP, theme)
    used = _properties_used(html)
    assert used, "the skin should be emitting styles"
    rogue = used - S.ALLOWED_CSS_PROPERTIES
    assert not rogue, f"{theme_name} emits properties Canvas would strip: {sorted(rogue)}"


# --------------------------------------------- WCAG contrast guardrails

@pytest.mark.parametrize("theme_name", ["terminal", "bauhaus", "plotter"])
def test_every_shipped_theme_passes_wcag(theme_name):
    assert S.validate_theme(S.load_theme(theme_name)) == []


def test_contrast_ratio_known_values():
    assert S.contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.1)
    assert S.contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0, abs=0.01)


def test_unreadable_accent_is_caught():
    theme = S.load_theme("bauhaus")
    theme["color"] = dict(theme["color"], accent="#ffff00")   # yellow on white: unreadable
    problems = S.validate_theme(theme)
    assert any("accent" in p for p in problems)


# ------------------------------------------------ style resolution

def test_load_style_defaults_when_no_course(tmp_path):
    t = S.load_style(None)
    assert t["_name"] == S.DEFAULT_THEME
    assert t["_problems"] == []


def test_course_selects_a_theme(tmp_path):
    (tmp_path / ".vtconfig").mkdir()
    (tmp_path / ".vtconfig" / "style.yaml").write_text("theme: terminal\n", encoding="utf-8")
    assert S.load_style(tmp_path)["_name"] == "terminal"


def test_unknown_theme_falls_back(tmp_path):
    (tmp_path / ".vtconfig").mkdir()
    (tmp_path / ".vtconfig" / "style.yaml").write_text("theme: vaporwave\n", encoding="utf-8")
    assert S.load_style(tmp_path)["_name"] == S.DEFAULT_THEME


def test_readable_accent_override_applies(tmp_path):
    (tmp_path / ".vtconfig").mkdir()
    (tmp_path / ".vtconfig" / "style.yaml").write_text(
        "theme: bauhaus\naccent: '#0a6e38'\n", encoding="utf-8")
    t = S.load_style(tmp_path)
    assert t["color"]["accent"] == "#0a6e38"
    assert t["_problems"] == []


def test_unreadable_accent_override_rejected_with_warning(tmp_path):
    (tmp_path / ".vtconfig").mkdir()
    (tmp_path / ".vtconfig" / "style.yaml").write_text(
        "theme: bauhaus\naccent: '#ffff00'\n", encoding="utf-8")
    t = S.load_style(tmp_path)
    assert t["color"]["accent"] != "#ffff00"      # kept the theme's own readable accent
    assert t["_problems"]                          # and said why


# --------------------------------------------- identity distinctness

def test_the_three_identities_actually_differ(fresh):
    page = _full_page()
    rendered = {n: render_body(page, style=dict(S.load_theme(n), _name=n))
                for n in ("terminal", "bauhaus", "plotter")}
    assert len(set(rendered.values())) == 3        # not token swaps of one look
    assert "background-color: #12333d" in rendered["terminal"]       # terminal's petrol ground
    assert "background-color: #2f4f59" in rendered["terminal"]       # …and a (default) segment chip
    assert "border-left: 3px solid #1d3fbf" in rendered["bauhaus"]   # bauhaus's structural bar
    assert "border-bottom: 1px solid #0b6e80" in rendered["plotter"] # plotter's riso-teal hairline


# --------------------------------------------- topic frames + images

def test_card_frame_wraps_heading_to_next_heading(fresh):
    P.reset()
    P.put_block(P.build_block(kind="heading", block_id="h1", text="Topic One", level=3))
    P.put_block(P.build_block(kind="paragraph", block_id="p1", text="about one"))
    P.put_block(P.build_block(kind="heading", block_id="h2", text="Topic Two", level=3))
    P.put_block(P.build_block(kind="code", block_id="c2", code="x = 1", language="js"))
    framed = render_body(P.get(), style=dict(S.load_theme("plotter"), _name="plotter"))
    unframed = render_body(P.get(), style=dict(S.load_theme("terminal"), _name="terminal"))

    # plotter frames each topic with its dashed registration hairline
    assert framed.count('border: 1px dashed #b9c2c9') == 2   # two topics, two cards
    assert "dashed" not in unframed                          # terminal stays flat


def test_frame_is_render_time_only(fresh):
    # page.json is identical either way — the frame never touches the IR
    P.reset()
    P.put_block(P.build_block(kind="heading", block_id="h", text="T", level=3))
    dumped = P.get().model_dump()
    assert "frame" not in str(dumped)


def test_images_supplement_renders_figures(fresh):
    page = _full_page()
    supp = {"images": [{"url": "https://x.io/photo.jpg", "caption": "f/2.8 — shallow depth",
                        "alt": "portrait"}]}
    html = render_body(page, supp, dict(S.load_theme("studio"), _name="studio"))
    assert '<img src="https://x.io/photo.jpg"' in html
    assert 'alt="portrait"' in html
    assert "f/2.8 — shallow depth" in html
    assert "<figure" in html and "<figcaption" in html


@pytest.mark.parametrize("theme_name", ["terminal", "bauhaus", "plotter", "studio"])
def test_allowlist_holds_with_frames_and_images(fresh, theme_name):
    theme = dict(S.load_theme(theme_name), _name=theme_name)
    supp = dict(_SUPP, images=[{"url": "https://x.io/a.jpg", "caption": "c"}])
    html = render_body(_full_page(), supp, theme)
    rogue = _properties_used(html) - S.ALLOWED_CSS_PROPERTIES
    assert not rogue, f"{theme_name}: {sorted(rogue)}"


def test_studio_theme_valid_and_quiet():
    t = S.load_theme("studio")
    assert S.validate_theme(t) == []
    assert t["shape"]["heading_marker"] == "none"    # the quiet identity: type only


# ------------------------------------ role-based framing + surface + a11y

def test_review_is_a_recap_container_of_question_accordions(fresh):
    # a review section is a block-level Recap CONTAINER (a bordered box in the theme's idiom) holding
    # one accordion per recall question — the container is not itself collapsible.
    for name, rborder in (("bauhaus", "#d4d4d4"), ("terminal", "#3f6b78"),
                          ("plotter", "#c9d1d6"), ("studio", "#ddd9d6")):
        P.reset()
        P.put_block(P.build_block(kind="heading", block_id="r", text="Recap", level=2, role="review"))
        P.put_block(P.build_block(kind="details", block_id="q1", summary="What is X?", text="X is a thing."))
        P.put_block(P.build_block(kind="details", block_id="q2", summary="What is Y?", text="Y is another."))
        html = render_body(P.get(), style=dict(S.load_theme(name), _name=name))
        assert rborder in html, name                 # the container's theme-idiom border
        assert html.count("<details") == 2, name     # one accordion per question, not one for the recap
        assert "What is X?" in html and "What is Y?" in html, name
        # the question dominates (recap ink) and the revealed answer recedes (recap muted)
        c = S.load_theme(name)["color"]
        q_color, a_color = c.get("recap_ink", c["ink"]), c.get("recap_muted", c["muted"])
        assert f'color: {q_color}' in html and f'color: {a_color}' in html, name


def test_terminal_recap_is_a_light_note_defined_by_a_linear_border(fresh):
    # terminal's recap is a pale box with DARK text (readable) set off from the dark page by a rule
    P.reset()
    P.put_block(P.build_block(kind="heading", block_id="r", text="Recap", level=2, role="review"))
    P.put_block(P.build_block(kind="details", block_id="q", summary="Recall?", text="Yes."))
    html = render_body(P.get(), style=dict(S.load_theme("terminal"), _name="terminal"))
    assert "background-color: #dbe6e9" in html        # the pale recap ground
    assert "color: #12333d" in html                   # dark petrol question text (high contrast)
    assert "#3f6b78" in html                          # the linear border that defines the box
    assert "1px" in html.split("background-color: #dbe6e9")[1][:80]   # a thin (1px) border, not heavy


def test_recap_header_names_the_prior_topic(fresh):
    P.reset()
    P.put_block(P.build_block(kind="heading", block_id="r", text="Still Life", level=2, role="review"))
    P.put_block(P.build_block(kind="details", block_id="q", summary="Q?", text="A."))
    html = render_body(P.get(), style=dict(S.load_theme("bauhaus"), _name="bauhaus"))
    assert "Still Life Recap" in html               # topic + label composed


def test_recap_header_does_not_double_a_generic_topic(fresh):
    P.reset()
    P.put_block(P.build_block(kind="heading", block_id="r", text="Recap", level=2, role="review"))
    P.put_block(P.build_block(kind="details", block_id="q", summary="Q?", text="A."))
    html = render_body(P.get(), style=dict(S.load_theme("bauhaus"), _name="bauhaus"))
    assert "Recap Recap" not in html                # a generic heading falls back to just the label


def _glossary_container_style(html):
    import re
    m = re.search(r'<div style="([^"]*)">\s*<div style="[^"]*font-size[^"]*">[^<]*Key Terms', html)
    return m.group(1) if m else ""


def test_standalone_glossary_is_a_framed_key_terms_block(fresh):
    # a standalone glossary (its own block / the week's terms) reads as its own framed box, with a
    # per-theme glyph marking it
    for name in ("bauhaus", "terminal", "plotter", "studio"):
        P.reset()
        P.put_block(P.build_block(kind="glossary", block_id="g",
                                  entries=[{"term": "Ha-ha", "definition": "a sunken wall"}]))
        html = render_body(P.get(), style=dict(S.load_theme(name), _name=name))
        theme = S.load_theme(name)
        c = theme["color"]
        assert "Key Terms" in html and "Ha-ha" in html, name
        assert "border-radius" in _glossary_container_style(html), name  # a full framed box
        assert f'color: {c["accent"]}' in html, name                     # label in the accent tone
        assert theme["glyphs"]["key_terms"] in html, name                # the graphic mark


def test_glossary_folds_into_a_concept_section(fresh):
    # key terms under a concept, with more page after them, are specific to it: they fold in as a
    # subsection — a top rule + label, no separate box
    P.reset()
    P.put_block(P.build_block(kind="heading", block_id="c", text="Landscape", level=2, role="concept"))
    P.put_block(P.build_block(kind="bullets", block_id="b", items=["conflict on the land"]))
    P.put_block(P.build_block(kind="glossary", block_id="g",
                              entries=[{"term": "Sublime", "definition": "awe"}]))
    P.put_block(P.build_block(kind="heading", block_id="c2", text="Beauty", level=2, role="concept"))
    P.put_block(P.build_block(kind="bullets", block_id="b2", items=["the picturesque"]))
    html = render_body(P.get(), style=dict(S.load_theme("bauhaus"), _name="bauhaus"))
    style = _glossary_container_style(html)
    assert "Landscape · Key Terms" in html and "Sublime" in html         # label names its concept
    assert "border-top" in style and "border-radius" not in style        # a rule, not a box


def test_trailing_week_glossary_is_peeled_to_standalone(fresh):
    # a glossary tacked onto the end of the last concept is the week's terms — it stands alone (a box),
    # it does not fold into that concept
    P.reset()
    P.put_block(P.build_block(kind="heading", block_id="c", text="Landscape", level=2, role="concept"))
    P.put_block(P.build_block(kind="bullets", block_id="b", items=["conflict on the land"]))
    P.put_block(P.build_block(kind="glossary", block_id="g",
                              entries=[{"term": "Sublime", "definition": "awe"}]))
    html = render_body(P.get(), style=dict(S.load_theme("bauhaus"), _name="bauhaus"))
    assert "border-radius" in _glossary_container_style(html)            # framed, not folded


def test_glossary_label_is_configurable(tmp_path):
    (tmp_path / ".vtconfig").mkdir()
    (tmp_path / ".vtconfig" / "style.yaml").write_text(
        "theme: bauhaus\nglossary_label: Vocabulary\n", encoding="utf-8")
    P.reset()
    P.put_block(P.build_block(kind="glossary", block_id="g",
                              entries=[{"term": "T", "definition": "d"}]))
    html = render_body(P.get(), style=S.load_style(tmp_path))
    assert "Vocabulary" in html and "Key Terms" not in html


def test_terminal_glossary_sits_on_a_ground_for_legibility(fresh):
    # in a dark identity the Key Terms frame carries its ground so the light ink stays readable
    P.reset()
    P.put_block(P.build_block(kind="glossary", block_id="g",
                              entries=[{"term": "T", "definition": "d"}]))
    html = render_body(P.get(), style=dict(S.load_theme("terminal"), _name="terminal"))
    assert "background-color: #12333d" in html               # the petrol ground under the terms


def test_a_non_review_section_is_not_a_recap(fresh):
    P.reset()
    P.put_block(P.build_block(kind="heading", block_id="c", text="Core Idea", level=2, role="concept"))
    P.put_block(P.build_block(kind="details", block_id="d", summary="Predict?", text="answer"))
    html = render_body(P.get(), style=dict(S.load_theme("bauhaus"), _name="bauhaus"))
    assert "Recap" not in html                       # no recap label for a non-review section


def test_role_glyph_renders_in_accent(fresh):
    P.reset()
    P.put_block(P.build_block(kind="heading", block_id="c", text="Loops", level=3, role="concept"))
    html = render_body(P.get(), style=dict(S.load_theme("bauhaus"), _name="bauhaus"))
    assert "■" in html                          # bauhaus's concept glyph


def test_terminal_panels_each_section_on_petrol(fresh):
    # terminal breaks into per-section petrol panels (with white gaps), not one full-bleed slab
    P.reset()
    P.put_block(P.build_block(kind="heading", block_id="a", text="One", level=3, role="concept"))
    P.put_block(P.build_block(kind="paragraph", block_id="pa", text="x"))
    P.put_block(P.build_block(kind="heading", block_id="b", text="Two", level=3, role="concept"))
    P.put_block(P.build_block(kind="paragraph", block_id="pb", text="y"))
    html = render_body(P.get(), style=dict(S.load_theme("terminal"), _name="terminal"))
    assert html.count("background-color: #12333d") == 2       # two separate petrol panels
    assert html.count("margin: 0 0 22px 0") == 2              # …each with a gap after it (breathing room)
    assert "border-left: 12px solid" in html                  # the CSS powerline chevron


def test_images_without_alt_or_caption_are_dropped(fresh):
    page = _full_page()
    supp = {"images": [
        {"url": "https://x.io/good.jpg", "alt": "a portrait"},
        {"url": "https://x.io/bad.jpg"},               # no alt, no caption -> must not ship
    ]}
    html = render_body(page, supp, dict(S.load_theme("studio"), _name="studio"))
    assert "good.jpg" in html
    assert "bad.jpg" not in html


def test_every_img_has_nonempty_alt_and_every_iframe_a_title(fresh):
    page = _full_page()
    supp = {
        "images": [{"url": "https://x.io/a.jpg", "caption": "used as alt"}],
        "examples": [{"label": "demo", "embed": True, "url": "https://editor.p5js.org/a/full/x"},
                     {"embed": True, "url": "https://www.youtube.com/embed/xyz"}],   # label-less
    }
    for name in ("terminal", "bauhaus", "plotter", "studio"):
        html = render_body(page, supp, dict(S.load_theme(name), _name=name))
        for m in re.finditer(r"<img [^>]*>", html):
            assert re.search(r'alt="[^"]+"', m.group(0)), f"{name}: img without alt"
        for m in re.finditer(r"<iframe [^>]*>", html):
            assert re.search(r'title="[^"]+"', m.group(0)), f"{name}: iframe without title"


def test_terminal_segments_color_by_role(fresh):
    P.reset()
    P.put_block(P.build_block(kind="heading", block_id="c", text="Core", level=3, role="concept"))
    P.put_block(P.build_block(kind="heading", block_id="p", text="Do", level=3, role="practice"))
    html = render_body(P.get(), style=dict(S.load_theme("terminal"), _name="terminal"))
    assert "background-color: #1f6a86" in html    # concept chip = blue (the "path" segment)
    assert "background-color: #8a5a12" in html    # practice chip = amber (the "git" segment)
    assert "$" not in html                         # the literal prompt gimmick is gone


# --------------------------------------------- pedagogy devices, styled

def _device_page():
    P.reset()
    P.put_block(P.build_block(kind="columns", block_id="c", columns=[
        {"title": "A", "items": ["a1", "a2"]}, {"title": "B", "items": ["b1"]}]))
    P.put_block(P.build_block(kind="pullquote", block_id="pq", text="the one idea", attribution="src"))
    P.put_block(P.build_block(kind="card", block_id="cd", card_kind="example", title="Ex", text="body"))
    P.put_block(P.build_block(kind="details", block_id="dt", summary="predict?", text="answer"))
    return P.get()


@pytest.mark.parametrize("theme_name", ["terminal", "bauhaus", "plotter", "studio"])
def test_devices_stay_within_the_allowlist(fresh, theme_name):
    html = render_body(_device_page(), style=dict(S.load_theme(theme_name), _name=theme_name))
    rogue = _properties_used(html) - S.ALLOWED_CSS_PROPERTIES
    assert not rogue, f"{theme_name} devices emit stripped properties: {sorted(rogue)}"


def test_columns_render_side_by_side(fresh):
    html = render_body(_device_page(), style=dict(S.load_theme("bauhaus"), _name="bauhaus"))
    assert "display: flex" in html and "flex-wrap: wrap" in html
    assert ">A</div>" in html and ">B</div>" in html      # both column titles present


def test_details_is_native_no_js(fresh):
    html = render_body(_device_page(), style=dict(S.load_theme("bauhaus"), _name="bauhaus"))
    assert "<details" in html and "<summary" in html
    assert "<script" not in html                          # progressive disclosure without JS


# ------------------------- action affordances vs meaning icons (UI/UX rule)

def test_disclosure_is_an_enclosed_control_not_a_bare_glyph(fresh):
    # An interactive affordance must read as a control: enclosed (border) + pointer cursor.
    # A descriptive role glyph must stay bare (no border, no pointer). This keeps "click me"
    # graphically distinct from "this is what this section is".
    P.reset()
    P.put_block(P.build_block(kind="heading", block_id="h", text="Concept", level=3, role="concept"))
    P.put_block(P.build_block(kind="details", block_id="d", summary="reveal?", text="answer"))
    html = render_body(P.get(), style=dict(S.load_theme("bauhaus"), _name="bauhaus"))

    import re as _re
    details = _re.search(r"<details[^>]*>", html).group(0)
    assert "border:" in details                                    # the FRAME encloses Q and A together
    summary = _re.search(r"<summary[^>]*>", html).group(0)
    assert "cursor: pointer" in summary and "background-color:" in summary  # a full-width tappable bar
    # the answer lives inside the same frame (between summary and </details>)
    assert html.index("answer") < html.index("</details>")
    heading = _re.search(r"<h3[^>]*>.*?</h3>", html, _re.S).group(0)
    assert "cursor: pointer" not in heading and "<details" not in heading  # meaning = bare, not a control


def test_disclosure_uses_the_native_rotating_marker(fresh):
    # The native <details> marker is kept (not suppressed) — it's the only thing that can rotate on
    # open/close without JS or a stylesheet, both of which Canvas strips. The enclosing control bar
    # keeps it reading as an action, so it no longer needs a hand-drawn chevron.
    P.reset()
    P.put_block(P.build_block(kind="details", block_id="d", summary="q", text="a"))
    html = render_body(P.get(), style=dict(S.load_theme("terminal"), _name="terminal"))
    summary = html[html.index("<summary"):html.index("</summary>")]
    assert "list-style-type: none" not in summary   # marker NOT suppressed -> rotates natively
    assert "▾" not in summary                   # and no static hand-drawn chevron


def test_answers_are_hidden_by_default(fresh):
    # retrieval practice = predict, then reveal. The answer is present (accessible) but collapsed.
    P.reset()
    P.put_block(P.build_block(kind="details", block_id="d", summary="predict?", text="the answer"))
    html = render_body(P.get(), style=dict(S.load_theme("bauhaus"), _name="bauhaus"))
    assert "<details open" not in html and "<details  open" not in html   # no open attr -> collapsed
    assert "the answer" in html                                           # but present in the DOM
