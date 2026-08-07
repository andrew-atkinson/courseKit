"""The component catalog — the single source of truth for what content COMPONENTS exist, what each
is FOR, and when to reach for it.

A component is a typed block a generator commits (today: the page blocks in `generate/page/page.py`).
This catalog consolidates what was scattered — the *schema* (page.py), the *pedagogic rationale*
(docs/design.md + the CLT/UDL frames), and the *when-to-use* guidance (the prompts) — into one place
a HUMAN reads (`docs/components.md` is generated from here) and the SYSTEM can program against
(composition and the upstream evaluators select by FUNCTION, not by name).

The drift guard in `tests/test_catalog.py` keeps it honest: every block kind has exactly one entry
and vice versa, so a component added to `page.py` without a catalog entry fails the suite.

Foundation for COMP-2 (one vocabulary across content types — see `Component.content_types`) and
COMP-3 (pedagogically-driven composition — pick components by `Component.functions`).
"""

from dataclasses import dataclass

# ---- the pedagogic FUNCTIONS a component can serve (the project's CLT + UDL frames) ----------------
# Named so composition (COMP-3) and evaluation (EVAL-10/12) can reason about a component's FIT, not
# just its presence. A component earns its place by serving one of these; design that serves none
# doesn't ship (the anti-decoration rule, which is itself CLT — restraint manages extraneous load).
# The vocabulary may name a function we have no component for yet (e.g. `action`) — that is a gap
# signal, not an error, so tests do NOT require every function to be used.
FUNCTIONS: dict[str, str] = {
    "exposition": "Explain an idea in prose — the base narrative act.",
    "chunking": "CLT segmenting — break content into working-memory-sized, labelled pieces.",
    "signalling": "CLT — foreground the one thing that matters; the reserved accent.",
    "contrast": "CLT — place two things side by side (wrong-way/right-way, before/after).",
    "type-distinction": "Cut 'what am I reading?' load by naming a unit's type (UDL representation).",
    "worked-example": "Show the doing — a concrete, followable example.",
    "retrieval": "Testing effect — make the student predict/recall before revealing.",
    "representation": "UDL multiple means — a non-prose channel (visual) for the same idea.",
    "engagement": "UDL — hook and motivate; give a reason to care.",
    "action": "UDL — invite the student to try it.",
    "reference": "Look-up material — terms and definitions to review.",
}


@dataclass(frozen=True)
class Component:
    """One catalog entry: a component, what it serves, and when to use it."""
    kind: str                       # the block kind in page._KINDS
    name: str                       # human name
    summary: str                    # one line — what it is
    functions: tuple[str, ...]      # the pedagogic functions it serves (keys of FUNCTIONS)
    use_when: str
    avoid_when: str
    fields: str = ""                # key schema fields, human-readable
    variants: str = ""              # enum choices (role/tone/card_kind), "" if none
    content_types: tuple[str, ...] = ("page",)   # the COMP-2 seam — which artifacts may use it


# Order mirrors `page._KINDS` so the generated doc reads in a sensible order.
CATALOG: dict[str, Component] = {c.kind: c for c in [
    Component(
        kind="heading", name="Section heading",
        summary="Opens a titled section and marks what KIND of section it is.",
        functions=("chunking", "signalling"),
        use_when="Start each concept/section; assign a role so students can scan the page's shape.",
        avoid_when="Never leave a heading with no content before the next heading — it renders as an empty panel.",
        fields="text, level (1–4), role?",
        variants="role: review · concept · practice · example · summary"),
    Component(
        kind="paragraph", name="Paragraph",
        summary="A paragraph of teaching prose (markdown).",
        functions=("exposition",),
        use_when="Explain one idea — one idea per paragraph.",
        avoid_when="Don't stack many long paragraphs with no device between them (crowds the reader).",
        fields="text (markdown)"),
    Component(
        kind="bullets", name="Bulleted list",
        summary="A short list of parallel points.",
        functions=("chunking",),
        use_when="Enumerate steps, key takeaways, or parallel items.",
        avoid_when="Not for prose fragmented into bullets, and not for comparisons (use columns).",
        fields="items[]"),
    Component(
        kind="code", name="Code block",
        summary="A literal, fenced code sample.",
        functions=("worked-example", "representation"),
        use_when="Show the actual code the material teaches; introduce it with a sentence first.",
        avoid_when="Never two code blocks back to back with no prose between; never invent code not in the material.",
        fields="code, language"),
    Component(
        kind="glossary", name="Glossary",
        summary="Term/definition pairs for review.",
        functions=("reference",),
        use_when="Collect a section's or a week's key terms for look-up.",
        avoid_when="Not a substitute for teaching a term in context the first time it appears.",
        fields="entries[] (term, definition)"),
    Component(
        kind="callout", name="Callout",
        summary="A set-apart note, tip, or warning.",
        functions=("signalling",),
        use_when="Flag a pitfall (warning), an aside (note), or a pro-tip (tip).",
        avoid_when="Sparingly — overuse drains the signal it depends on.",
        fields="text, tone",
        variants="tone: note · tip · warning"),
    Component(
        kind="columns", name="Comparison columns",
        summary="2–3 side-by-side lists for comparison.",
        functions=("contrast",),
        use_when="Wrong-way/right-way, before/after, or option A vs B.",
        avoid_when="Not for a single list (use bullets); code reads poorly as bulleted lines (known bug, RICH-1).",
        fields="columns[] (title, items[])"),
    Component(
        kind="pullquote", name="Pull quote",
        summary="The one key idea, foregrounded.",
        functions=("signalling",),
        use_when="Once per page — the week's enduring understanding.",
        avoid_when="More than one per page dilutes the signal.",
        fields="text, attribution?"),
    Component(
        kind="card", name="Typed card",
        summary="A titled, self-contained unit whose type is visible.",
        functions=("type-distinction", "representation"),
        use_when="Distinguish a concept / example / takeaway as its own visible unit.",
        avoid_when="Don't card ordinary prose — reserve it for a genuinely distinct unit.",
        fields="title, text, card_kind",
        variants="card_kind: concept · example · takeaway"),
    Component(
        kind="details", name="Disclosure / retrieval",
        summary="A predict-before-reveal foldout (native <details>, no JS).",
        functions=("retrieval", "chunking"),
        use_when="A 'Predict: …' recall prompt, or optional depth ('Going deeper').",
        avoid_when="Don't hide essential content behind a fold; a hollow foldout to satisfy a gate is worse than none.",
        fields="summary (the visible prompt), text (the revealed content)"),
    Component(
        kind="image", name="Inline image",
        summary="A visual placed inline where it teaches (the instructor supplies the file).",
        functions=("representation",),
        use_when="A diagram, example work, or chart the material shows — place the ref where it belongs.",
        avoid_when="Never emit a URL (the model fabricates them); alt text is required or the image is dropped.",
        fields="ref, alt (required), caption?"),
]}


# ---- content types (COMP-2) — which components each artifact composes from ------------------------
# The catalog is the single authority on composition: a content type's PALETTE is just the components
# whose `content_types` include it. Composition (COMP-3) picks from the palette; a content type's
# validate step calls `unknown_components` to reject anything off-palette. New content types
# (discussion, assignment, overview, …) join CONTENT_TYPES and tag components in `content_types` —
# one source, no per-type block registry.
CONTENT_TYPES: dict[str, str] = {
    "page": "A teaching, reference, or orientation page (page.json).",
}


def components_for(content_type: str) -> list[Component]:
    """The components a content type may compose from (its palette)."""
    return [c for c in CATALOG.values() if content_type in c.content_types]


def allows(content_type: str, kind: str) -> bool:
    """Whether `content_type` may use the component `kind`."""
    c = CATALOG.get(kind)
    return bool(c and content_type in c.content_types)


def unknown_components(content_type: str, kinds) -> list[str]:
    """The kinds `content_type` is NOT allowed to use (empty = all fine) — the enforcement hook a
    content type's validate step calls once it has a real subset of the vocabulary."""
    return [k for k in kinds if not allows(content_type, k)]


# ---- doc generation (COMP-4) — docs/components.md is rendered from here, never hand-edited ----------
def render_markdown() -> str:
    """The `docs/components.md` content, generated from CATALOG + FUNCTIONS. Deterministic, so a test
    can assert the committed doc matches (no drift)."""
    lines = [
        "# Component catalog",
        "",
        "> Generated from `coursekit/generate/catalog.py` — edit there, then run "
        "`python -m coursekit.generate.catalog`. Do not edit this file by hand.",
        "",
        "The components a page (later: any content type) is composed from. Each earns its place by "
        "serving a **pedagogic function** — the design that serves none doesn't ship.",
        "",
        "## Pedagogic functions",
        "",
        "The CLT + UDL frames a component can serve; composition and evaluation reason about these.",
        "",
    ]
    for name, desc in FUNCTIONS.items():
        lines.append(f"- **{name}** — {desc}")
    lines += ["", "## Content types", "",
              "The artifacts these components compose into; each component's **Used in** says which apply.", ""]
    for name, desc in CONTENT_TYPES.items():
        lines.append(f"- **{name}** — {desc} ({len(components_for(name))} components)")
    lines += ["", "## Components", ""]
    for c in CATALOG.values():
        lines.append(f"### `{c.kind}` — {c.name}")
        lines.append(f"- **Serves:** {', '.join(c.functions)}")
        lines.append(f"- **What:** {c.summary}")
        lines.append(f"- **Use when:** {c.use_when}")
        lines.append(f"- **Avoid:** {c.avoid_when}")
        if c.fields:
            lines.append(f"- **Fields:** {c.fields}")
        if c.variants:
            lines.append(f"- **Variants:** {c.variants}")
        lines.append(f"- **Used in:** {', '.join(c.content_types)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


DOC_PATH = "docs/components.md"


def _repo_root():
    from pathlib import Path
    return Path(__file__).resolve().parents[2]


def write_doc() -> str:
    """Write docs/components.md from the catalog; returns the path written."""
    p = _repo_root() / DOC_PATH
    p.write_text(render_markdown(), encoding="utf-8")
    return str(p)


if __name__ == "__main__":
    print(f"wrote {write_doc()}  ({len(CATALOG)} components, {len(FUNCTIONS)} functions)")
