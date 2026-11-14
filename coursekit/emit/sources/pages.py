"""Pages as cartridge items — `page.json` → `WikiPage` module items.

Reuses the page emitter (`cc.render_page` / `cc.page_resource`) verbatim, so a page in the course
cartridge is byte-identical to one in a pages-only `.imscc`.
"""

from coursekit.course import artifact_units, ir_files
from coursekit.courseconfig import find_root
from coursekit.emit import cc
from coursekit.emit.cartridge import CartridgeItem


class PagesSource:
    content_type = "WikiPage"

    def collect(self, course_path) -> list[CartridgeItem]:
        from coursekit.generate.page.page import Page
        from coursekit.generate.page.renderer import load_supplements
        from coursekit.generate.page.style import load_style

        items = []
        units = artifact_units(course_path)
        for pj in ir_files(course_path, "page"):
            page = Page.model_validate_json(pj.read_text(encoding="utf-8"))
            root = find_root(pj)
            supp = load_supplements(root, page.unit_ref or page.slug)
            style = load_style(root)
            items.append(CartridgeItem(
                unit=units.get(pj),
                content_type="WikiPage",
                title=page.title,
                resource_id=cc.page_ident(page),
                item_id=cc.item_ident(page),
                resource_xml=cc.page_resource(page),
                files={f"wiki_content/{page.slug}.html": cc.render_page(page, supp, style)},
                rank=0,   # pages come before quizzes in a unit's module
                source=pj,
            ))
        return items
