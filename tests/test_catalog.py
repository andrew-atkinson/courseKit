"""The component catalog (COMP-1) + its drift guards.

The catalog is the single source of truth for what components exist and what each is FOR. These
tests keep it honest: it must stay in lockstep with the actual block kinds, every function it cites
must be defined, and the generated `docs/components.md` (COMP-4) must not drift from the code.
"""

from pathlib import Path

from coursekit.generate import blocks, catalog
from coursekit.generate.page import page as pageir


def test_catalog_covers_every_block_kind_exactly():
    # The load-bearing guard: a block added to the vocabulary without a catalog entry (or vice versa)
    # fails. Keyed to the shared `blocks` module (COMP-2), the content-type-neutral import point.
    assert set(catalog.CATALOG) == set(blocks._KINDS)


def test_blocks_module_re_exports_the_page_vocabulary():
    # COMP-2: the shared import point exposes the same vocabulary the page IR defines today.
    assert blocks._KINDS is pageir._KINDS
    assert blocks.build_block is pageir.build_block


# ---- content-type governance (COMP-2) ----

def test_page_palette_is_the_whole_catalog_today():
    palette = {c.kind for c in catalog.components_for("page")}
    assert palette == set(catalog.CATALOG)                 # every component is a page component (for now)


def test_allows_and_unknown_components():
    assert catalog.allows("page", "heading")
    assert not catalog.allows("page", "no-such-kind")
    assert not catalog.allows("discussion", "heading")    # an undeclared content type has no palette
    assert catalog.unknown_components("page", ["heading", "code"]) == []
    assert catalog.unknown_components("page", ["heading", "bogus"]) == ["bogus"]


def test_content_types_registry_has_page():
    assert "page" in catalog.CONTENT_TYPES


def test_every_component_serves_a_known_function():
    for c in catalog.CATALOG.values():
        assert c.functions, f"{c.kind} serves no pedagogic function (design that serves none doesn't ship)"
        unknown = set(c.functions) - set(catalog.FUNCTIONS)
        assert not unknown, f"{c.kind} cites undefined function(s): {unknown}"


def test_kind_field_matches_the_registry_key():
    for key, c in catalog.CATALOG.items():
        assert c.kind == key


def test_every_component_is_usable_on_a_page_today():
    # content_types is the COMP-2 seam; every current component is a page block.
    for c in catalog.CATALOG.values():
        assert "page" in c.content_types


def test_functions_vocabulary_may_lead_the_components():
    # A named function with no component yet is a GAP signal, not an error — assert the vocabulary is
    # a superset of what's used, so this stays a deliberate design space, not an accident.
    used = {f for c in catalog.CATALOG.values() for f in c.functions}
    assert used <= set(catalog.FUNCTIONS)


def test_docs_components_md_is_generated_and_fresh():
    # COMP-4: the doc is rendered from the catalog. If this fails, run:
    #   python -m coursekit.generate.catalog
    doc = (Path(catalog._repo_root()) / catalog.DOC_PATH).read_text(encoding="utf-8")
    assert doc == catalog.render_markdown(), "docs/components.md is stale — regenerate it from the catalog"
