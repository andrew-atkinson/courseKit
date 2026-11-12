"""Records for pages and concept maps (CORE-4.2): which steps made each, and how a check rebuilds each
step's brief from today's files. See coursekit/records.py and agent/core-4-design.md.

A page's steps depend on how it was made (`options["generator"]`): a monolithic page has one `generate`
step; a decomposed one a `frame`, one `section: <concept>` per concept, and a `close`; a glossary one
`glossary` step; a model-free overview or recap one `build` step, whose brief is the page coursekit
assembles — so a check rebuilds it and compares. A concept map has `analyze` and, when its text was split
into per-concept material, `segment`. Every rebuild calls the run's own builder.
"""

from dataclasses import replace
from pathlib import Path

from coursekit import courseconfig, records

PAGE_OUTPUTS = ("page.json",)        # what a page is; its .html is rendered from it


def options(unit, generator: str, *, overrides: dict | None = None, neighbours: bool = True) -> dict:
    opts = {"text": str(Path(unit.transcript_path).resolve()), "generator": generator}
    if overrides:
        opts["overrides"] = overrides
    if not neighbours:
        opts["neighbours"] = False
    return opts


def write_page(out_dir, unit, steps: list[dict], *, read: dict, options: dict, model: str | None = None,
               by: str = "model") -> None:
    """A finished page's record: a new one, since every page build makes the whole page again."""
    records.write_steps(out_dir, [{**s, "by": by, "read": read, "model": model, "options": options}
                                  for s in steps],
                        kind="page", unit=unit.week_num or unit.week_slug, outputs=PAGE_OUTPUTS, fresh=True)


def write_fix(out_dir, model: str, *, edited: bool = False) -> None:
    """A `fix` rewrote sections of a page: a step, so the page reads as coursekit's, not as edited by
    hand. `edited` notes a hand edit found before the fix. A fix is provenance only (no brief), as for a
    quiz; a page with no record gets none."""
    records.write_step(out_dir, step="fix", by="model", model=model, kind="page", unit=None,
                       outputs=PAGE_OUTPUTS, edited=edited)


def write_map(unit, step: str, messages, read: dict, model: str, *, fresh: bool = False) -> None:
    """A step of `analyze` on a unit's concept map, recorded beside it (`week-7.record.json`)."""
    from coursekit.generate.page.concept_map import concept_map_path
    path = concept_map_path(unit.course_root, unit.week_num)
    materials = f"week-{unit.week_num}.materials.json"
    outputs = (path.name,) + ((materials,) if step == "segment" else ())
    records.write_steps(path.parent, [{"step": step, "by": "model", "brief": records.digest(messages), "read": read,
                                       "model": model, "wrote": [materials if step == "segment" else path.name],
                                       "options": {"text": str(Path(unit.transcript_path).resolve())}}],
                        kind="concept_map", unit=unit.week_num, outputs=outputs, fresh=fresh,
                        name=records.name_for(path))


def deterministic(unit, function: str):
    """A model-free overview or recap page, assembled from the unit's concept map."""
    from coursekit.generate.overview import build_week_overview, build_week_recap
    from coursekit.generate.page.concept_map import load_for_unit
    builder = build_week_overview if function == "overview" else build_week_recap
    return builder(unit.course_title or "Course", unit.week_num, unit.week_label or unit.week_slug,
                   unit.module or "", load_for_unit(unit))


def rebuild(rec: dict, step: dict, art_dir) -> list | dict:
    """What `step` would show the model today (for a model-free page, the page itself)."""
    opts = step.get("options", {})
    unit, text = records.unit_for(opts["text"], art_dir)
    if rec["kind"] == "concept_map":
        from coursekit.generate.page import consolidate, segment
        if step["step"] == "analyze":
            return consolidate.analyze_brief(unit)
        plan = segment.brief(unit)
        if plan is None:
            raise LookupError("there is nothing to split into per-concept material")
        return plan[2]
    gen = opts["generator"]
    if gen == "monolithic":
        from coursekit.generate.page.generator import PageGenerator
        cfg = courseconfig.load(unit.transcript_path, config_name="page.yaml")
        if opts.get("overrides"):
            cfg = replace(cfg, config={**(cfg.config or {}), **opts["overrides"]})
        return PageGenerator().build_messages(unit, text, cfg)
    if gen == "decompose":
        from coursekit.generate.page import decompose
        for st in decompose.plan(unit, neighbours=opts.get("neighbours", True)):
            if st["step"] == step["step"]:
                return decompose.step_messages(st)
        raise LookupError(f"{step['step'].removeprefix('section: ')!r} is no longer in the concept map")
    if gen == "glossary":
        from coursekit.generate.page import glossary
        return glossary.step_messages(glossary.passes(unit))
    return deterministic(unit, gen).model_dump(mode="json")
