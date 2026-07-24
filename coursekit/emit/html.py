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


def render_document(page, supplements: dict | None = None, style: dict | None = None) -> str:
    return _DOC.format(title=escape(page.title), body=render_body(page, supplements, style))


def write_html(page, out_dir, supplements: dict | None = None, style: dict | None = None) -> Path:
    """Write `<slug>.html` beside the page's other artifacts. Returns the path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{page.slug}.html"
    path.write_text(render_document(page, supplements, style), encoding="utf-8")
    return path


def reemit(path) -> list[tuple[Path, Path]]:
    """Re-render every `page.json` under `path` to HTML — model-free.

    Reads each committed page, its course supplements, and the course's style (theme), all found by
    walking up to the `.vtconfig/` root, and rewrites `<slug>.html`. This is how you iterate on a
    supplements file or switch themes without paying for a model run.
    """
    from coursekit.courseconfig import find_root
    from coursekit.generate.page.page import Page
    from coursekit.generate.page.style import load_style

    out = []
    for pj in sorted(Path(path).rglob("page.json")):
        page = Page.model_validate_json(pj.read_text(encoding="utf-8"))
        root = find_root(pj)
        supplements = load_supplements(root, page.week_ref or page.slug)
        out.append((pj, write_html(page, pj.parent, supplements, load_style(root))))
    return out
