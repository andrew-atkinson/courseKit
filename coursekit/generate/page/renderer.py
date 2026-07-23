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


def _md_inline(value) -> Markup:
    """Escape, then apply inline Markdown (**bold**, *italic*, `code`). Escaping first means the
    Markdown markers act on safe text and a user's `<` is already `&lt;`."""
    s = str(escape(value))
    s = _BOLD.sub(r"<strong>\1</strong>", s)
    s = _ITAL.sub(r"<em>\1</em>", s)
    s = _CODE.sub(r"<code>\1</code>", s)
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

    shape = t.get("shape") or {}
    color = t.get("color") or {}
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

    parts = []
    for group in groups:
        framed = frame in ("card", "panel") and group[0].kind == "heading"
        if framed and frame_roles:
            role = getattr(group[0], "role", None)
            # a role outside the theme's frame list stays flat; role-less headings keep the default
            framed = role is None or role in frame_roles
        rendered = [
            _env.get_template(f"{b.kind}.html.j2").render(
                b=b.model_dump(), t=t, framed=framed, frame_pad=unit * 3).strip()
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
