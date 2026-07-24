"""CLI entry point. All orchestration lives in pipeline.py; this only parses args, builds the
LM Studio client, and prints a summary.

    python app.py [PATH] [--week N ...] [--weeks A-B] [--output-root DIR] [--dry-run]

PATH is a transcript file or a directory of them; it defaults to the TRANSCRIPTION env var.
Artifacts are written with the course (a sibling quizzes/ tree), never into this repo.
"""

import argparse
import os
import sys
from dotenv import load_dotenv

load_dotenv(override=True)

from coursekit import pipeline
from coursekit.emit import qti
from coursekit import courseconfig
from coursekit.emit import html as html_emit
from coursekit.emit import cc as cc_emit
from coursekit.generate.page.generator import PageGenerator
from coursekit.providers import get_provider


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


def _run_bundle(path) -> int:
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


def _run_to_qti(path) -> int:
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate question banks from lecture transcripts.")
    parser.add_argument("path", nargs="?", default=os.getenv("TRANSCRIPTION"),
                        help="transcript file or directory (default: $TRANSCRIPTION)")
    parser.add_argument("--week", action="append", metavar="N",
                        help="a week to include, repeatable, e.g. --week 3 --week 5")
    parser.add_argument("--weeks", metavar="A-B", help="an inclusive week range, e.g. --weeks 3-8")
    parser.add_argument("--output-root", metavar="DIR",
                        help="override: write under DIR/<course>/<week> instead of with the course")
    parser.add_argument("--dry-run", action="store_true",
                        help="list the units that would be processed, without calling the model")
    parser.add_argument("--pages", action="store_true",
                        help="generate course pages instead of quizzes")
    parser.add_argument("--to-qti", metavar="PATH",
                        help="model-free: write a Canvas QTI .zip beside every bank.json under PATH")
    parser.add_argument("--to-html", metavar="PATH",
                        help="model-free: re-render every page.json under PATH to HTML, merging "
                             "the course's current supplements")
    parser.add_argument("--to-cc", metavar="PATH",
                        help="model-free: package every page.json under PATH into ONE Canvas "
                             ".imscc that imports as Pages")
    parser.add_argument("--bundle", action="store_true",
                        help="with --to-qti: write ONE package containing every quiz, "
                             "so a single Canvas import brings them all in")
    parser.add_argument("--max-iters", type=int, default=pipeline.DEFAULT_MAX_ITERS)
    args = parser.parse_args(argv)

    if args.to_qti:
        return _run_bundle(args.to_qti) if args.bundle else _run_to_qti(args.to_qti)

    if args.to_html:
        results = html_emit.reemit(args.to_html)
        if not results:
            print(f"No page.json found under {args.to_html}")
            return 1
        print("Pages re-rendered:")
        for _, out in results:
            print(f"  [OK]   {out}")
        print(f"\n{len(results)} page(s).")
        return 0

    if args.to_cc:
        out = cc_emit.write_imscc(args.to_cc)
        if out is None:
            print(f"No page.json found under {args.to_cc}")
            return 1
        print(f"Canvas Common Cartridge:\n  [OK]   {out}")
        return 0

    if not args.path:
        parser.error("no PATH given and TRANSCRIPTION is not set")

    weeks = _parse_weeks(args)
    generator = PageGenerator() if args.pages else None   # None → the default quiz generator
    provider = None if args.dry_run else _build_provider()
    # MODEL_NAME (env) wins; otherwise the course's own <generator>.yaml `model` key. Resolved from
    # the input path's course root — one invocation targets one course in practice.
    config_name = "page.yaml" if args.pages else "quiz.yaml"
    model = os.getenv("MODEL_NAME") or courseconfig.load(args.path, config_name=config_name).value("model")

    if not args.dry_run:
        verdict, msg = provider.check_fit(model)
        if verdict is False:
            print(f"Warning: {msg}\n")

    try:
        results = pipeline.run_course(
            args.path, weeks=weeks, output_root=args.output_root,
            provider=provider, model=model, dry_run=args.dry_run, max_iters=args.max_iters,
            generator=generator,
        )
    except pipeline.ModelLoadError as e:
        print(str(e))
        return 2

    _print_summary(results, dry_run=args.dry_run)

    if not args.dry_run and any(not r.finalized for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
