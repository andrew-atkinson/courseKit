"""Pages as cartridge items — `page.json` → `WikiPage` module items.

Reuses the page emitter (`cc.render_page` / `cc.page_resource`) verbatim, so a page in the course
cartridge is byte-identical to one in a pages-only `.imscc`.
"""

from pathlib import Path

from coursekit.courseconfig import find_root, week_key
from coursekit.emit import cc
from coursekit.emit.cartridge import CartridgeItem


class PagesSource:
    content_type = "WikiPage"

    def collect(self, course_path) -> list[CartridgeItem]:
        from coursekit.generate.page.page import Page
        from coursekit.generate.page.renderer import load_supplements
        from coursekit.generate.page.style import load_style

        p = Path(course_path)
        jsons = [p] if (p.is_file() and p.name == "page.json") else sorted(p.rglob("page.json"))
        items = []
        for pj in jsons:
            page = Page.model_validate_json(pj.read_text(encoding="utf-8"))
            root = find_root(pj)
            supp = load_supplements(root, page.week_ref or page.slug)
            style = load_style(root)
            wk = week_key(page.week_ref) if page.week_ref else None
            if wk is None:
                wk = week_key(pj.parent.name)
            items.append(CartridgeItem(
                week_key=wk,
                content_type="WikiPage",
                title=page.title,
                resource_id=cc.page_ident(page),
                item_id=cc.item_ident(page),
                resource_xml=cc.page_resource(page),
                files={f"wiki_content/{page.slug}.html": cc.render_page(page, supp, style)},
                rank=0,   # pages come before quizzes in a week's module
            ))
        return items
