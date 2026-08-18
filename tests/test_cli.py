"""CLI-level behaviour that isn't the pipeline itself: which generators a run drives, and that the
subcommand parser routes each phase (ingest / generate / emit qti|html|cc) to the right handler."""

from argparse import Namespace

import pytest

from coursekit import cli
from coursekit.generate.quiz import bank as bankmod


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
    args = _parse("generate", "/course", "--pages", "--function", "glossary", "--generator", "decompose")
    assert args.func is cli._cmd_generate
    assert args.path == "/course" and args.pages
    assert args.function == "glossary" and args.generator == "decompose"


def test_generate_page_axis_defaults():
    args = _parse("generate", "/course", "--pages")
    assert args.function == "teaching" and args.generator == "auto"   # sensible defaults


def test_generate_source_targets_one_document():
    args = _parse("generate", "--quizzes", "--source", "/c/week-3/reading.pdf")
    assert args.func is cli._cmd_generate and args.quizzes and args.source == "/c/week-3/reading.pdf"


def test_generate_rejects_the_removed_detail_flag():
    import pytest
    with pytest.raises(SystemExit):
        _parse("generate", "/course", "--pages", "--detail", "full")


def test_emit_qti_routes_and_carries_bundle():
    args = _parse("emit", "qti", "/course/quizzes", "--bundle")
    assert args.func is cli._cmd_emit_qti and args.path == "/course/quizzes" and args.bundle


def test_emit_html_and_cc_route_to_their_handlers():
    assert _parse("emit", "html", "/p").func is cli._cmd_emit_html
    assert _parse("emit", "cc", "/p").func is cli._cmd_emit_cc


def test_emit_course_routes_to_the_course_cartridge():
    args = _parse("emit", "course", "/course")
    assert args.func is cli._cmd_emit_course and args.path == "/course"


def test_evaluate_routes_with_week_filter():
    args = _parse("evaluate", "/course", "--week", "3")
    assert args.func is cli._cmd_evaluate and args.path == "/course" and args.week == ["3"]


def test_evaluate_defaults_to_both_quizzes_and_pages():
    args = _parse("evaluate", "/course")
    assert args.quizzes is False and args.pages is False   # neither flag => both facticity passes


def test_evaluate_all_is_the_umbrella_flag():
    args = _parse("evaluate", "/course", "--pages", "--all")
    assert args.pages and args.all
    assert _parse("evaluate", "/course").all is False   # default: facticity only, no deeper rubrics


def test_evaluate_quizzes_and_pages_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        _parse("evaluate", "/course", "--quizzes", "--pages")


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


# ---- generate's report-only quiz review (step 5) ----

def test_generate_runs_the_review_by_default():
    assert _parse("generate", "/course").review is True


def test_no_review_flag_disables_it():
    assert _parse("generate", "/course", "--no-review").review is False


class _FakeCritic:
    """FLAGs any question containing `marker`, else PASS (accepts seed, like the real provider)."""
    def __init__(self, marker=None):
        self.marker = marker

    def chat(self, *, model, messages, temperature=None, max_tokens=None, seed=None):
        q = messages[1]["content"]
        if self.marker and self.marker in q:
            return "VERDICT: FLAG\nCONCERN: not in the material\nFIX: ground it"
        return "VERDICT: PASS\nCONCERN:\nFIX:"


def _write_course(tmp_path):
    course = tmp_path / "course"
    (course / "output").mkdir(parents=True)
    (course / "output" / "week-3.md").write_text("loops and iteration", encoding="utf-8")
    qd = course / "quizzes" / "week-3"
    qd.mkdir(parents=True)
    bankmod.reset()
    bankmod.init("run", None, title="Week 3", source="week-3.md")
    bankmod.create_group("c1", "Loops", "multiple_choice")
    for i, lbl in enumerate("ABCD"):
        bankmod.put_variant(bankmod.MCVariant(
            group_id="c1", label=lbl, variant_summary=f"angle {lbl}",
            question_text=f"Q{lbl}: loops {'OUTOFSCOPE' if lbl == 'B' else 'here'}?",
            options=["one", "two", "three", "four"], correct_index=i))
    (qd / "bank.json").write_text(bankmod.get().model_dump_json(), encoding="utf-8")
    return course


def _review_args(course):
    return Namespace(path=str(course), week=None, weeks=None)


def test_review_quizzes_flags_and_writes_a_review(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MODEL_NAME", "m")
    course = _write_course(tmp_path)
    review, metrics = cli._review_quizzes(_review_args(course), _FakeCritic("OUTOFSCOPE"))
    out = capsys.readouterr().out
    assert "1 of 4 question(s) flagged" in out
    assert (course / "quizzes" / "quiz-review.md").exists()
    assert review is not None                              # returned for the run-store archive
    assert metrics == {"reviewed": 4, "flagged": 1}


def test_review_quizzes_skips_without_a_critic_model(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MODEL_NAME", raising=False)
    course = _write_course(tmp_path)
    result = cli._review_quizzes(_review_args(course), _FakeCritic("OUTOFSCOPE"))
    out = capsys.readouterr().out
    assert "skipping quiz review" in out
    assert not (course / "quizzes" / "quiz-review.md").exists()   # nothing written, generate unharmed
    assert result == (None, None)                                 # nothing to archive


def _write_page_course(tmp_path):
    from coursekit.generate.page import page as pagemod
    course = tmp_path / "course"
    (course / "output").mkdir(parents=True)
    (course / "output" / "week-3.md").write_text("loops and iteration", encoding="utf-8")
    pd = course / "pages" / "week-3"
    pd.mkdir(parents=True)
    pagemod.reset()
    pagemod.init("p1", None, title="Week 3", week_ref="week-3", slug="week-3")
    pagemod.put_block(pagemod.build_block("heading", block_id="h1", text="Loops", level=2))
    pagemod.put_block(pagemod.build_block(
        "paragraph", block_id="b2", text="Recursion OUTOFSCOPE is the tool this week."))
    (pd / "page.json").write_text(pagemod.get().model_dump_json(), encoding="utf-8")
    return course


def test_review_pages_flags_and_writes_a_review(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MODEL_NAME", "m")
    course = _write_page_course(tmp_path)
    cli._review_pages(_review_args(course), _FakeCritic("OUTOFSCOPE"))
    out = capsys.readouterr().out
    assert "section(s) flagged" in out
    assert (course / "pages" / "page-review.md").exists()
