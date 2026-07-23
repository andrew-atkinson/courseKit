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

def test_roles_select_which_topics_get_frames(fresh):
    # plotter frames concept/practice/example; a review section stays flat
    P.reset()
    P.put_block(P.build_block(kind="heading", block_id="r", text="Recap", level=3, role="review"))
    P.put_block(P.build_block(kind="bullets", block_id="rb", items=["old stuff"]))
    P.put_block(P.build_block(kind="heading", block_id="c", text="Core Idea", level=3, role="concept"))
    P.put_block(P.build_block(kind="paragraph", block_id="cp", text="the idea"))
    html = render_body(P.get(), style=dict(S.load_theme("plotter"), _name="plotter"))
    assert html.count("1px dashed") == 1        # only the concept topic is framed
    idx_recap = html.index("Recap")
    idx_frame = html.index("1px dashed")
    assert idx_frame > idx_recap                # and the frame is the later (concept) section


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
