"""Tools the model calls to build a page.

A tool call is the only way a block enters the page; prose is scratch. Mirrors the quiz tools:
hand-written schemas (the descriptions are prompt engineering for a small local model), pydantic
behind the function, dispatch that never raises.

**No tool accepts a URL.** Links, embeds, and example works come from the course's supplements file
at render time — never from the model. This is the facticity guardrail made structural: the model
*cannot* emit a link because no parameter takes one, and the page IR rejects one that sneaks into
prose.
"""

from pathlib import Path

from coursekit.generate import dispatch
from coursekit.generate.page import page

_call_log: Path | None = None


def set_call_log(path: Path | None) -> None:
    global _call_log
    _call_log = Path(path) if path else None


def reset_state() -> None:
    """Reset tool-local state only. The page IR is reset by page.init(), exactly as the quiz
    tools leave bank.init() to own the bank — so this must NOT clobber the out_dir a caller
    just set on the page."""
    set_call_log(None)


# ------------------------------------------------------------- block tools

def add_heading(block_id: str, text: str, level: int = 2, role: str = "") -> str:
    return page.put_block(page.build_block("heading", block_id=block_id, text=text, level=level,
                                           role=role or None))


def add_paragraph(block_id: str, text: str) -> str:
    return page.put_block(page.build_block("paragraph", block_id=block_id, text=text))


def add_bullets(block_id: str, items: list[str]) -> str:
    return page.put_block(page.build_block("bullets", block_id=block_id, items=items))


def add_code(block_id: str, code: str = "", language: str = "", text: str = "") -> str:
    # `text` is a lenient alias: the model sometimes sends the code under `text` (the arg name it uses
    # for prose blocks). Silently dropping a rejected code block is how a section ends up all bullets and
    # no nuts-and-bolts, so accept either.
    return page.put_block(page.build_block("code", block_id=block_id, code=code or text, language=language))


def add_glossary(block_id: str, entries: list[dict]) -> str:
    return page.put_block(page.build_block("glossary", block_id=block_id, entries=entries))


def add_callout(block_id: str, text: str, tone: str = "note") -> str:
    return page.put_block(page.build_block("callout", block_id=block_id, text=text, tone=tone))


def add_columns(block_id: str, columns: list[dict]) -> str:
    return page.put_block(page.build_block("columns", block_id=block_id, columns=columns))


def add_pullquote(block_id: str, text: str, attribution: str = "") -> str:
    return page.put_block(page.build_block("pullquote", block_id=block_id, text=text,
                                           attribution=attribution or None))


def add_card(block_id: str, title: str, text: str, card_kind: str = "concept") -> str:
    return page.put_block(page.build_block("card", block_id=block_id, title=title, text=text,
                                           card_kind=card_kind))


def add_details(block_id: str, summary: str, text: str) -> str:
    return page.put_block(page.build_block("details", block_id=block_id, summary=summary, text=text))


def get_page_report() -> str:
    return page.report()


def finalize_page() -> str:
    return page.finalize()


# ------------------------------------------------------------- schemas

_ID = {"type": "string",
       "description": "a short stable id for this block (e.g. 'review', 'loops'); reusing an id "
                      "replaces that block, so you can revise without starting over"}

add_heading_json = {
    "name": "add_heading",
    "description": "Add a section heading — the page's structure (e.g. REVIEW, FUNDAMENTALS, EXAMPLES).",
    "parameters": {"type": "object", "properties": {
        "block_id": _ID,
        "text": {"type": "string", "description": "the heading text"},
        "level": {"type": "integer", "description": "2, 3 or 4 (section depth); default 2"},
        "role": {"type": "string", "enum": ["review", "concept", "practice", "example", "summary"],
                 "description": "what kind of section this opens — lets students scan the page "
                                "by section type (optional)"},
    }, "required": ["block_id", "text"], "additionalProperties": False},
}

add_paragraph_json = {
    "name": "add_paragraph",
    "description": ("Add a paragraph of prose (Markdown). Do NOT include links or URLs — references "
                    "and examples come from the course, not from you."),
    "parameters": {"type": "object", "properties": {
        "block_id": _ID,
        "text": {"type": "string", "description": "the paragraph, in Markdown, with no links"},
    }, "required": ["block_id", "text"], "additionalProperties": False},
}

add_bullets_json = {
    "name": "add_bullets",
    "description": "Add a bulleted list of concepts or key points. No links in items.",
    "parameters": {"type": "object", "properties": {
        "block_id": _ID,
        "items": {"type": "array", "items": {"type": "string"},
                  "description": "the bullet points, each a short phrase"},
    }, "required": ["block_id", "items"], "additionalProperties": False},
}

add_code_json = {
    "name": "add_code",
    "description": "Add a fenced code example (shown verbatim). Code may contain anything.",
    "parameters": {"type": "object", "properties": {
        "block_id": _ID,
        "code": {"type": "string", "description": "the code, exactly as it should appear"},
        "language": {"type": "string", "description": "language hint, e.g. 'js' (optional)"},
        "text": {"type": "string", "description": "accepted as an alias for `code`; prefer `code`"},
    }, "required": ["block_id"], "additionalProperties": False},
}

add_glossary_json = {
    "name": "add_glossary",
    "description": "Add a short glossary — key terms and their definitions from this week.",
    "parameters": {"type": "object", "properties": {
        "block_id": _ID,
        "entries": {"type": "array", "items": {
            "type": "object", "properties": {
                "term": {"type": "string"},
                "definition": {"type": "string"},
            }, "required": ["term", "definition"], "additionalProperties": False,
        }, "description": "term/definition pairs, no links"},
    }, "required": ["block_id", "entries"], "additionalProperties": False},
}

add_callout_json = {
    "name": "add_callout",
    "description": "Add a highlighted note, tip, or warning (e.g. a common pitfall).",
    "parameters": {"type": "object", "properties": {
        "block_id": _ID,
        "text": {"type": "string", "description": "the note text, no links"},
        "tone": {"type": "string", "enum": ["note", "tip", "warning"],
                 "description": "note (default), tip, or warning"},
    }, "required": ["block_id", "text"], "additionalProperties": False},
}

add_columns_json = {
    "name": "add_columns",
    "description": ("Two or three columns side by side — use this to COMPARE things: two approaches, "
                    "before/after, correct vs incorrect. No links."),
    "parameters": {"type": "object", "properties": {
        "block_id": _ID,
        "columns": {"type": "array", "minItems": 2, "maxItems": 3, "items": {
            "type": "object", "properties": {
                "title": {"type": "string", "description": "the column heading"},
                "items": {"type": "array", "items": {"type": "string"},
                          "description": "the points in this column"},
            }, "required": ["title", "items"], "additionalProperties": False,
        }, "description": "2–3 columns to compare"},
    }, "required": ["block_id", "columns"], "additionalProperties": False},
}

add_pullquote_json = {
    "name": "add_pullquote",
    "description": ("Foreground the week's ONE key idea as a large pull quote. Use at most once per "
                    "page — it only signals if it is rare. No links."),
    "parameters": {"type": "object", "properties": {
        "block_id": _ID,
        "text": {"type": "string", "description": "the key idea, one or two sentences"},
        "attribution": {"type": "string", "description": "optional source (a person, a text)"},
    }, "required": ["block_id", "text"], "additionalProperties": False},
}

add_card_json = {
    "name": "add_card",
    "description": ("A titled, self-contained box whose TYPE is visible — for a worked example, a "
                    "single concept, or a key takeaway a student should be able to point to. No links."),
    "parameters": {"type": "object", "properties": {
        "block_id": _ID,
        "title": {"type": "string", "description": "the card's title"},
        "text": {"type": "string", "description": "the card's content (Markdown, no links)"},
        "card_kind": {"type": "string", "enum": ["concept", "example", "takeaway"],
                      "description": "what kind of content this card holds"},
    }, "required": ["block_id", "title", "text"], "additionalProperties": False},
}

add_details_json = {
    "name": "add_details",
    "description": ("A collapsible block: a visible prompt (summary) with content hidden until the "
                    "student expands it. Use for 'predict before you reveal', an answer to a "
                    "question, or optional depth. No links."),
    "parameters": {"type": "object", "properties": {
        "block_id": _ID,
        "summary": {"type": "string", "description": "the always-visible prompt/question"},
        "text": {"type": "string", "description": "the revealed content (Markdown, no links)"},
    }, "required": ["block_id", "summary", "text"], "additionalProperties": False},
}

get_page_report_json = {
    "name": "get_page_report",
    "description": "List the blocks recorded so far. Call this when you think the page is done.",
    "parameters": {"type": "object", "properties": {}, "required": [],
                   "additionalProperties": False},
}

finalize_page_json = {
    "name": "finalize_page",
    "description": ("Check the page and write it out. Call this last. If it reports problems, fix "
                    "them with more add_ calls and call it again."),
    "parameters": {"type": "object", "properties": {}, "required": [],
                   "additionalProperties": False},
}


# ------------------------------------------------------------- dispatch

TOOL_REGISTRY = {
    "add_heading": add_heading,
    "add_paragraph": add_paragraph,
    "add_bullets": add_bullets,
    "add_code": add_code,
    "add_glossary": add_glossary,
    "add_callout": add_callout,
    "add_columns": add_columns,
    "add_pullquote": add_pullquote,
    "add_card": add_card,
    "add_details": add_details,
    "get_page_report": get_page_report,
    "finalize_page": finalize_page,
}

_SCHEMAS = {
    "add_heading": add_heading_json,
    "add_paragraph": add_paragraph_json,
    "add_bullets": add_bullets_json,
    "add_code": add_code_json,
    "add_glossary": add_glossary_json,
    "add_callout": add_callout_json,
    "add_columns": add_columns_json,
    "add_pullquote": add_pullquote_json,
    "add_card": add_card_json,
    "add_details": add_details_json,
    "get_page_report": get_page_report_json,
    "finalize_page": finalize_page_json,
}

TOOL_SPECS = [_SCHEMAS[name] for name in TOOL_REGISTRY]
tools = [{"type": "function", "function": spec} for spec in TOOL_SPECS]


def run_tool_calls(tool_calls) -> list[tuple[str, str]]:
    return dispatch.run_tool_calls(TOOL_REGISTRY, tool_calls, _call_log,
                                   terminal_tools={"finalize_page"})


def replay(path) -> list[str]:
    return dispatch.replay(TOOL_REGISTRY, path)
