"""CORE-1.2 — errors and notices as data. The library raises `CoursekitError` and reports through
notices; an interface captures them (an app, a test) or lets the terminal render them (the CLI)."""

import pytest

from coursekit import cli, console, outcomes
from coursekit.outcomes import CoursekitError
from coursekit.pipeline import ModelLoadError


def test_capture_collects_notices_in_order_and_can_silence_the_terminal(capsys):
    with outcomes.capture(sink=lambda n: None) as report:
        outcomes.info("a.progress", "step one")
        outcomes.warn("a.skipped", "skipped X", item="X")
        outcomes.error("a.failed", "Y failed")
    assert [n.code for n in report.notices] == ["a.progress", "a.skipped", "a.failed"]
    assert [n.code for n in report.warnings] == ["a.skipped"] and report.warnings[0].details == {"item": "X"}
    assert [n.code for n in report.errors] == ["a.failed"]
    assert capsys.readouterr().out == ""                      # the sink replaced the terminal


def test_without_capture_notices_render_to_the_terminal_as_plain_text(capsys):
    outcomes.info("a.progress", "  [route] week-3: monolithic (fits)")     # brackets survive — no markup
    outcomes.warn("a.skipped", "  ⚠ skipped quiz week-3: broken")
    out = capsys.readouterr().out
    assert "  [route] week-3: monolithic (fits)\n" in out and "⚠ skipped quiz week-3: broken" in out


def test_capture_still_renders_unless_a_sink_is_given_and_ends_with_the_block(capsys):
    with outcomes.capture() as report:
        outcomes.info("a.in", "inside")
    outcomes.info("a.out", "outside")
    assert [n.code for n in report.notices] == ["a.in"]      # the report closed with the block
    assert "inside" in capsys.readouterr().out                # no sink given → still drawn


def test_an_error_carries_its_code_details_and_category():
    e = CoursekitError("the message", code="x.bad", details={"path": "p"}, hint="do this")
    assert (str(e), e.code, e.details, e.hint, e.category) == ("the message", "x.bad", {"path": "p"}, "do this", "config")
    m = ModelLoadError("model would not load")
    assert isinstance(m, CoursekitError) and m.category == "infra" and m.code == "model.unavailable"


def test_console_run_turns_an_error_into_a_message_and_exit_code(capsys):
    def config_problem():
        raise CoursekitError("fix your settings", code="x.config")

    def infra_problem():
        raise ModelLoadError("server down")

    assert console.run(config_problem) == 1
    assert console.run(infra_problem) == 2
    assert console.run(lambda: 0) == 0
    err = capsys.readouterr().err
    assert "fix your settings" in err and "server down" in err and "Traceback" not in err


def test_the_cli_reports_a_library_error_without_a_traceback(tmp_path, capsys):
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    (root / "quizzes" / "week-3").mkdir(parents=True)
    (root / "quizzes" / "week-3" / "bank.json").write_text("{}", encoding="utf-8")
    assert cli.main(["propose", str(root), "--grading"]) == 0
    capsys.readouterr()
    assert cli.main(["propose", str(root), "--grading"]) == 1          # second run refuses to clobber
    err = capsys.readouterr().err
    assert "already declares `grading:`" in err and "--force" in err


def test_library_code_never_exits_or_prints():
    """The pass criterion, enforced: outside the CLI, the terminal renderer, and per-module `main()`
    script entry points, no library function raises SystemExit or calls print()."""
    import ast
    import pathlib

    root = pathlib.Path(cli.__file__).parent
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if path.name in ("cli.py", "console.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}

        def in_entry_point(node):
            while node in parents:
                node = parents[node]
                if isinstance(node, ast.FunctionDef) and node.name == "main":
                    return True
                if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test):
                    return True
            return False

        for node in ast.walk(tree):
            bad = (isinstance(node, ast.Call) and ast.unparse(node.func) == "print") or \
                  (isinstance(node, ast.Raise) and node.exc is not None and "SystemExit" in ast.unparse(node.exc))
            if bad and not in_entry_point(node):
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert offenders == []
