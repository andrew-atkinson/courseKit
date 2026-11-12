"""Page dispatch — one unit → the right page, by FUNCTION, with the generator chosen automatically.

This is the single seam the CLI drives for pages. The user asks for a FUNCTION (what the page is
for); the program decides the mechanism:

  overview  → deterministic assembly (overview.py) — orientation, no teaching arc
  recap     → deterministic assembly (overview.py) — after-the-week recall, no teaching arc
  glossary  → the glossary companion (glossary.py) — terms beside the video
  teaching  → monolithic (the Generator seam via pipeline.run_unit) OR decompose (per-concept passes),
              chosen by route.choose_generator from measured length/concepts/spans, unless the caller
              forces one with `generator=`.

Everything lands under `pages/` (teaching → `pages/<week>/`, the others → `pages/<week>-<function>/`),
so evaluate/fix/emit see every function uniformly. Returns a RunResult like the pipeline does.
"""

from pathlib import Path

from coursekit import atomic, courseconfig, outcomes
from coursekit.generate.base import RunResult
from coursekit.generate.page import decompose, glossary as glossary_mod, route
from coursekit.generate.page.concept_map import load_for_unit
from coursekit.outcomes import CoursekitError

FUNCTIONS = ("teaching", "glossary", "overview", "recap")
GENERATORS = ("auto", "monolithic", "decompose")
# Model-FREE functions: assembled deterministically from the concept map, so there is no model output
# to cold-read afterward — `generate` skips its post-run review for these (see cli).
DETERMINISTIC_FUNCTIONS = ("overview", "recap")


def _write_page(page, out_dir: Path, project_root) -> None:
    """Write page.json + rendered HTML (with supplements) — the same output shape emit reads."""
    from coursekit.emit import html as html_emit
    from coursekit.generate.page.renderer import load_supplements
    from coursekit.generate.page.style import load_style
    atomic.write(out_dir / "page.json", page.model_dump_json(indent=2))
    supp = load_supplements(project_root, page.week_ref or page.slug)
    html_emit.write_html(page, out_dir, supp, load_style(project_root))


def route_teaching(unit, *, verbose: bool = True) -> str:
    """The program's monolithic-vs-decompose call for a teaching page (page.yaml can tune the budgets)."""
    from coursekit.generate.page import segment as seg
    cfg = courseconfig.load(unit.transcript_path, config_name="page.yaml")
    transcript = Path(unit.transcript_path).read_text(encoding="utf-8", errors="replace")
    sig = route.signals_for(transcript, load_for_unit(unit), seg.load_materials_for_unit(unit) or {})
    pass_budget = int(cfg.value("max_pass_chars", decompose.DEFAULT_PASS_CHARS))
    reasons = route.decompose_reasons(
        sig,
        char_budget=int(cfg.value("mono_char_budget", route.MONO_CHAR_BUDGET)),
        concept_budget=int(cfg.value("mono_concept_budget", route.MONO_CONCEPT_BUDGET)),
        pass_budget=pass_budget)
    choice = "decompose" if reasons else "monolithic"
    if verbose:
        why = "; ".join(reasons) if reasons else "fits a single pass"
        outcomes.info("page.route", f"  [route] {unit.week_slug}: {choice} ({why})",
                      unit=unit.week_slug, choice=choice, reasons=reasons)
    return choice


def page_dir(unit, function: str = "teaching") -> Path:
    """Where a unit's page for `function` lives: the unit's folder for teaching, a sibling for the others."""
    out = Path(unit.output_dir)
    return out if function == "teaching" else out.parent / f"{unit.week_slug}-{function}"


def build_page_unit(unit, provider, model, *, function: str = "teaching", generator: str = "auto",
                    max_iters: int | None = None, project_root=None) -> RunResult:
    """Produce one unit's page for the requested `function`, choosing the generator automatically
    (or as forced by `generator`). Returns a RunResult (counts blocks)."""
    project_root = project_root or unit.course_root
    out = page_dir(unit, function)

    if function == "glossary":
        pg, problems = glossary_mod.build_glossary_page(unit, provider, model, out,
                                                        project_root=project_root)
        return RunResult(unit, finalized=not problems, output_dir=out,
                         counts={"blocks": len(pg.blocks)}, problems=problems)

    if function in DETERMINISTIC_FUNCTIONS:
        cm = load_for_unit(unit)
        if cm is None or not cm.concepts:        # these pages are built FROM the map — refuse, don't ship an intro
            raise CoursekitError(f"{unit.week_slug}: a {function} page is built from the concept map, and "
                                 f"{'there is none (run `analyze` first)' if cm is None else 'it lists no concepts'}.",
                                 code="concept_map.missing", category="source",
                                 details={"unit": unit.week_slug, "function": function})
        from coursekit import records
        from coursekit.generate.page import record
        with records.reading() as read:
            page = record.deterministic(unit, function)
        _write_page(page, out, project_root)
        record.write_page(out, unit, [{"step": "build", "brief": records.digest(page.model_dump(mode="json"))}],
                          read=read, by="coursekit", options=record.options(unit, function))
        return RunResult(unit, finalized=True, output_dir=out, counts={"blocks": len(page.blocks)})

    # teaching — the program picks the mechanism unless the caller forces it
    which = generator if generator in ("monolithic", "decompose") else route_teaching(unit)
    if which == "decompose":
        pg, problems = decompose.generate_page_decomposed(unit, provider, model, out,
                                                          project_root=project_root)
        return RunResult(unit, finalized=not problems, output_dir=out,
                         counts={"blocks": len(pg.blocks)}, problems=problems)

    from coursekit import pipeline                       # monolithic path — the Generator seam
    from coursekit.generate.page.generator import PageGenerator
    kw = {} if max_iters is None else {"max_iters": max_iters}
    return pipeline.run_unit(unit, provider, model, PageGenerator(), **kw)
