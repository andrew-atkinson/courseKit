"""CLI-level behaviour that isn't the pipeline itself — which generators a run drives."""

from argparse import Namespace

import app


def _args(*, quizzes=False, pages=False, all=False):
    return Namespace(quizzes=quizzes, pages=pages, all=all)


def test_default_runs_both_quizzes_and_pages():
    cats = [g.category for g in app._select_generators(_args())]
    assert cats == ["quiz", "page"]        # quizzes first, pages last


def test_all_is_the_explicit_form_of_the_default():
    assert [g.category for g in app._select_generators(_args(all=True))] == ["quiz", "page"]


def test_quizzes_narrows_to_quizzes_only():
    assert [g.category for g in app._select_generators(_args(quizzes=True))] == ["quiz"]


def test_pages_narrows_to_pages_only():
    assert [g.category for g in app._select_generators(_args(pages=True))] == ["page"]


def test_both_flags_together_run_both():
    assert [g.category for g in app._select_generators(_args(quizzes=True, pages=True))] \
        == ["quiz", "page"]
