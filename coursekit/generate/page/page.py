"""The page IR: the canonical, platform-neutral form of a course page.

Mirrors `bank.py` exactly in shape — a module-level singleton, autosave after every write, per-type
builders, guardrails written as steering — because a generator is the quiz pattern with a different
IR. A page is an ordered set of typed **blocks**; the renderer turns blocks into Canvas-safe HTML,
and platform emitters wrap that HTML.

Two rules are load-bearing:

- **Blocks are keyed by `block_id`**, so re-adding one overwrites in place (the same overwrite
  mechanism that stops the quiz generator's drafts from piling up), while new ids append in order.
- **Model-authored blocks carry no URLs.** Every link and embed on a page enters through the
  course's supplements file at render time, never through the model — a model asked for "a reference"
  fabricates plausible-but-fake URLs. The block validators reject a URL in any prose field, and the
  tools expose no URL parameter at all. Code blocks are exempt: a URL inside code is literal text,
  not a link.
"""

import json
import re
from pathlib import Path
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

__all__ = ["ValidationError"]

# http(s):// or bare www. or a markdown link target — any of these in model prose is a fabricated
# link risk. Kept deliberately broad; the sanctioned channel for links is the supplements file.
_URL_RE = re.compile(r"https?://|www\.|\]\(", re.IGNORECASE)


def _check_no_url(text: str) -> str:
    if _URL_RE.search(text or ""):
        raise ValueError(
            "links are not allowed in generated page text — a page's references, examples, and "
            "embeds come from the course's supplements file, not the model. Remove the URL."
        )
    return text


class _Block(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: str = Field(min_length=1)


class HeadingBlock(_Block):
    kind: Literal["heading"] = "heading"
    text: str = Field(min_length=1)
    level: int = Field(default=2, ge=1, le=4)

    _nourl = field_validator("text")(staticmethod(_check_no_url))


class ParagraphBlock(_Block):
    kind: Literal["paragraph"] = "paragraph"
    text: str = Field(min_length=1)  # markdown prose

    _nourl = field_validator("text")(staticmethod(_check_no_url))


class BulletsBlock(_Block):
    kind: Literal["bullets"] = "bullets"
    items: list[str] = Field(min_length=1)

    @field_validator("items")
    @classmethod
    def _items_ok(cls, v: list[str]) -> list[str]:
        cleaned = [i.strip() for i in v if i and i.strip()]
        if not cleaned:
            raise ValueError("a bullets block needs at least one non-empty item")
        for item in cleaned:
            _check_no_url(item)
        return cleaned


class CodeBlock(_Block):
    kind: Literal["code"] = "code"
    code: str = Field(min_length=1)
    language: str = ""   # a hint for rendering; not validated for URLs (code is literal)


class GlossaryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    term: str = Field(min_length=1)
    definition: str = Field(min_length=1)

    @field_validator("term", "definition")
    @classmethod
    def _nourl(cls, v: str) -> str:
        return _check_no_url(v)


class GlossaryBlock(_Block):
    kind: Literal["glossary"] = "glossary"
    entries: list[GlossaryEntry] = Field(min_length=1)


class CalloutBlock(_Block):
    kind: Literal["callout"] = "callout"
    text: str = Field(min_length=1)
    tone: Literal["note", "tip", "warning"] = "note"

    _nourl = field_validator("text")(staticmethod(_check_no_url))


Block = Union[HeadingBlock, ParagraphBlock, BulletsBlock, CodeBlock, GlossaryBlock, CalloutBlock]

_KINDS: dict[str, type[_Block]] = {
    "heading": HeadingBlock,
    "paragraph": ParagraphBlock,
    "bullets": BulletsBlock,
    "code": CodeBlock,
    "glossary": GlossaryBlock,
    "callout": CalloutBlock,
}


class Page(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_id: str
    page_type: str = "week_intro"
    title: str = "Untitled page"
    week_ref: str | None = None
    slug: str = "page"
    blocks: dict[str, Block] = Field(default_factory=dict)
    finalized: bool = False


# ---- module state (mirrors bank.py) ----

_page = Page(page_id="unsaved")
_out_dir: Path | None = None


def init(page_id: str, out_dir: Path | None = None, *, title: str = "Untitled page",
         page_type: str = "week_intro", week_ref: str | None = None, slug: str = "page") -> None:
    global _page, _out_dir
    _page = Page(page_id=page_id, title=title, page_type=page_type, week_ref=week_ref, slug=slug)
    _out_dir = Path(out_dir) if out_dir else None


def reset() -> None:
    """Test hook."""
    init("test", None)


def get() -> Page:
    return _page


def is_finalized() -> bool:
    return _page.finalized


def _autosave() -> None:
    """Persist after every write, exactly as bank.py does — a crash mid-build loses nothing."""
    if _out_dir is None:
        return
    _out_dir.mkdir(parents=True, exist_ok=True)
    (_out_dir / "page.json").write_text(
        json.dumps(_page.model_dump(), indent=2), encoding="utf-8"
    )


def build_block(kind: str, **kwargs) -> Block:
    """Construct a typed block, raising pydantic ValidationError on bad input (the tools layer
    turns that into an actionable message for the model)."""
    if kind not in _KINDS:
        raise ValueError(f"unknown block kind '{kind}'. Use one of: {', '.join(_KINDS)}")
    return _KINDS[kind](**kwargs)


def put_block(block: Block) -> str:
    """Store a block, REPLACING any block already at block_id (revision without pile-up)."""
    replacing = block.block_id in _page.blocks
    _page.blocks[block.block_id] = block
    _autosave()
    verb = "replaced" if replacing else "added"
    return (f"OK {verb} block '{block.block_id}' ({block.kind}). "
            f"Page now has {len(_page.blocks)} block(s).")


def report() -> str:
    if not _page.blocks:
        return "Page is empty."
    lines = [f"Page '{_page.title}' ({_page.page_type}) — {len(_page.blocks)} block(s):"]
    for bid, b in _page.blocks.items():
        lines.append(f"  [{bid}] {b.kind}")
    return "\n".join(lines)


def validate_final() -> list[str]:
    """Reasons the page is not ready. Empty list means finalizable."""
    problems = []
    if not _page.blocks:
        problems.append("the page has no blocks")
    if not any(b.kind == "heading" for b in _page.blocks.values()):
        problems.append("the page has no heading block to structure it")
    return problems


def finalize() -> str:
    problems = validate_final()
    if problems:
        return "ERROR: cannot finalize — " + "; ".join(problems)
    _page.finalized = True
    _autosave()
    return f"OK page finalized with {len(_page.blocks)} block(s)."
