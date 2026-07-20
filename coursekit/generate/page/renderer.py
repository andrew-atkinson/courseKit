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


def _prep_examples(examples) -> list[dict]:
    """An example asking to embed from a non-allowlisted host degrades to a link, so a page never
    emits an iframe Canvas would strip."""
    out = []
    for e in examples or []:
        e = dict(e)
        if e.get("embed") and not _embed_allowed(e.get("url", "")):
            e["embed"] = False
        out.append(e)
    return out


def render_body(page, supplements: dict | None = None) -> str:
    """The block sequence + merged supplements, as an HTML fragment (no <html>/<body> wrapper)."""
    supplements = supplements or {}
    parts = []
    for b in page.blocks.values():
        tmpl = _env.get_template(f"{b.kind}.html.j2")
        parts.append(tmpl.render(b=b.model_dump()).strip())

    supp = _env.get_template("supplements.html.j2").render(
        references=supplements.get("references") or [],
        examples=_prep_examples(supplements.get("examples")),
    ).strip()
    if supp:
        parts.append(supp)

    return "\n".join(p for p in parts if p)


def load_supplements(course_root, slug: str) -> dict:
    """A course's instructor-authored supplements for one page, or {} when absent. Never raises."""
    if not course_root:
        return {}
    path = Path(course_root) / ".vtconfig" / "pages" / f"{slug}.yaml"
    if not path.is_file():
        return {}
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
