"""Render a page IR to Canvas-safe HTML.

One Jinja component per block kind (in `components/`), composed in order — the "component" model the
user asked for, without a JS runtime. The output grammar is taken from real Canvas pages: `<h4>`,
`<ul><li><span>`, `<pre><span>…<br>…`, entity-escaped throughout.

Two things enter here that the model never authored: the **supplements** (a course's own references,
examples, and embeds, from `.vtconfig/pages/<slug>.yaml`) are merged at *render* time, so they
survive a regenerate of `page.json` and their URLs land verbatim. Embeds are only rendered as an
`<iframe>` when their host is on the allowlist; anything else degrades to a plain link.
"""

import re
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

_COMPONENTS = Path(__file__).resolve().parent / "components"

# Hosts Canvas will keep as an <iframe>. Not the two courses we happened to see — the general set.
ALLOWED_EMBED_HOSTS = (
    "editor.p5js.org", "youtube.com", "youtu.be", "player.vimeo.com", "vimeo.com",
    "docs.google.com", "drive.google.com", "panopto.com", "hosted.panopto.com",
)

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITAL = re.compile(r"\*(.+?)\*")
_CODE = re.compile(r"`(.+?)`")

# ------------------------------------------------------------------- inline math
#
# Models trained on math-heavy text emit LaTeX (`$\rightarrow$`, `$a \leq b$`) even for an art
# course; Canvas does NOT render bare `$…$`, so it would ship as literal source. The strategy here
# is deliberately the *simple* one — map the handful of symbols that actually show up to their
# Unicode glyph and drop the delimiters, so `$\rightarrow$` becomes `→` with no MathJax needed.
#
# `_render_math` is the single swap point. To add real typeset math later, replace it with a
# strategy that wraps spans in Canvas's `\(…\)` MathJax delimiters (or emits equation markup); the
# call site in `_md_inline` does not change. Crucially, this version is *information-preserving*: a
# span whose LaTeX it cannot fully resolve is left untouched (still `$…\command…$`), which is
# exactly what a future MathJax pass would look for — nothing is destroyed on the way through.
_LATEX_UNICODE = {
    r"\rightarrow": "→", r"\to": "→", r"\Rightarrow": "⇒", r"\implies": "⇒",
    r"\leftarrow": "←", r"\gets": "←", r"\leftrightarrow": "↔", r"\mapsto": "↦",
    r"\uparrow": "↑", r"\downarrow": "↓",
    r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥", r"\neq": "≠", r"\ne": "≠",
    r"\times": "×", r"\div": "÷", r"\cdot": "·", r"\pm": "±", r"\mp": "∓",
    r"\approx": "≈", r"\equiv": "≡", r"\propto": "∝", r"\infty": "∞", r"\partial": "∂",
    r"\pi": "π", r"\tau": "τ", r"\theta": "θ", r"\alpha": "α", r"\beta": "β",
    r"\gamma": "γ", r"\delta": "δ", r"\lambda": "λ", r"\mu": "μ", r"\sigma": "σ", r"\phi": "φ",
    r"\degree": "°", r"\circ": "∘", r"\sum": "∑", r"\prod": "∏", r"\sqrt": "√",
    r"\ldots": "…", r"\dots": "…", r"\cdots": "⋯",
}
_MATH_TOKEN = re.compile(r"\\[a-zA-Z]+")
# $…$ only counts as math when it contains a \command — so prose like "$5 and $10" is left alone.
_DOLLAR_MATH = re.compile(r"\$([^$]*\\[a-zA-Z][^$]*)\$")
_PAREN_MATH = re.compile(r"\\\((.+?)\\\)")   # \(…\): an explicit LaTeX inline-math delimiter


def _render_math(s: str) -> str:
    """Resolve inline LaTeX math to Unicode; leave anything it can't fully resolve intact.

    The one swap point for math rendering (see the note above). A span is converted only when
    every `\\command` in it maps to a glyph; otherwise the original `$…$` / `\\(…\\)` is preserved
    so no information is lost and a later MathJax strategy can pick it up.
    """
    def _resolve(inner: str):
        converted = _MATH_TOKEN.sub(lambda t: _LATEX_UNICODE.get(t.group(0), t.group(0)), inner)
        return converted, _MATH_TOKEN.search(converted) is None   # (text, fully_resolved?)

    def _span(m):
        converted, done = _resolve(m.group(1))
        return converted if done else m.group(0)

    return _PAREN_MATH.sub(_span, _DOLLAR_MATH.sub(_span, s))


# The inline-code chip style, set per render from the active theme (render_body). A self-contained
# chip — the theme's WCAG-validated code_bg/code_fg pair — so `code` reads on ANY ground (a dark
# terminal panel, or the white gaps between panels, where a bare unstyled <code> went light-on-white).
_INLINE_CODE_STYLE = ""


def _md_inline(value) -> Markup:
    """Escape, resolve inline math, then apply inline Markdown (**bold**, *italic*, `code`).
    Escaping first means every later pass acts on safe text and a user's `<` is already `&lt;`."""
    s = str(escape(value))
    s = _render_math(s)
    s = _BOLD.sub(r"<strong>\1</strong>", s)
    s = _ITAL.sub(r"<em>\1</em>", s)
    tag = f'<code style="{_INLINE_CODE_STYLE}">' if _INLINE_CODE_STYLE else "<code>"
    s = _CODE.sub(lambda m: f"{tag}{m.group(1)}</code>", s)
    return Markup(s)


def _nl2br(value) -> Markup:
    """Escape each line and join with <br> — the `<pre><span>…<br>…` convention Canvas uses."""
    return Markup("<br>".join(str(escape(line)) for line in str(value).split("\n")))


_env = Environment(
    loader=FileSystemLoader(str(_COMPONENTS)),
    autoescape=select_autoescape(["html", "j2"], default_for_string=True),
    trim_blocks=False, lstrip_blocks=False,
)
_env.filters["md_inline"] = _md_inline
_env.filters["nl2br"] = _nl2br


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _embed_allowed(url: str) -> bool:
    h = _host(url)
    return any(h == a or h.endswith("." + a) for a in ALLOWED_EMBED_HOSTS)


_IFRAME_SRC = re.compile(r"""src\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_IFRAME_W = re.compile(r"""width\s*=\s*["']?(\d+)""", re.IGNORECASE)
_IFRAME_H = re.compile(r"""height\s*=\s*["']?(\d+)""", re.IGNORECASE)


def _parse_iframe(snippet: str) -> dict | None:
    """Pull src/width/height out of a pasted `<iframe …>` blob. We keep only those — the host
    allowlist and our own template decide the rest, so a copied snippet can't inject attributes or
    a script. Returns None when there is no usable src."""
    m = _IFRAME_SRC.search(snippet or "")
    if not m:
        return None
    out = {"url": m.group(1), "embed": True}
    w, h = _IFRAME_W.search(snippet), _IFRAME_H.search(snippet)
    if w:
        out["width"] = int(w.group(1))
    if h:
        out["height"] = int(h.group(1))
    return out


def _prep_examples(examples) -> list[dict]:
    """Normalise every example to {url, label, embed?, width?, height?}, whichever way it was
    written — structured fields *or* a pasted `iframe:` snippet — then downgrade any embed from a
    non-allowlisted host to a plain link, so a page never emits an iframe Canvas would strip."""
    out = []
    for e in examples or []:
        e = dict(e)
        if e.get("iframe"):
            parsed = _parse_iframe(e["iframe"])
            if not parsed:                      # a malformed snippet: drop it rather than emit junk
                continue
            label = e.get("label")
            e = dict(parsed)
            if label:
                e["label"] = label
        if not e.get("url"):
            continue
        if e.get("embed") and not _embed_allowed(e["url"]):
            e["embed"] = False
        out.append(e)
    return out


def _prep_images(images) -> list[dict]:
    """Accessibility gate: an image ships only with meaningful alt text (alt, else caption).
    We cannot invent alt for an instructor's image, so an image with neither is dropped rather
    than shipped inaccessible."""
    out = []
    for im in images or []:
        im = dict(im)
        if not im.get("url"):
            continue
        alt = im.get("alt") or im.get("caption")
        if not alt:
            continue
        im["alt"] = alt
        out.append(im)
    return out


def render_body(page, supplements: dict | None = None, style: dict | None = None) -> str:
    """The block sequence + merged supplements, as an HTML fragment (no <html>/<body> wrapper).

    `style` is a resolved theme (see style.load_style) — a full design identity whose tokens every
    component template draws its inline styles from. Resolved at render time, like supplements, so
    a theme change re-renders model-free and `page.json` stays neutral.
    """
    from coursekit.generate.page.style import load_style
    supplements = supplements or {}
    t = style or load_style(None)

    # Topic grouping: a heading opens a topic that runs until the next heading. The grouping is
    # already implicit in the block sequence, so framing it is purely a theme decision
    # (shape.section_frame: card) — no IR or model involvement.
    groups: list[list] = []
    current: list = []
    for b in page.blocks.values():
        if b.kind == "heading" and current:
            groups.append(current)
            current = []
        current.append(b)
    if current:
        groups.append(current)

    # The week's summary glossary lands at the very end, grouped with the last concept — but it isn't
    # specific to that concept. Peel a run of trailing glossary blocks off the last section into their
    # own standalone groups, so they render as clean framed "Key Terms" boxes rather than folding into
    # (and inheriting the frame of) the last concept. A glossary that sits mid-page, under a concept
    # with more sections after it, stays put and folds in.
    if groups and any(b.kind == "heading" for b in groups[-1]):
        tail = []
        while len(groups[-1]) > 1 and groups[-1][-1].kind == "glossary":
            tail.insert(0, groups[-1].pop())
        groups.extend([g] for g in tail)

    shape = t.get("shape") or {}
    color = t.get("color") or {}
    # Inline `code` renders as a self-contained chip in the theme's validated code_bg/code_fg pair, so
    # it stays legible on any ground (used by _md_inline). Fixes terminal's inline code going light on
    # the white panel gaps.
    global _INLINE_CODE_STYLE
    _c_bg = color.get("code_bg", color.get("surface") or "#f2f2f0")
    _c_fg = color.get("code_fg", color.get("ink") or "#111111")
    _mono = (t.get("type") or {}).get("mono_family", "ui-monospace, Menlo, monospace")
    _INLINE_CODE_STYLE = (f"background-color: {_c_bg}; color: {_c_fg}; "
                          f"font-family: {_mono}; padding: 1px 5px; border-radius: 3px;")
    # section_frame: none | card (a light card on the page) | panel (each section on the theme's
    # own surface colour, so a dark identity breaks into separate petrol panels with white gaps
    # between them, rather than one flowing slab).
    frame = shape.get("section_frame", "none")
    panels = frame == "panel"
    frame_roles = shape.get("frame_roles")     # themes may frame only certain section roles
    frame_style = shape.get("frame_style", "solid")
    surface = color.get("surface")
    unit = (t.get("space") or {}).get("unit", 8)
    radius = shape.get("radius", 0)
    gap = (t.get("space") or {}).get("section_gap", 40)
    border_w = shape.get("border_width", 1)

    def _panel(inner: str) -> str:
        bg = surface if panels else color.get("frame_bg", "#ffffff")
        border = color.get("frame_border", bg)
        return (f'<div style="background-color: {bg}; border: {border_w}px {frame_style} {border}; '
                f'border-radius: {radius}px; padding: {unit * 3}px; margin: 0 0 {gap}px 0;">\n'
                f'{inner}\n</div>')

    # A `review` section is a block-level Recap CONTAINER: a distinct box in the theme's border idiom
    # (terminal a linear petrol rule, plotter dashed, studio a hairline) holding one accordion per
    # recall question. A theme may give the recap its own ground + palette (terminal's light-mode
    # note), so the box has good contrast whether it sits on a light page or the dark panels' gaps.
    type_ = t.get("type") or {}
    heading_family = type_.get("heading_family", "sans-serif")
    body_family = type_.get("body_family", heading_family)
    heading_weight = type_.get("heading_weight", 700)
    review_glyph = ((t.get("glyphs") or {}).get("roles") or {}).get("review", "↺")
    recap_label = t.get("recap_label", "Recap")     # course-set in style.yaml; no assumed cadence
    recap_border = color.get("recap_border", color.get("frame_border", color.get("muted", "#cccccc")))
    r_ink = color.get("recap_ink", color.get("ink"))          # question text (dark on the recap ground)
    r_muted = color.get("recap_muted", color.get("muted"))    # answer text, receded but legible
    r_bg = color.get("recap_bg")                              # a distinct ground; None on light themes
    # the question is larger but only medium-weight (capped below a heavy theme heading, so it reads
    # as a prompt, not a shout; a light heading like studio's 400 is left as-is).
    q_weight = min(int(heading_weight), 500)
    # fallback (non-question) recap content renders in the recap palette so it stays legible on r_bg
    t_recap = dict(t)
    t_recap["color"] = {**color, "ink": r_ink, "muted": r_muted}

    def _recap_qa(question: str, answer_html: str) -> str:
        """One recall question, its own accordion. The QUESTION dominates — larger, medium weight,
        the recap's ink; the revealed answer recedes (smaller, muted). The native marker rotates."""
        return (
            f'<details style="border-top: 1px {frame_style} {recap_border}; '
            f'padding: {unit}px 0; margin: 0;">\n'
            f'<summary style="cursor: pointer; font-family: {heading_family}; '
            f'font-weight: {q_weight}; font-size: 18px; color: {r_ink};">{question}</summary>\n'
            f'<div style="color: {r_muted}; font-family: {body_family}; font-size: 15px; '
            f'line-height: 1.55; padding: {unit}px 0 0 {unit * 2}px;">{answer_html}</div>\n</details>')

    def _recap(title: str, body_blocks) -> str:
        """The block-level recap: a distinct bordered container with a header and one accordion per
        question. The header names the prior topic when the model supplies one — "Still Life Recap" —
        otherwise just the label. The container is NOT collapsible; it recedes by being quiet."""
        topic = (title or "").strip()
        label = (f"{topic} {recap_label}"
                 if topic and topic.lower() not in ("recap", "review", recap_label.lower())
                 else recap_label)
        header = (f'<div style="font-family: {heading_family}; font-weight: {heading_weight}; '
                  f'font-size: 17px; color: {r_ink}; margin: 0 0 {unit}px 0;">'
                  f'{review_glyph}&nbsp;&nbsp;{escape(label)}</div>')
        inner = []
        for b in body_blocks:
            if b.kind == "details":
                inner.append(_recap_qa(str(escape(b.summary)), _md_inline(b.text)))
            else:  # fallback if the model didn't phrase the recap as questions
                inner.append(_env.get_template(f"{b.kind}.html.j2").render(
                    b=b.model_dump(), t=t_recap, framed=False, frame_pad=0).strip())
        bg = f"background-color: {r_bg}; " if r_bg else ""
        return (f'<div style="{bg}border: 1px {frame_style} {recap_border}; '
                f'border-radius: {radius}px; padding: {unit * 2}px {unit * 3}px; '
                f'margin: 0 0 {gap}px 0;">\n{header}\n' + "\n".join(inner) + "\n</div>")

    parts = []
    for group in groups:
        is_heading = group[0].kind == "heading"
        role = getattr(group[0], "role", None) if is_heading else None

        if role == "review":
            # the review heading names the prior topic; its questions are the following details blocks
            parts.append(_recap(group[0].text, group[1:]))
            continue

        framed = frame in ("card", "panel") and is_heading
        if framed and frame_roles:
            # a role outside the theme's frame list stays flat; role-less headings keep the default
            framed = role is None or role in frame_roles
        # Dark-surface protection: on a theme whose panels ARE the surface (terminal's petrol),
        # a heading-less group (the opening hook paragraph, a standalone pullquote) would otherwise
        # render its light ink straight onto the white gap between panels — illegible. So give every
        # group its panel; the white gaps stay the margins between them, never a ground for light text.
        if not framed and panels and surface and surface.lower() not in ("#fff", "#ffffff"):
            framed = True
        # A glossary under a concept/example/practice/summary heading is specific to that topic, so
        # it FOLDS IN — just the labelled terms, no separate box. A standalone glossary — its own
        # section (a plain or "Key Terms" heading, or no heading) — keeps its full Key Terms frame.
        topic_section = is_heading and role in ("concept", "example", "practice", "summary")
        concept_name = group[0].text if topic_section else None
        rendered = [
            _env.get_template(f"{b.kind}.html.j2").render(
                b=b.model_dump(), t=t, framed=framed, frame_pad=unit * 3,
                nested=(b.kind == "glossary" and topic_section),
                concept=concept_name).strip()
            for b in group
        ]
        parts.append(_panel("\n".join(rendered)) if framed else "\n".join(rendered))

    supp = _env.get_template("supplements.html.j2").render(
        references=supplements.get("references") or [],
        examples=_prep_examples(supplements.get("examples")),
        images=_prep_images(supplements.get("images")),
        t=t,
    ).strip()
    if supp:
        # In panel mode the supplements are their own section, so they get their own panel — light
        # ink would be unreadable on the white page gap otherwise.
        parts.append(_panel(supp) if panels else supp)

    body = "\n".join(p for p in parts if p)

    # A surface theme that does NOT panel per-section gets one full-bleed ground instead.
    if surface and not panels and surface.lower() not in ("#fff", "#ffffff"):
        body = (f'<div style="background-color: {surface}; padding: {unit * 4}px; '
                f'border-radius: {radius}px;">\n{body}\n</div>')

    return body


def load_supplements(course_root, week_ref) -> dict:
    """A course's instructor-authored supplements for one page, or {} when absent. Never raises.

    Matched by **week identity, not an exact filename** — any `.vtconfig/pages/*.yaml` whose name
    resolves to the same week number wins, so `week-3.yaml`, `week-3-repetition.yaml`, and
    `week 3.yaml` all work. This is the same forgiving matching `courseconfig.week_key` gives
    everywhere else, so a faculty member never has to guess the tool's internal slug.
    """
    if not course_root:
        return {}
    d = Path(course_root) / ".vtconfig" / "pages"
    if not d.is_dir():
        return {}

    from coursekit.courseconfig import week_key
    target = week_key(week_ref)
    match = None
    for f in sorted(list(d.glob("*.yaml")) + list(d.glob("*.yml"))):
        if target is not None and week_key(f.stem) == target:
            match = f
            break
    if match is None:                                   # non-week pages: fall back to exact stem
        exact = d / f"{week_ref}.yaml"
        match = exact if exact.is_file() else None
    if match is None:
        return {}

    try:
        import yaml
        data = yaml.safe_load(match.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
