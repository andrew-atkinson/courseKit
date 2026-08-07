"""Shared block vocabulary (COMP-2) — the content-type-neutral import point for the typed components
every PROSE content type composes from (pages today; discussions, assignments, overviews next).

The pedagogic metadata for these components lives in `coursekit/generate/catalog.py`. The class
DEFINITIONS currently live with their first consumer, the page IR (`generate/page/page.py`), and are
re-exported here. This module is the stable interface: a second content type imports its blocks from
HERE, and when one lands the definitions relocate into this module behind the same names — with no
change to any consumer (the project's "extract at the second consumer, not speculatively" rule; the
same discipline as the quizbot→coursekit rename trigger).

So: compose from `coursekit.generate.blocks`, describe from `coursekit.generate.catalog`.
"""

from coursekit.generate.page.page import (  # noqa: F401  — re-export: the shared vocabulary
    Block,
    _Block,
    _KINDS,
    build_block,
    _check_no_url,
    HeadingBlock,
    ParagraphBlock,
    BulletsBlock,
    CodeBlock,
    GlossaryEntry,
    GlossaryBlock,
    CalloutBlock,
    Column,
    ColumnsBlock,
    PullquoteBlock,
    CardBlock,
    DetailsBlock,
    ImageBlock,
)
