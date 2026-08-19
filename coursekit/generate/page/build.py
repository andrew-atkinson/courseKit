"""Page dispatch — one unit → the right page, by FUNCTION, with the generator chosen automatically.

This is the single seam the CLI drives for pages. The user asks for a FUNCTION (what the page is
for); the program decides the mechanism:

  overview  → deterministic assembly (overview.py) — orientation, no teaching arc
  glossary  → the glossary companion (glossary.py) — terms beside the video
  teaching  → monolithic (the Generator seam via pipeline.run_unit) OR decompose (per-concept passes),
              chosen by route.choose_generator from measured length/concepts/spans, unless the caller
              forces one with `generator=`.

Everything lands under `pages/` (teaching → `pages/<week>/`, the others → `pages/<week>-<function>/`),
so evaluate/fix/emit see every function uniformly. Returns a RunResult like the pipeline does.
"""

from pathlib import Path

from coursekit import courseconfig
from coursekit.generate.base import RunResult
from coursekit.generate.page import decompose, glossary as glossary_mod, route
from coursekit.generate.page.concept_map import load_for_unit

FUNCTIONS = ("teaching", "glossary", "overview")
GENERATORS = ("auto", "monolithic", "decompose")


def _write_page(page, out_dir: Path, project_root) -> None:
    """Write page.json + rendered HTML (with supplements) — the same output shape emit reads."""
    from coursekit.emit import html as html_emit
    from coursekit.generate.page.renderer import load_supplements
    from coursekit.generate.page.style import load_style
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "page.json").write_text(page.model_dump_json(indent=2), encoding="utf-8")
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
        print(f"  [route] {unit.week_slug}: {choice} ({why})")
    return choice


def build_page_unit(unit, provider, model, *, function: str = "teaching", generator: str = "auto",
                    max_iters: int | None = None, project_root=None) -> RunResult:
    """Produce one unit's page for the requested `function`, choosing the generator automatically
    (or as forced by `generator`). Returns a RunResult (counts blocks)."""
    project_root = project_root or unit.course_root
    parent = Path(unit.output_dir).parent

    if function == "glossary":
        out = parent / f"{unit.week_slug}-glossary"
        pg, problems = glossary_mod.build_glossary_page(unit, provider, model, out,
                                                        project_root=project_root)
        return RunResult(unit, finalized=not problems, output_dir=out,
                         counts={"blocks": len(pg.blocks)}, problems=problems)

    if function == "overview":
        from coursekit.generate.overview import build_week_overview
        num = unit.week_num
        page = build_week_overview(unit.course_title or "Course", num,
                                   unit.week_label or unit.week_slug, unit.module or "",
                                   load_for_unit(unit))
        out = parent / f"{unit.week_slug}-overview"
        _write_page(page, out, project_root)
        return RunResult(unit, finalized=True, output_dir=out, counts={"blocks": len(page.blocks)})

    # teaching — the program picks the mechanism unless the caller forces it
    which = generator if generator in ("monolithic", "decompose") else route_teaching(unit)
    out = Path(unit.output_dir)
    if which == "decompose":
        pg, problems = decompose.generate_page_decomposed(unit, provider, model, out,
                                                          project_root=project_root)
        return RunResult(unit, finalized=not problems, output_dir=out,
                         counts={"blocks": len(pg.blocks)}, problems=problems)

    from coursekit import pipeline                       # monolithic path — the Generator seam
    from coursekit.generate.page.generator import PageGenerator
    kw = {} if max_iters is None else {"max_iters": max_iters}
    return pipeline.run_unit(unit, provider, model, PageGenerator(), **kw)
