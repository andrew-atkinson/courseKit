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

from coursekit import atomic, courseconfig, outcomes, prompts
from coursekit.discover import slugify
from coursekit.generate.page import concept_map as cmap
from coursekit.generate.page.page import Page, build_block
from coursekit.outcomes import CoursekitError


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


def build_week_recap(course_title: str, num, title: str, module: str, cm) -> Page:
    """A week RECAP: consolidation AFTER the week — the big idea to carry forward, then a
    predict-then-reveal recall of each concept. Assembled from the concept map (the retrieval
    foldouts are the point); the `review`-role heading + the details render as one Recap box."""
    intro = (f"A quick recap of {title} before you move on — recall the big idea, then test "
             "yourself on each concept.")
    pairs = [("intro", "paragraph", {"text": intro})]
    if cm is not None and cm.enduring_understanding:
        pairs.append(("big-idea", "pullquote", {"text": cm.enduring_understanding}))
    concepts = list(cm.concepts) if cm is not None else []
    if concepts:
        pairs.append(("recall-h", "heading", {"text": title, "role": "review"}))
        for i, c in enumerate(concepts):
            answer = c.gist or f"Look back at {c.name} in the week's material."
            pairs.append((f"recall-{i}", "details",
                          {"summary": f"Can you explain {c.name}?", "text": answer}))
    slug = f"week-{num}-recap"
    return Page(page_id=f"{slugify(course_title)}-{slug}", page_type="week_recap",
                title=f"Week {num}: {title} — Recap" if num else f"{title} — Recap",
                week_ref=f"week-{num}" if num else None, slug=slug,
                blocks=_blocks(pairs), finalized=True)


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
    atomic.write(out_dir / f"{page.slug}.json", page.model_dump_json(indent=2))
    return html_emit.write_html(page, out_dir, {}, load_style(root))


def _frame_messages(cfg, root, title: str, topics: str, eu: str) -> list[dict]:
    system = (courseconfig.domain_preface(cfg.domain) + courseconfig.voice_preface(cfg.voice)
              + prompts.load("page", "overview_frame", project_root=root).body)
    return [{"role": "system", "content": system},
            {"role": "user", "content": f"Title: {title}\nTopics: {topics}\nBig idea: {eu or '(none stated)'}"}]


def plan(course_path, *, framing: bool = True) -> tuple:
    """Every overview page for a course, from today's files, in order: each week with a concept map, then
    each module. Each is {"unit", "build": framing → Page, "frame": the framing pass's messages (when
    `framing`), "maps": the concept maps it is built from}, or {"unit", "skip": why}. The run and a record's check both build it here (CORE-4.2).
    Returns (root, entries)."""
    from functools import partial
    cfg = courseconfig.load(course_path)
    root = cfg.root
    if not root:
        raise CoursekitError("no .vtconfig course root found (need context.yaml + concept maps)",
                             code="course.no_root", details={"path": str(course_path)})
    course_title = cfg.course_title or "Course"
    weeks = (cfg.context or {}).get("weeks") or {}

    parsed = []
    for key, meta in weeks.items():
        num = courseconfig.week_key(key)
        cm = cmap.load_concept_map(cmap.concept_map_path(root, num)) if num else None
        parsed.append((num, (meta or {}).get("title") or key, (meta or {}).get("module") or "", cm))
    parsed.sort(key=lambda t: int(t[0]) if t[0] and str(t[0]).isdigit() else 999)

    def entry(unit, build, title, topics, eu, weeks):
        return {"unit": unit, "build": build, "title": title, "maps": [cmap.concept_map_path(root, n) for n in weeks],
                "frame": _frame_messages(cfg, root, title, topics, eu) if framing else None}

    entries = []
    for num, title, module, cm in parsed:
        if cm is None or not cm.concepts:        # nothing to orient toward without a concept map
            entries.append({"unit": num, "skip": f"week {num} ({title}): no overview — "
                            f"{'no concept map; run `coursekit analyze`' if cm is None else 'its concept map lists no concepts'}."})
            continue
        entries.append(entry(num, partial(build_week_overview, course_title, num, title, module, cm),
                             f"Week {num}: {title}", ", ".join(c.name for c in cm.concepts), cm.enduring_understanding,
                             [num]))
    modules: dict[str, list] = {}
    for num, title, module, cm in parsed:
        if module and cm is not None:
            modules.setdefault(module, []).append((num, title, cm.enduring_understanding))
    for module, wks in modules.items():
        entries.append(entry(None, partial(build_module_overview, course_title, module, wks),
                             module, "; ".join(t for _, t, _ in wks), "", [n for n, _, _ in wks]))
    return root, entries


def generate_overviews(course_path, *, provider=None, model=None, framing: bool = True) -> list[Path]:
    """Build every week 'Start Here' + every module overview for a course, writing them to
    `<course>/overview/`, each with its record (`<slug>.record.json`). Deterministic assembly; `framing`
    adds a light model intro per page."""
    from coursekit import records
    with records.reading() as read:
        root, entries = plan(course_path, framing=bool(framing and provider))
    every_map = {str(cmap.concept_map_path(root, courseconfig.week_key(k)).resolve())
                 for k in (courseconfig.load(course_path).context or {}).get("weeks") or {}}

    def frame(e) -> str:
        if not e["frame"]:
            return ""
        try:
            out = provider.chat(model=model, temperature=0.4, messages=e["frame"]).strip()
            return "" if ("http" in out or "://" in out) else out   # framing carries no links
        except Exception as ex:                  # optional: the default intro stands in, but say so
            outcomes.warn("overview.framing_failed", f"  {e['title']}: framing skipped ({type(ex).__name__}: {ex}) "
                                                     f"— using the default intro.", page=e["title"])
            return ""

    out_dir = Path(root) / "overview"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for e in entries:
        if "skip" in e:
            outcomes.warn("overview.skipped", f"  {e['skip']}", unit=e["unit"])
            continue
        f = frame(e)
        page = e["build"](framing=f)
        written.append(_render_overview(page, out_dir, root))
        mine = {str(m.resolve()) for m in e["maps"]}                # every page reads the course's settings,
        own = {k: h for k, h in read.items() if k not in every_map or k in mine}   # but only its own weeks' maps
        steps = [{"step": "build", "by": "coursekit", "brief": records.digest(_built(e)), "read": own,
                  "options": {"slug": page.slug}}]
        if f:
            steps.append({"step": "frame", "by": "model", "brief": records.digest(e["frame"]), "read": own,
                          "model": model, "options": {"slug": page.slug}})
        records.write_steps(out_dir, steps, kind="overview", unit=e["unit"], outputs=(f"{page.slug}.json",),
                            fresh=True, name=records.name_for(f"{page.slug}.json"))
    return written


def _built(e) -> dict:
    """What the program assembles for an overview, apart from the model's framing."""
    return e["build"]().model_dump(mode="json")


def rebuild(rec: dict, step: dict, art_dir):
    """What `step` of an overview's record would produce today: the page as assembled, or the framing
    pass's messages."""
    from coursekit import records
    _, entries = plan(records._root(Path(art_dir)), framing=step["step"] == "frame")
    for e in entries:
        if "skip" not in e and e["build"]().slug == step["options"]["slug"]:
            return e["frame"] if step["step"] == "frame" else _built(e)
    raise LookupError(f"{step['options']['slug']!r} is no longer one of the course's overviews")


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
    from coursekit.console import run
    raise SystemExit(run(main))
