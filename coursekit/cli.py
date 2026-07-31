"""The coursekit CLI.

Three task phases as subcommands, mirroring the architecture's layers (agent/architecture.md):
ingest (documents → week text) → generate (text → artifacts, uses the model) → emit (canonical JSON
→ LMS packages, model-free). Each phase's conditional flags live on its own subcommand, so the
surface is self-describing and the couplings are structural rather than a footgun.

    coursekit ingest   PATH [--raw]
    coursekit generate PATH [--quizzes | --pages] [--week N ...] [--weeks A-B]
                            [--detail brief|medium|full] [--dry-run] [--max-iters N]
                            [--output-root DIR] [--no-review]
    coursekit emit qti  PATH [--bundle]
    coursekit emit html PATH
    coursekit emit cc   PATH

A `generate` run ends with a report-only cold-read review of what it produced — flagged questions to
quiz-review.md, flagged page sections to page-review.md — each read against the week's own material.
`--no-review` skips it; it is also skipped, harmlessly, when no critic model is configured.

All orchestration lives in pipeline.py and the emitters; this only parses args, builds the provider,
and prints summaries. Reachable as the `coursekit` command (an editable install) or `python app.py`.
"""

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)

from coursekit import courseconfig, pipeline
from coursekit.emit import cc as cc_emit
from coursekit.emit import html as html_emit
from coursekit.emit import qti
from coursekit.generate.page.generator import PageGenerator
from coursekit.generate.quiz.generator import QuizGenerator
from coursekit.providers import get_provider


# ---------------------------------------------------------------- shared helpers

def _select_generators(args):
    """Which generators a `generate` run drives. Default is both; --quizzes / --pages narrow to one.
    Quizzes run first so a combined run leaves the pages step last."""
    if args.quizzes:
        return [QuizGenerator()]
    if args.pages:
        return [PageGenerator()]
    return [QuizGenerator(), PageGenerator()]


def _build_provider():
    """Which endpoint serves the model is config, not code — institutional policy may dictate
    on-prem inference or a specific vendor."""
    return get_provider(os.getenv("PROVIDER", "lm_studio"),
                        base_url=os.getenv("LOCAL_HOST_URL"))


def _parse_weeks(args) -> list[str] | None:
    weeks = list(args.week or [])
    if args.weeks:
        try:
            lo, hi = (int(x) for x in args.weeks.split("-"))
        except ValueError:
            raise SystemExit(f"--weeks expects a range like 3-8, got {args.weeks!r}")
        weeks += [str(n) for n in range(lo, hi + 1)]
    return weeks or None


def _print_summary(results, *, dry_run: bool) -> None:
    if not results:
        print("No transcripts found.")
        return
    print("DRY RUN — units that would be processed:" if dry_run else "Run complete:")
    for r in results:
        if dry_run:
            print(f"  [plan] {r.unit.week_label}")
        else:
            status = "OK" if r.finalized else "INCOMPLETE"
            counts = ", ".join(f"{v} {k}" for k, v in r.counts.items()) or "nothing"
            print(f"  [{status}] {r.unit.week_label}  {counts}")
            for p in r.problems:
                print(f"           - {p}")
        print(f"         -> {r.output_dir}")
    print(f"\n{len(results)} unit(s).")


def _critic_model_and_reads(path, reads_override=None):
    """Resolve the quiz critic's model (MODEL_NAME env, else evaluate.yaml `model:`) and read count.
    Model is None when nothing is configured — callers decide whether that is fatal or a skip."""
    from coursekit.generate.quiz import evaluate as ev
    cfg = courseconfig.load(path, config_name="evaluate.yaml")
    model = os.getenv("MODEL_NAME") or cfg.value("model")
    reads = int(reads_override or cfg.value("reads", ev.DEFAULT_READS))
    return model, reads


def _review_quizzes(args, provider) -> None:
    """Cold-read the just-generated quizzes and surface flags (report-only). Best-effort by design: a
    missing or unreachable critic model prints a note and returns — a review problem must never sink an
    otherwise-good generate. Scopes to the same weeks the run produced."""
    from coursekit.generate.quiz import evaluate as ev
    model, reads = _critic_model_and_reads(args.path)
    if not model:
        print("\n(skipping quiz review: no critic model — set MODEL_NAME or evaluate.yaml `model:`)")
        return
    print("\nReviewing the generated quizzes (cold read)…")
    try:
        findings, review = ev.evaluate_course(
            args.path, weeks=_parse_weeks(args), provider=provider, model=model, reads=reads,
            progress=_tick)
    except Exception as e:                       # never let the review abort a finished generate
        print(f"(quiz review skipped: {type(e).__name__}: {e})")
        return
    if not findings:
        return
    flagged = [f for f in findings if f.flagged]
    print(f"Quiz review: {len(flagged)} of {len(findings)} question(s) flagged.")
    for f in flagged:
        print(f"  [{f.verdict}] {f.week} {f.group_id}/{f.label}: {f.concern}")
    if review:
        print(f"-> {review}")


def _review_pages(args, provider) -> None:
    """The page equivalent of _review_quizzes — cold-read each generated page section against the
    week's material (report-only). Same best-effort contract: never fails the generate."""
    from coursekit.generate.page import evaluate as pev
    model, reads = _critic_model_and_reads(args.path)
    if not model:
        print("\n(skipping page review: no critic model — set MODEL_NAME or evaluate.yaml `model:`)")
        return
    print("\nReviewing the generated pages (cold read)…")
    try:
        findings, review = pev.evaluate_course_pages(
            args.path, weeks=_parse_weeks(args), provider=provider, model=model, reads=reads,
            progress=_tick)
    except Exception as e:
        print(f"(page review skipped: {type(e).__name__}: {e})")
        return
    if not findings:
        return
    flagged = [f for f in findings if f.flagged]
    print(f"Page review: {len(flagged)} of {len(findings)} section(s) flagged.")
    for f in flagged:
        print(f"  [{f.verdict}] {f.week} {f.group_id}/{f.label}: {f.concern}")
    if review:
        print(f"-> {review}")


# ---------------------------------------------------------------- ingest

def _cmd_ingest(args) -> int:
    """Turn documents (PDF/pptx/txt/md) under PATH into output/week-N.md, then stop. Local-first:
    with --raw it never calls the model; otherwise it reshapes each doc with the local model."""
    from coursekit.ingest import ingest as ing
    provider = model = None
    if not args.raw:
        provider = _build_provider()
        model = os.getenv("MODEL_NAME") or courseconfig.load(args.path, config_name="ingest.yaml").value("model")
    results = ing.ingest(args.path, raw=args.raw, provider=provider, model=model)
    if not results:
        from coursekit.ingest.extract import SUPPORTED_SUFFIXES
        kinds = "/".join(sorted(SUPPORTED_SUFFIXES))
        print(f"No supported documents ({kinds}) found under {args.path}")
        return 1
    print("Ingested:")
    for src, dest in results:
        print(f"  {src.name}  ->  {dest}")
    print(f"\n{len(results)} week doc(s) written. Now generate with:  coursekit generate \"<course>\"")
    return 0


# ---------------------------------------------------------------- generate

def _cmd_analyze(args) -> int:
    """The 'analyze' phase, between ingest and generate: build each week's concept map. Reads the
    transcriber's `knowledge.json` beside every week doc, consolidates it (the model) into the week's
    teaching concepts + enduring understanding, and writes `.vtconfig/concepts/week-N.yaml` — the
    content model both generate and evaluate stand on. Instructor-editable after; re-run when the
    material changes. Weeks with no knowledge.json are skipped (that course's pages fall back to
    inline derivation until a map is authored)."""
    if not args.path:
        raise SystemExit("no PATH given and TRANSCRIPTION is not set")
    from coursekit.discover import find_units
    from coursekit.generate.page import concept_map as cmap
    from coursekit.generate.page import consolidate as con

    weeks = _parse_weeks(args)
    units = find_units(args.path)
    if weeks:
        units = [u for u in units if any(pipeline._week_matches(w, u) for w in weeks)]
    if not units:
        print("No week transcripts found.")
        return 0

    if args.dry_run:
        print("DRY RUN — weeks that would be analyzed:")
        for u in units:
            wk = cmap.read_week_knowledge(u.transcript_path)
            detail = (f"{len(wk.kcs)} knowledge component(s) from {len(wk.sources)} source(s)"
                      if wk.kcs else "no knowledge.json — would extract from the week text")
            print(f"  [plan] {u.week_label}: {detail}")
        return 0

    provider = _build_provider()
    model = os.getenv("MODEL_NAME") or courseconfig.load(
        args.path, config_name="page.yaml").value("model")
    if not model:
        raise SystemExit("no model configured — set MODEL_NAME or page.yaml `model:`")

    wrote = 0
    for u in units:
        label = u.week_label or u.week_slug
        if not u.course_root:
            print(f"  [skip] {label}: no .vtconfig course root to write the map into")
            continue
        key = courseconfig.week_key(u.week_slug)
        if not key:
            print(f"  [skip] {label}: could not resolve a week number for the filename")
            continue
        cfg = courseconfig.load(u.transcript_path, config_name="page.yaml")
        wk = cmap.read_week_knowledge(u.transcript_path, week=label)
        if wk.kcs:
            cmp = con.consolidate(wk, provider, model, week=label, domain=cfg.domain,
                                  project_root=u.course_root)
            via = f"from {len(wk.kcs)} knowledge components"
        else:
            # No transcriber knowledge.json — fall back to extracting from the week text itself, so a
            # PDF/readings course (no transcripts) still gets a map. Same schema, same consumers.
            from pathlib import Path as _P
            text = _P(u.transcript_path).read_text(encoding="utf-8")
            cmp = con.build_concept_map_from_text(text, provider, model, week=label,
                                                  domain=cfg.domain, project_root=u.course_root)
            via = "from the week text (no knowledge.json)"
        out = cmap.save_concept_map(cmp, cmap.concept_map_path(u.course_root, key))
        eu = " + enduring understanding" if cmp.enduring_understanding else ""
        print(f"  [OK] {label}: {len(cmp.concepts)} concept(s){eu} {via} -> {out}")
        wrote += 1

    print(f"\n{wrote} concept map(s) written. Edit them, then generate.")
    return 0


def _cmd_generate(args) -> int:
    if not args.path:
        raise SystemExit("no PATH given and TRANSCRIPTION is not set")
    weeks = _parse_weeks(args)
    generators = _select_generators(args)
    provider = None if args.dry_run else _build_provider()

    incomplete = False
    for gen in generators:
        # MODEL_NAME (env) wins; otherwise the course's own <generator>.yaml `model` key. Each
        # generator resolves its own — a combined run may use different models for quizzes and pages.
        model = os.getenv("MODEL_NAME") or courseconfig.load(
            args.path, config_name=f"{gen.category}.yaml").value("model")

        if not args.dry_run:
            verdict, msg = provider.check_fit(model)
            if verdict is False:
                print(f"Warning ({gen.category}): {msg}\n")

        try:
            results = pipeline.run_course(
                args.path, weeks=weeks, output_root=args.output_root,
                provider=provider, model=model, dry_run=args.dry_run, max_iters=args.max_iters,
                generator=gen,
                config_overrides={"detail": args.detail} if args.detail else None,
            )
        except pipeline.ModelLoadError as e:
            print(str(e))
            return 2

        if len(generators) > 1:
            print(f"\n=== {gen.category} ===")
        _print_summary(results, dry_run=args.dry_run)
        incomplete = incomplete or (not args.dry_run and any(not r.finalized for r in results))

    # Report-only quality gate: cold-read the new artifacts right after generating them (default on).
    if not args.dry_run and args.review:
        if any(g.category == "quiz" for g in generators):
            _review_quizzes(args, provider)
        if any(g.category == "page" for g in generators):
            _review_pages(args, provider)

    return 1 if incomplete else 0


# ---------------------------------------------------------------- emit (model-free)

def _cmd_emit_qti(args) -> int:
    return _emit_bundle(args.path) if args.bundle else _emit_qti(args.path)


def _emit_qti(path) -> int:
    results = qti.reemit(path)
    if not results:
        print(f"No bank.json found under {path}")
        return 1
    print("Canvas QTI:")
    wrote = 0
    for bank_json, imscc, reason in results:
        if imscc is not None:
            print(f"  [OK]   {imscc}")
            wrote += 1
        else:
            print(f"  [skip] {bank_json.parent.name}: {reason}")
    print(f"\n{wrote}/{len(results)} package(s) written.")
    return 0 if wrote else 1


def _emit_bundle(path) -> int:
    out, included, skipped = qti.bundle(path)
    for bank_json, reason in skipped:
        print(f"  [skip] {bank_json.parent.name}: {reason}")
    if out is None:
        print(f"No usable bank.json found under {path}")
        return 1
    print(f"Bundled {len(included)} quiz(zes) into one package:")
    for bj in included:
        print(f"  - {bj.parent.name}")
    print(f"\n-> {out}")
    print("Import in Canvas via Content Type: \"QTI .zip file\".")
    return 0


def _cmd_emit_html(args) -> int:
    results = html_emit.reemit(args.path)
    if not results:
        print(f"No page.json found under {args.path}")
        return 1
    print("Pages re-rendered:")
    for _, out in results:
        print(f"  [OK]   {out}")
    print(f"\n{len(results)} page(s).")
    return 0


def _cmd_emit_cc(args) -> int:
    out = cc_emit.write_imscc(args.path)
    if out is None:
        print(f"No page.json found under {args.path}")
        return 1
    print(f"Canvas Common Cartridge:\n  [OK]   {out}")
    return 0


def _cmd_emit_course(args) -> int:
    from coursekit.emit import cartridge
    out = cartridge.write_course_imscc(args.path)
    if out is None:
        print(f"No pages or quizzes found under {args.path}")
        return 1
    print(f"Canvas course cartridge (pages + quizzes, in week modules):\n  [OK]   {out}")
    return 0


def _print_findings(kind: str, noun: str, findings, review) -> bool:
    """Print one facticity review block; return whether anything was flagged."""
    flagged = [f for f in findings if f.flagged]
    print(f"{kind}: reviewed {len(findings)} {noun}(s); {len(flagged)} flagged.")
    for f in flagged:
        print(f"  [{f.verdict}] {f.week} {f.group_id}/{f.label}: {f.concern}")
    if review:
        print(f"  -> {review}")
    return bool(flagged)


def _cmd_evaluate(args) -> int:
    """Review ALREADY-generated content in place — quizzes and/or pages, plus an optional page pedagogy
    rubric — without regenerating. Reads bank.json / page.json off disk."""
    from coursekit.generate.page import concept_delivery as cd
    from coursekit.generate.page import evaluate as pev
    from coursekit.generate.page import pedagogy as ped
    from coursekit.generate.quiz import evaluate as ev
    provider = _build_provider()
    model, reads = _critic_model_and_reads(args.path, args.reads)
    if not model:
        print("No critic model configured (set MODEL_NAME or evaluate.yaml `model:`).")
        return 2
    weeks = _parse_weeks(args)
    do_quiz, do_page = not args.pages, not args.quizzes    # default: both facticity passes
    did_something = flagged_any = False

    if do_quiz:
        findings, review = ev.evaluate_course(args.path, weeks=weeks, provider=provider,
                                              model=model, reads=reads, progress=_tick)
        if findings:
            did_something = True
            flagged_any |= _print_findings("Quizzes", "question", findings, review)

    if do_page:
        findings, review = pev.evaluate_course_pages(args.path, weeks=weeks, provider=provider,
                                                     model=model, reads=reads, progress=_tick)
        if findings:
            did_something = True
            flagged_any |= _print_findings("Pages", "section", findings, review)

    # --all adds the deeper page-quality rubrics (form + concept delivery) on top of facticity.
    if args.all and do_page:
        rubrics, out = ped.evaluate_course_pedagogy(args.path, weeks=weeks, provider=provider, model=model)
        if rubrics:
            did_something = True
            print(f"Pedagogy: scored {len(rubrics)} page(s).")
            for r in rubrics:
                print(f"  {r.page_id}: {r.total}/{3 * len(ped.CRITERIA)}")
            print(f"  -> {out}")

        concepts, cout = cd.evaluate_course_concepts(args.path, weeks=weeks, provider=provider, model=model)
        if concepts:
            did_something = True
            print(f"Concept delivery: scored {len(concepts)} page(s).")
            for c in concepts:
                print(f"  {c.page_id}: avg {c.average:.1f}/3 over {len(c.concepts)} concept(s)")
            print(f"  -> {cout}")

    if not did_something:
        print("Nothing found to evaluate (need generated bank.json / page.json under the course).")
        return 1
    return 1 if flagged_any else 0


# ---------------------------------------------------------------- parser

def _tick(msg: str) -> None:
    """A live heartbeat line for the slow model-driven commands — printed and flushed immediately so
    the user sees progress instead of a silent terminal."""
    print(msg, flush=True)


def _review_findings(path, *, pages: bool):
    """The Findings from an existing quiz-review.md / page-review.md, or None if there is no review to
    act on. Lets `fix` repair exactly what the last review flagged without re-auditing the course."""
    from pathlib import Path
    from coursekit.discover import find_units
    from coursekit.generate.quiz.evaluate import parse_review
    units = find_units(path, subdir="pages") if pages else find_units(path)
    if not units:
        return None
    rp = Path(units[0].output_dir).parent / ("page-review.md" if pages else "quiz-review.md")
    return parse_review(rp.read_text(encoding="utf-8")) if rp.exists() else None


def _cmd_fix(args) -> int:
    """REGENERATE each flagged quiz question / page section in place, then verify. By default it acts
    on the LAST review (quiz-review.md / page-review.md) — no re-audit, so a just-flagged item is fixed
    at once; `--reaudit` forces a fresh cold read. Updates bank.json/GIFT + page.json/HTML."""
    if not args.path:
        raise SystemExit("no PATH given")
    provider = _build_provider()
    model, reads = _critic_model_and_reads(args.path, args.reads)
    if not model:
        raise SystemExit("no critic model configured — set MODEL_NAME or evaluate.yaml `model:`")
    weeks = _parse_weeks(args)
    do_quiz, do_page = not args.pages, not args.quizzes    # default: fix both
    did = False

    def _run(kind, fix_call, pages):
        review = None if args.reaudit else _review_findings(args.path, pages=pages)
        if review is not None:
            n = sum(1 for f in review if f.flagged)
            if not n:
                print(f"Last {kind} review had no flags — nothing to fix "
                      f"(use --reaudit for a fresh check).")
                return []
            print(f"Fixing {n} flagged {kind}(s) from the last review…")
        else:
            print(f"No prior {kind} review found — cold-reading the {kind}s (use it, or run "
                  f"`evaluate` first)…")
        return fix_call(review)

    if do_quiz:
        from coursekit.generate.quiz import fix as qfix
        outs = _run("question", lambda review: qfix.fix_course(
            args.path, weeks=weeks, provider=provider, model=model, reads=reads,
            max_turns=args.max_turns, findings=review, progress=_tick), pages=False)
        if outs:
            did = True
            print(qfix.render_outcomes(outs))

    if do_page:
        from coursekit.generate.page import fix as pfix
        outs = _run("section", lambda review: pfix.fix_course_pages(
            args.path, weeks=weeks, provider=provider, model=model, reads=reads,
            max_turns=args.max_turns, findings=review, progress=_tick), pages=True)
        if outs:
            did = True
            print(pfix.render_outcomes(outs))

    if not did:
        print("Nothing fixed.")
        return 0
    print("Artifacts updated (bank.json/GIFT, page.json/HTML). "
          "Re-run `coursekit emit qti` / `emit course` to refresh the Canvas package.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coursekit", description="Generate Canvas artifacts from course material.")
    sub = parser.add_subparsers(dest="command", required=True,
                                metavar="{ingest,analyze,generate,emit}")

    # ingest — documents → week text
    pi = sub.add_parser("ingest", help="documents (PDF/docx/odt/pptx/txt/md) → output/week-N.md")
    pi.add_argument("path", help="a document, or a directory of them")
    pi.add_argument("--raw", action="store_true",
                    help="extract text only; skip the local-LLM shaping pass (fully offline)")
    pi.set_defaults(func=_cmd_ingest)

    # analyze — week text + knowledge.json → the per-week concept map (uses the model)
    pa = sub.add_parser("analyze",
                        help="build each week's concept map (.vtconfig/concepts/week-N.yaml) — the "
                             "content model generate and evaluate read")
    pa.add_argument("path", nargs="?", default=os.getenv("TRANSCRIPTION"),
                    help="transcript file or directory (default: $TRANSCRIPTION)")
    pa.add_argument("--week", action="append", metavar="N", help="a week to analyze, repeatable")
    pa.add_argument("--weeks", metavar="A-B", help="an inclusive week range, e.g. --weeks 3-8")
    pa.add_argument("--dry-run", action="store_true",
                    help="list the weeks and their knowledge-component counts, without the model")
    pa.set_defaults(func=_cmd_analyze)

    # generate — week text → quizzes and/or pages (uses the model)
    pg = sub.add_parser("generate", help="week text → quizzes and/or pages (uses the model)")
    pg.add_argument("path", nargs="?", default=os.getenv("TRANSCRIPTION"),
                    help="transcript file or directory (default: $TRANSCRIPTION)")
    which = pg.add_mutually_exclusive_group()
    which.add_argument("--quizzes", action="store_true", help="only quizzes (default: both)")
    which.add_argument("--pages", action="store_true", help="only pages (default: both)")
    pg.add_argument("--week", action="append", metavar="N",
                    help="a week to include, repeatable, e.g. --week 3 --week 5")
    pg.add_argument("--weeks", metavar="A-B", help="an inclusive week range, e.g. --weeks 3-8")
    pg.add_argument("--detail", choices=("brief", "medium", "full"),
                    help="how much of the week a PAGE covers (overrides page.yaml `detail`); "
                         "medium is the default. No effect on quizzes.")
    pg.add_argument("--dry-run", action="store_true",
                    help="list the units that would be processed, without calling the model")
    pg.add_argument("--max-iters", type=int, default=pipeline.DEFAULT_MAX_ITERS,
                    help=f"cap model turns per week (default {pipeline.DEFAULT_MAX_ITERS})")
    pg.add_argument("--output-root", metavar="DIR",
                    help="write under DIR/<course>/<week> instead of with the course")
    pg.add_argument("--no-review", dest="review", action="store_false",
                    help="skip the automatic cold-read review of the generated quizzes")
    pg.set_defaults(func=_cmd_generate, review=True)

    # emit — canonical JSON → LMS packages (model-free)
    pe = sub.add_parser("emit", help="canonical JSON → LMS packages (model-free)")
    esub = pe.add_subparsers(dest="target", required=True, metavar="{qti,html,cc}")

    eq = esub.add_parser("qti", help="Canvas quiz .zip from every bank.json under PATH")
    eq.add_argument("path", help="a course, or its quizzes/ tree")
    eq.add_argument("--bundle", action="store_true",
                    help="ONE package containing every quiz, so a single Canvas import brings them all in")
    eq.set_defaults(func=_cmd_emit_qti)

    eh = esub.add_parser("html", help="re-render every page.json under PATH to HTML")
    eh.add_argument("path", help="a course, or its pages/ tree")
    eh.set_defaults(func=_cmd_emit_html)

    ec = esub.add_parser("cc", help="ONE Canvas .imscc of all pages under PATH (imports as Pages)")
    ec.add_argument("path", help="a course, or its pages/ tree")
    ec.set_defaults(func=_cmd_emit_cc)

    eco = esub.add_parser("course",
                          help="ONE Canvas .imscc of the WHOLE course — pages AND quizzes, in week modules")
    eco.add_argument("path", help="the course root (its pages/ and quizzes/ trees)")
    eco.set_defaults(func=_cmd_emit_course)

    # evaluate — cold-read quality review of ALREADY-generated quizzes and pages (uses the model)
    pv = sub.add_parser("evaluate",
                        help="cold-read review of already-generated quizzes and pages; flags weak items")
    pv.add_argument("path", help="the course (its quizzes/ and pages/ trees + transcripts)")
    pvw = pv.add_mutually_exclusive_group()
    pvw.add_argument("--quizzes", action="store_true", help="only the quizzes (default: quizzes and pages)")
    pvw.add_argument("--pages", action="store_true", help="only the pages (default: quizzes and pages)")
    pv.add_argument("--all", action="store_true",
                    help="run every evaluation, not just facticity: the page pedagogy (form) and "
                         "concept-delivery rubrics too -> page-pedagogy.md, page-concepts.md")
    pv.add_argument("--week", action="append", metavar="N", help="a week to review, repeatable")
    pv.add_argument("--weeks", metavar="A-B", help="an inclusive week range, e.g. --weeks 3-8")
    pv.add_argument("--reads", type=int, metavar="N",
                    help="cold reads per question/section, unioned (default 1; more = more calls)")
    pv.set_defaults(func=_cmd_evaluate)

    # fix — cold-read the quizzes and regenerate each flagged question in place (uses the model)
    pf = sub.add_parser("fix",
                        help="cold-read quizzes and/or pages and REGENERATE each flagged item in place")
    pf.add_argument("path", help="the course (its quizzes/ and pages/ trees + transcripts)")
    pfw = pf.add_mutually_exclusive_group()
    pfw.add_argument("--quizzes", action="store_true", help="only quizzes (default: quizzes and pages)")
    pfw.add_argument("--pages", action="store_true", help="only pages (default: quizzes and pages)")
    pf.add_argument("--week", action="append", metavar="N", help="a week to fix, repeatable")
    pf.add_argument("--weeks", metavar="A-B", help="an inclusive week range, e.g. --weeks 3-8")
    pf.add_argument("--reaudit", action="store_true",
                    help="cold-read the whole course afresh instead of acting on the last review")
    pf.add_argument("--reads", type=int, metavar="N",
                    help="cold reads per question when finding flaws with --reaudit (default 1)")
    pf.add_argument("--max-turns", type=int, default=4, metavar="N",
                    help="model turns allowed per fix (default 4)")
    pf.set_defaults(func=_cmd_fix)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
