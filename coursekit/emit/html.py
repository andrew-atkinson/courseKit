"""Standalone HTML emitter for pages.

The simplest page target: a reviewable `.html` file, no packaging, works anywhere. It wraps the
rendered block body (from the page renderer) in a minimal document with light styling for reading.
The same rendered body feeds the Common Cartridge emitter and, later, the Canvas API — this one just
wraps it for a browser.
"""

from pathlib import Path

from markupsafe import escape

from coursekit.generate.page.renderer import load_supplements, render_body

_DOC = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; line-height: 1.6;
         max-width: 44rem; margin: 2rem auto; padding: 0 1rem; color: #16211f; }}
  h1 {{ font-size: 1.6rem; }} h4 {{ margin-top: 1.6rem; }}
  pre {{ background: #f2f4f3; padding: .75rem 1rem; border-radius: 4px; overflow-x: auto; }}
  code {{ background: #f2f4f3; padding: .1em .35em; border-radius: 3px; }}
  iframe {{ max-width: 100%; border: 1px solid #d8e0dd; border-radius: 4px; }}
  a {{ color: #0e6b59; }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
</body>
</html>
"""


def render_document(page, supplements: dict | None = None) -> str:
    return _DOC.format(title=escape(page.title), body=render_body(page, supplements))


def write_html(page, out_dir, supplements: dict | None = None) -> Path:
    """Write `<slug>.html` beside the page's other artifacts. Returns the path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{page.slug}.html"
    path.write_text(render_document(page, supplements), encoding="utf-8")
    return path
