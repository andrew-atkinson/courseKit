"""CLI-level behaviour that isn't the pipeline itself: which generators a run drives, and that the
subcommand parser routes each phase (ingest / generate / emit qti|html|cc) to the right handler."""

from argparse import Namespace

import pytest

from coursekit import cli


def _gen_args(*, quizzes=False, pages=False):
    return Namespace(quizzes=quizzes, pages=pages)


# ---- generator selection ----

def test_default_runs_both_quizzes_and_pages():
    cats = [g.category for g in cli._select_generators(_gen_args())]
    assert cats == ["quiz", "page"]        # quizzes first, pages last


def test_quizzes_narrows_to_quizzes_only():
    assert [g.category for g in cli._select_generators(_gen_args(quizzes=True))] == ["quiz"]


def test_pages_narrows_to_pages_only():
    assert [g.category for g in cli._select_generators(_gen_args(pages=True))] == ["page"]


# ---- subcommand routing ----

def _parse(*argv):
    return cli.build_parser().parse_args(list(argv))


def test_generate_routes_with_only_generation_flags():
    args = _parse("generate", "/course", "--pages", "--detail", "full")
    assert args.func is cli._cmd_generate
    assert args.path == "/course" and args.pages and args.detail == "full"


def test_emit_qti_routes_and_carries_bundle():
    args = _parse("emit", "qti", "/course/quizzes", "--bundle")
    assert args.func is cli._cmd_emit_qti and args.path == "/course/quizzes" and args.bundle


def test_emit_html_and_cc_route_to_their_handlers():
    assert _parse("emit", "html", "/p").func is cli._cmd_emit_html
    assert _parse("emit", "cc", "/p").func is cli._cmd_emit_cc


def test_emit_course_routes_to_the_course_cartridge():
    args = _parse("emit", "course", "/course")
    assert args.func is cli._cmd_emit_course and args.path == "/course"


def test_ingest_routes_with_raw():
    args = _parse("ingest", "/docs", "--raw")
    assert args.func is cli._cmd_ingest and args.path == "/docs" and args.raw


def test_bundle_belongs_to_emit_qti_only():
    # --bundle is not a generate flag any more; the coupling is structural
    with pytest.raises(SystemExit):
        _parse("generate", "/course", "--bundle")


def test_quizzes_and_pages_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        _parse("generate", "/course", "--quizzes", "--pages")


def test_a_bare_path_with_no_verb_errors():
    with pytest.raises(SystemExit):
        _parse("/course")


def test_emit_requires_a_target():
    with pytest.raises(SystemExit):
        _parse("emit")
