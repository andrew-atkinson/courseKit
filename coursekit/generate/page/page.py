"""The page IR: the canonical, platform-neutral form of a course page.

Mirrors `bank.py` exactly in shape — a draft that owns the artifact being built, autosave after every
write, per-type builders, guardrails written as steering — because a generator is the quiz pattern with
a different IR. A page is an ordered set of typed **blocks**; the renderer turns blocks into Canvas-safe HTML,
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
import os
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
    # Semantic section identity — what KIND of section this opens. The model assigns meaning;
    # the theme decides its visual (glyph, framing). Never a style, always a meaning.
    role: Literal["review", "concept", "practice", "example", "summary"] | None = None

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


# ---- pedagogy devices: each maps to a documented learning function (see docs/design.md) ----

class Column(BaseModel):
    """One column of a comparison."""
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    items: list[str] = Field(min_length=1)

    _nourl_title = field_validator("title")(staticmethod(_check_no_url))

    @field_validator("items")
    @classmethod
    def _items_ok(cls, v: list[str]) -> list[str]:
        cleaned = [i.strip() for i in v if i and i.strip()]
        if not cleaned:
            raise ValueError("a column needs at least one non-empty item")
        for item in cleaned:
            _check_no_url(item)
        return cleaned


class ColumnsBlock(_Block):
    """Side-by-side comparison — CLT: managing element interactivity, 'wrong way / right way'."""
    kind: Literal["columns"] = "columns"
    columns: list[Column] = Field(min_length=2, max_length=3)


class PullquoteBlock(_Block):
    """The week's single key idea, foregrounded — CLT: signalling."""
    kind: Literal["pullquote"] = "pullquote"
    text: str = Field(min_length=1)
    attribution: str | None = None

    _nourl = field_validator("text")(staticmethod(_check_no_url))

    @field_validator("attribution")
    @classmethod
    def _attr_ok(cls, v):
        return _check_no_url(v) if v else v


class CardBlock(_Block):
    """A titled, self-contained unit whose type is visible — UDL: representation; CLT: cutting the
    'what am I reading?' load. `card_kind` names the content type, not a style."""
    kind: Literal["card"] = "card"
    card_kind: Literal["concept", "example", "takeaway"] = "concept"
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)

    _nourl_title = field_validator("title")(staticmethod(_check_no_url))
    _nourl_text = field_validator("text")(staticmethod(_check_no_url))


class DetailsBlock(_Block):
    """Progressive disclosure — 'predict before you reveal', optional depth. Native <details>, no JS."""
    kind: Literal["details"] = "details"
    summary: str = Field(min_length=1)   # the always-visible prompt
    text: str = Field(min_length=1)      # the revealed content (markdown)

    _nourl_summary = field_validator("summary")(staticmethod(_check_no_url))
    _nourl_text = field_validator("text")(staticmethod(_check_no_url))


class ImageBlock(_Block):
    """A visual placed inline where it teaches — a diagram, an example work, a chart. The model places
    the SLOT (a `ref` + real alt text) but NEVER a URL: an image URL is exactly what a model fabricates,
    so the instructor supplies the actual file in the supplements and the renderer resolves it by `ref`
    at render time (the two-author split; the no-fabricated-URLs guardrail made structural). UDL:
    multiple means of representation. `alt` is required — an image ships accessible or not at all."""
    kind: Literal["image"] = "image"
    ref: str = Field(min_length=1)          # the key the instructor's supplements maps to a file
    alt: str = Field(min_length=1)          # WCAG — what the image shows / what belongs here
    caption: str | None = None

    _nourl_ref = field_validator("ref")(staticmethod(_check_no_url))
    _nourl_alt = field_validator("alt")(staticmethod(_check_no_url))

    @field_validator("caption")
    @classmethod
    def _cap_ok(cls, v):
        return _check_no_url(v) if v else v


Block = Union[HeadingBlock, ParagraphBlock, BulletsBlock, CodeBlock, GlossaryBlock, CalloutBlock,
              ColumnsBlock, PullquoteBlock, CardBlock, DetailsBlock, ImageBlock]

_KINDS: dict[str, type[_Block]] = {
    "heading": HeadingBlock,
    "paragraph": ParagraphBlock,
    "bullets": BulletsBlock,
    "code": CodeBlock,
    "glossary": GlossaryBlock,
    "callout": CalloutBlock,
    "columns": ColumnsBlock,
    "pullquote": PullquoteBlock,
    "card": CardBlock,
    "details": DetailsBlock,
    "image": ImageBlock,
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


def build_block(kind: str, **kwargs) -> Block:
    """Construct a typed block, raising pydantic ValidationError on bad input (the tools layer
    turns that into an actionable message for the model)."""
    if kind not in _KINDS:
        raise ValueError(f"unknown block kind '{kind}'. Use one of: {', '.join(_KINDS)}")
    return _KINDS[kind](**kwargs)


# Page FUNCTIONS whose job is reference/orientation, not a teaching arc — they carry no retrieval
# foldout (see the retrieval check below). The teaching page (`week_intro`) is deliberately absent.
_REFERENCE_PAGE_TYPES = {"glossary", "week_overview", "module_overview", "week_recap", "reference"}


class PageDraft:
    """A page being built, and where it saves. `new` starts empty and stages to `page.partial.json`, so a
    re-run that fails leaves the last good `page.json` untouched; `adopt` takes an existing page for
    editing (the targeted-fix pass reloads a `page.json`, then a `put_block` overwrites just the flagged
    block), and saves in place."""

    def __init__(self, page: Page, out_dir: Path | None = None, *, staged: bool = False):
        self.page = page
        self.out_dir = Path(out_dir) if out_dir else None
        self.staged = staged

    @classmethod
    def new(cls, page_id: str, out_dir: Path | None = None, *, title: str = "Untitled page",
            page_type: str = "week_intro", week_ref: str | None = None, slug: str = "page") -> "PageDraft":
        return cls(Page(page_id=page_id, title=title, page_type=page_type, week_ref=week_ref, slug=slug),
                   out_dir, staged=True)

    @classmethod
    def adopt(cls, page: Page, out_dir: Path | None = None) -> "PageDraft":
        return cls(page, out_dir)

    def is_finalized(self) -> bool:
        return self.page.finalized

    def _autosave(self) -> None:
        """Persist after every write, exactly as bank.py does — a crash mid-build loses nothing, and a
        staged build reaches `page.json` (atomically) only once finalized."""
        if self.out_dir is None:
            return
        self.out_dir.mkdir(parents=True, exist_ok=True)
        partial = self.out_dir / "page.partial.json"
        partial.write_text(json.dumps(self.page.model_dump(), indent=2), encoding="utf-8")
        if self.page.finalized or not self.staged:
            os.replace(partial, self.out_dir / "page.json")

    def put_block(self, block: Block) -> str:
        """Store a block, REPLACING any block already at block_id (revision without pile-up)."""
        replacing = block.block_id in self.page.blocks
        self.page.blocks[block.block_id] = block
        self._autosave()
        verb = "replaced" if replacing else "added"
        return (f"OK {verb} block '{block.block_id}' ({block.kind}). "
                f"Page now has {len(self.page.blocks)} block(s).")

    def report(self) -> str:
        if not self.page.blocks:
            return "Page is empty."
        lines = [f"Page '{self.page.title}' ({self.page.page_type}) — {len(self.page.blocks)} block(s):"]
        for bid, b in self.page.blocks.items():
            lines.append(f"  [{bid}] {b.kind}")
        return "\n".join(lines)

    def validate_final(self) -> list[str]:
        """Reasons the page is not ready. Empty list means finalizable."""
        problems = []
        if not self.page.blocks:
            problems.append("the page has no blocks")
        # A teaching page needs a heading to structure it; a reference page (a glossary companion, an
        # overview) is self-structuring — its glossary/overview block carries its own label — so a
        # redundant heading is not required (and would just repeat the block's label).
        if self.page.page_type not in _REFERENCE_PAGE_TYPES and \
                not any(b.kind == "heading" for b in self.page.blocks.values()):
            problems.append("the page has no heading block to structure it")
        # A page must ask the student to RETRIEVE — the testing effect is core pedagogy, and this device
        # is the first to get dropped as the prompt grows. So gate it structurally (unlike the hook /
        # pullquote / summary, which stay prompt-guidance): at least one predict/recall `details` foldout —
        # the recap's recall questions or the closing "Predict: …" prompt both count.
        # PROVISIONAL (2026-07-31): this is really a stopgap for local-model ATTENTION crowding, not a
        # universal pedagogical invariant — retrieval isn't right for every page type (a pure reference or
        # intro page), and forcing it can yield a hollow foldout. A candidate for removal / making it
        # page-type-aware once composable generation manages attention properly (see roadmap "Composable
        # generation"). NOW page-type-aware (2026-08-06): a page whose FUNCTION is reference/orientation
        # (a glossary companion, a week/module overview) has no teaching arc to retrieve from, so the
        # foldout is skipped for those types; a teaching page still requires it.
        if self.page.page_type not in _REFERENCE_PAGE_TYPES and \
                not any(b.kind == "details" for b in self.page.blocks.values()):
            problems.append("the page has no retrieval prompt — add a predict/recall `details` block "
                            "(the closing 'Predict: …' or the recap's questions) so students retrieve "
                            "before they leave")
        # A heading introduces the blocks beneath it, and the renderer runs a section from one heading to
        # the next — so a heading with no content before the next heading (or the page end) renders as an
        # empty titled panel while its content piles into the previous section. This happens when the model
        # writes all the prose first and appends the section headings last (a crowding failure). It is
        # unambiguously broken structure, so refuse to finalize it — deterministically, because the critics
        # read block text and never SEE the page.
        ordered = list(self.page.blocks.values())
        empty = [b for i, b in enumerate(ordered) if b.kind == "heading"
                 and (i + 1 == len(ordered) or ordered[i + 1].kind == "heading")]
        if empty:
            problems.append(
                f"{len(empty)} heading(s) have no content under them ({', '.join(b.text for b in empty)}) — "
                "every heading must be immediately followed by the blocks it introduces, before the next "
                "heading; place each section heading directly above its own content, not all at the end")
        return problems

    def finalize(self) -> str:
        problems = self.validate_final()
        if problems:
            return "ERROR: cannot finalize — " + "; ".join(problems)
        self.page.finalized = True
        self._autosave()
        return f"OK page finalized with {len(self.page.blocks)} block(s)."
