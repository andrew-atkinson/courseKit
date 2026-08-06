"""Week & module OVERVIEW pages — orientation, ASSEMBLED from data (the cheap high-value page type).

A week "Start Here" and a module overview are mostly navigation, and the data already exists: the
course's `context.yaml` (weeks, titles, modules) and its concept maps (each week's concepts + enduring
understanding = the topics). So these are built DETERMINISTICALLY from that data — no tool-calling
generation, none of the per-pass reliability risk — with one optional light model call for a warm 2-3
sentence orientation. Reuses the page IR + renderer + HTML emitter; writes each as `<slug>.html` under
`<course>/overview/`. Canvas's own module UI supplies the navigation links, so the page's job is the
what/why, not the where.

    uv run python -m coursekit.generate.overview "/path/to/course"               # week + module overviews
    uv run python -m coursekit.generate.overview "/path/to/course" --no-framing   # deterministic only, no model
"""

import argparse
import os
from pathlib import Path

from coursekit import courseconfig, prompts
from coursekit.discover import slugify
from coursekit.generate.page import concept_map as cmap
from coursekit.generate.page.page import Page, build_block


def _blocks(pairs) -> dict:
    """(block_id, kind, fields) tuples → the page's ordered blocks dict."""
    return {bid: build_block(kind, block_id=bid, **fields) for bid, kind, fields in pairs}


# --------------------------------------------------------------------------- deterministic builders
def build_week_overview(course_title: str, num, title: str, module: str, cm, *, framing: str = "") -> Page:
    """A week 'Start Here': orientation + the big idea + what-you'll-cover + objectives, all from the
    concept map. `framing` (a model blurb) replaces the default intro when supplied."""
    intro = framing or ((f"This week — {title} — is part of {module}. " if module else f"This is {title}. ")
                        + "Here is what it covers and why it matters.")
    pairs = [("intro", "paragraph", {"text": intro})]
    if cm is not None and cm.enduring_understanding:
        pairs.append(("big-idea", "pullquote", {"text": cm.enduring_understanding}))
    concepts = list(cm.concepts) if cm is not None else []
    if concepts:
        pairs.append(("cover-h", "heading", {"text": "What you'll cover", "role": "concept"}))
        pairs.append(("cover", "bullets",
                      {"items": [f"{c.name} — {c.gist}" if c.gist else c.name for c in concepts]}))
        objectives = [f"{c.level} {c.name}" for c in concepts if c.level]
        if objectives:
            pairs.append(("obj-h", "heading", {"text": "By the end, you'll be able to", "role": "practice"}))
            pairs.append(("obj", "bullets", {"items": objectives}))
    slug = f"week-{num}-overview"
    return Page(page_id=f"{slugify(course_title)}-{slug}", page_type="week_overview",
                title=f"Week {num}: {title}" if num else title,
                week_ref=f"week-{num}" if num else None, slug=slug, blocks=_blocks(pairs), finalized=True)


def build_module_overview(course_title: str, module: str, weeks, *, framing: str = "") -> Page:
    """A module overview: its weeks, each with a one-line theme (its enduring understanding).
    `weeks` is a list of (num, title, enduring_understanding)."""
    intro = framing or f"{module} spans {len(weeks)} week(s). Here is the arc it follows."
    items = []
    for num, title, eu in weeks:
        line = f"Week {num}: {title}" if num else title
        items.append(f"{line} — {eu}" if eu else line)
    pairs = [("intro", "paragraph", {"text": intro}),
             ("weeks-h", "heading", {"text": "In this module", "role": "concept"}),
             ("weeks", "bullets", {"items": items})]
    # avoid "module-module-2-…" when the module name already starts with "Module"
    mslug = slugify(module)
    slug = (f"{mslug}-overview" if mslug.startswith("module-") else f"module-{mslug}-overview")
    return Page(page_id=f"{slugify(course_title)}-{slug}", page_type="module_overview",
                title=module, week_ref=None, slug=slug, blocks=_blocks(pairs), finalized=True)


# --------------------------------------------------------------------------- orchestration
def _render_overview(page, out_dir: Path, root) -> Path:
    from coursekit.emit import html as html_emit
    from coursekit.generate.page.style import load_style
    (out_dir / f"{page.slug}.json").write_text(page.model_dump_json(indent=2), encoding="utf-8")
    return html_emit.write_html(page, out_dir, {}, load_style(root))


def generate_overviews(course_path, *, provider=None, model=None, framing: bool = True) -> list[Path]:
    """Build every week 'Start Here' + every module overview for a course, writing them to
    `<course>/overview/`. Deterministic assembly; `framing` adds a light model intro per page."""
    cfg = courseconfig.load(course_path)
    root = cfg.root
    if not root:
        raise SystemExit("no .vtconfig course root found (need context.yaml + concept maps)")
    course_title = cfg.course_title or "Course"
    weeks = (cfg.context or {}).get("weeks") or {}

    sys_frame = None
    if framing and provider:
        sys_frame = (courseconfig.domain_preface(cfg.domain) + courseconfig.voice_preface(cfg.voice)
                     + prompts.load("page", "overview_frame", project_root=root).body)

    def frame(title: str, topics: str, eu: str) -> str:
        if not sys_frame:
            return ""
        try:
            out = provider.chat(model=model, temperature=0.4, messages=[
                {"role": "system", "content": sys_frame},
                {"role": "user", "content": f"Title: {title}\nTopics: {topics}\nBig idea: {eu or '(none stated)'}"},
            ]).strip()
            return "" if ("http" in out or "://" in out) else out   # framing carries no links
        except Exception:
            return ""

    parsed = []
    for key, meta in weeks.items():
        num = courseconfig.week_key(key)
        cm = cmap.load_concept_map(cmap.concept_map_path(root, num)) if num else None
        parsed.append((num, (meta or {}).get("title") or key, (meta or {}).get("module") or "", cm))
    parsed.sort(key=lambda t: int(t[0]) if t[0] and str(t[0]).isdigit() else 999)

    out_dir = Path(root) / "overview"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for num, title, module, cm in parsed:
        if cm is None or not cm.concepts:        # nothing to orient toward without a concept map
            continue
        f = frame(f"Week {num}: {title}", ", ".join(c.name for c in cm.concepts), cm.enduring_understanding)
        written.append(_render_overview(build_week_overview(course_title, num, title, module, cm, framing=f),
                                        out_dir, root))

    modules: dict[str, list] = {}
    for num, title, module, cm in parsed:
        if module and cm is not None:
            modules.setdefault(module, []).append((num, title, cm.enduring_understanding))
    for module, wks in modules.items():
        f = frame(module, "; ".join(t for _, t, _ in wks), "")
        written.append(_render_overview(build_module_overview(course_title, module, wks, framing=f),
                                        out_dir, root))
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble week + module overview pages from course data.")
    ap.add_argument("course")
    ap.add_argument("--no-framing", action="store_true",
                    help="skip the model framing pass — fully deterministic, no model call")
    args = ap.parse_args()

    provider = model = None
    if not args.no_framing:
        from coursekit.cli import _build_provider
        provider = _build_provider()
        model = os.getenv("MODEL_NAME") or courseconfig.load(
            args.course, config_name="page.yaml").value("model")

    written = generate_overviews(args.course, provider=provider, model=model, framing=not args.no_framing)
    if not written:
        print("No overviews written — need context.yaml weeks + concept maps (run analyze first).")
        return 1
    print(f"{len(written)} overview page(s) → {written[0].parent}")
    for p in written:
        print(f"  {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
