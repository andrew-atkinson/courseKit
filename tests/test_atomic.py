"""CORE-4.2: every file coursekit writes is written whole or not at all, through one helper.

A write made to fail partway (a full disk, a crash) leaves the previous file whole and no temporary file
behind — checked for each writer, by making every file write fail after half its bytes, so a writer that
wrote its file in place would leave half a file and fail here. A guard fails if code under coursekit/
writes a file any other way.
"""

import ast
import contextlib
import itertools
import json
import pathlib
import zipfile
from pathlib import Path

import pytest

from coursekit import atomic, records, settings
from coursekit.generate.page.concept_map import Concept, ConceptMap, save_concept_map


def _snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


@contextlib.contextmanager
def disk_full(monkeypatch, at: int = 0):
    """The `at`-th file write (or zip member) from here on fails partway: half its bytes land, then an
    OSError, as on a full disk. The writes before it succeed."""
    count = itertools.count()
    def half(write):
        def broken(self, data, *a, **k):
            if next(count) < at:
                return write(self, data, *a, **k)
            write(self, data[: len(data) // 2], *a, **k)
            raise OSError("No space left on device")
        return broken
    with monkeypatch.context() as m:
        m.setattr(pathlib.Path, "write_text", half(pathlib.Path.write_text))
        m.setattr(pathlib.Path, "write_bytes", half(pathlib.Path.write_bytes))
        m.setattr(zipfile.ZipFile, "writestr", half(zipfile.ZipFile.writestr))
        yield


def test_the_helper_replaces_whole_or_leaves_the_old_file(tmp_path, monkeypatch):
    p = atomic.write(tmp_path / "a" / "f.json", "old")
    assert p.read_text() == "old" and atomic.write(p, b"new").read_bytes() == b"new"
    with pytest.raises(RuntimeError), atomic.replacing(p) as tmp:
        tmp.write_text("half")
        raise RuntimeError("the writer failed")
    with disk_full(monkeypatch), pytest.raises(OSError):
        atomic.write(p, "a much longer replacement")
    assert _snapshot(tmp_path) == {"a/f.json": b"new"}           # the old file, whole; no temporary


# --------------------------------------------------------------------------- each writer
def _mc(bank, gid, i):
    return bank.MCVariant(group_id=gid, label="ABCD"[i], question_text=f"Which is right ({gid}{i})?",
                          variant_summary=f"angle {i}", options=["a", "b", "c", "d"], correct_index=i)


def _quiz(tmp, title="Week 7"):
    from coursekit.generate.quiz import bank
    d = bank.BankDraft.adopt(bank.Bank(run_id="run", title=title), tmp / "quizzes" / "week-7")
    for gid in ("g1", "g2"):
        d.create_group(gid, f"Concept {gid}", "multiple_choice")
        for i in range(4):
            d.put_variant(_mc(bank, gid, i))
    d.finalize(seed=7)
    return d


def _finalize(tmp):
    d = _quiz(tmp)
    d.bank.title = "Week 7, renamed"                             # what finalize writes next: all four files
    return lambda: d.finalize(seed=8)


def _reorder(tmp):
    from coursekit.generate.quiz import bank
    _quiz(tmp)
    return lambda: bank.set_order(tmp / "quizzes" / "week-7", ["g2", "g1"])


def _autosave_page(tmp):
    from coursekit.generate.page import page as P
    d = P.PageDraft.new("p", tmp / "pages" / "week-7", title="Week 7")
    d.put_block(P.build_block("heading", block_id="h1", text="Loops", level=2))
    return lambda: d.put_block(P.build_block("heading", block_id="h2", text="Arrays", level=2))


def _write_page(tmp):
    from coursekit.generate.overview import build_week_overview
    from coursekit.generate.page.build import _write_page
    cm = ConceptMap(week="7", enduring_understanding="Structure scales.", concepts=[Concept(name="Objects")])
    _write_page(build_week_overview("CC101", "7", "Objects", "", cm), tmp / "pages" / "week-7-overview", tmp)
    cm.concepts.append(Concept(name="Arrays"))
    return lambda: _write_page(build_week_overview("CC101", "7", "Objects", "", cm),
                               tmp / "pages" / "week-7-overview", tmp)


def _overview(tmp):
    from coursekit.generate.overview import _render_overview, build_module_overview
    _render_overview(build_module_overview("CC101", "Data", [("7", "Objects", "")]), tmp / "overview", tmp)
    return lambda: _render_overview(build_module_overview("CC101", "Data", [("7", "Objects", "x"),
                                                                            ("8", "Classes", "")]),
                                    tmp / "overview", tmp)


def _assignment(tmp):
    from coursekit.generate.assignment.build import AssignmentDraft
    def draft(title):
        d = AssignmentDraft(assignment_id="a", slug="week-7-assignment", week_ref="week-7", default_points=10,
                            out_dir=tmp / "assignments" / "week-7")
        d.set_brief(title, "Make a sketch.", "", "", None, "online_upload")
        d.add_criterion("Works", [{"description": "Yes", "points": 10}, {"description": "No", "points": 0}],
                        "", None)
        return d
    (tmp / "assignments" / "week-7").mkdir(parents=True)
    draft("Objects").finalize()
    return lambda: draft("Objects and arrays").finalize()


def _concept_map(tmp):
    p = tmp / ".vtconfig" / "concepts" / "week-7.yaml"
    save_concept_map(ConceptMap(week="7", concepts=[Concept(name="Objects")]), p)
    return lambda: save_concept_map(ConceptMap(week="7", concepts=[Concept(name="Arrays")]), p)


def _setting(tmp):
    (tmp / ".vtconfig").mkdir(parents=True)
    settings.write(tmp, "quiz", {"eu_question": True})
    return lambda: settings.write(tmp, "quiz", {"eu_question": False})


def _record(tmp):
    d = tmp / "quizzes" / "week-7"
    d.mkdir(parents=True)
    (d / "bank.json").write_text("{}")
    step = dict(kind="quiz", unit="7", by="model", outputs=("bank.json",), brief="sha256:x", read={})
    records.write_step(d, step="generate", fresh=True, **step)
    return lambda: records.write_step(d, step="eu", **step)


def _package(tmp):
    from coursekit.emit import qti
    d = _quiz(tmp)
    quiz = json.loads((d.out_dir / "quiz.json").read_text())
    qti.write_imscc(d.bank, quiz, tmp / "export" / "week-7.zip")
    d.bank.title = "Week 7, renamed"
    return lambda: qti.write_imscc(d.bank, quiz, tmp / "export" / "week-7.zip")


WRITERS = {"quiz finalize": _finalize, "set_order": _reorder, "page autosave": _autosave_page,
           "model-free page": _write_page, "course overview": _overview, "assignment": _assignment,
           "concept map": _concept_map, "setting": _setting, "record": _record, "export package": _package}


@pytest.mark.parametrize("name", WRITERS)
def test_a_write_that_fails_partway_leaves_each_file_old_or_new_never_half(name, tmp_path, monkeypatch):
    # what a successful write leaves; then the same write failing at its first, second, … file
    WRITERS[name](tmp_path / "ok")()
    after = _snapshot(tmp_path / "ok")
    for at in itertools.count():
        d = tmp_path / str(at)
        again = WRITERS[name](d)
        before = _snapshot(d)
        with disk_full(monkeypatch, at):
            try:
                again()
                break                                            # it wrote fewer files than `at`
            except OSError:
                pass
        now = _snapshot(d)
        assert set(now) <= set(before) | set(after), f"left behind: {set(now) - set(before) - set(after)}"
        half = [f for f in now if now[f] not in (before.get(f), after.get(f))]
        assert not half, f"{name}, failing at write {at}: half-written {half}"
    assert at > 0


def test_a_quizs_record_is_written_after_the_quiz_it_describes(tmp_path, monkeypatch):
    from tests.test_quiz_records import _course, _generate
    order = []
    write = atomic.write
    monkeypatch.setattr(atomic, "write", lambda p, d: order.append(Path(p).name) or write(p, d))
    _generate(_course(tmp_path))
    last = {n: i for i, n in enumerate(order)}
    first = {n: i for i, n in reversed(list(enumerate(order)))}
    # the first record follows the finished quiz, and the last follows the last change to it
    assert first["quiz.json"] < first["record.json"] and max(last["bank.json"], last["quiz.json"]) < last["record.json"]


# --------------------------------------------------------------------------- the guard
_WRITE_CALLS = {"write_text", "write_bytes", "rename", "symlink_to", "hardlink_to", "touch"}
_WRITE_FUNCS = {"os.replace", "os.rename", "os.link", "shutil.copy", "shutil.copy2", "shutil.copyfile",
                "shutil.copytree", "shutil.move", "json.dump", "yaml.dump", "yaml.safe_dump", "pickle.dump"}


def _mode(call, at):
    args = call.args[at:at + 1] + [k.value for k in call.keywords if k.arg == "mode"]
    return args[0].value if args and isinstance(args[0], ast.Constant) else ("r" if not args else "?")


def unsafe_writes(source: str) -> list[str]:
    """Every way `source` writes a file other than through coursekit.atomic, as `line: code`."""
    tree = ast.parse(source)
    tmps = {item.optional_vars.id for n in ast.walk(tree) if isinstance(n, ast.With) for item in n.items
            if isinstance(item.optional_vars, ast.Name) and ast.unparse(item.context_expr).startswith("atomic.replacing(")}
    bad = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        func = ast.unparse(n.func)
        attr = n.func.attr if isinstance(n.func, ast.Attribute) else func
        if attr in _WRITE_CALLS or func in _WRITE_FUNCS and (func != "yaml.safe_dump" or len(n.args) > 1):
            bad.append(n)
        elif attr == "replace" and len(n.args) == 1 and not n.keywords:       # Path.replace, not str.replace
            bad.append(n)
        elif func == "open" and not set(_mode(n, 1)) <= set("rbta") or attr == "open" and func != "open" \
                and isinstance(n.func, ast.Attribute) and not set(_mode(n, 0)) <= set("rbta"):
            bad.append(n)
        elif func in ("zipfile.ZipFile", "ZipFile") and _mode(n, 1) != "r" and not (
                n.args and isinstance(n.args[0], ast.Name) and n.args[0].id in tmps):
            bad.append(n)
    return [f"{n.lineno}: {ast.unparse(n)}" for n in bad]


def test_nothing_under_coursekit_writes_a_file_except_through_the_helper():
    root = Path(__file__).resolve().parent.parent / "coursekit"
    found = {str(p.relative_to(root)): w for p in sorted(root.rglob("*.py")) if p.name != "atomic.py"
             for w in [unsafe_writes(p.read_text(encoding="utf-8"))] if w}
    assert not found, f"write these through coursekit.atomic: {found}"


@pytest.mark.parametrize("code", [
    'p.write_text("x")', "p.write_bytes(b)", "os.replace(a, b)", "tmp.replace(target)", "p.rename(q)",
    'open(p, "w")', 'open(p, mode="wb")', 'p.open("w")', "shutil.copy2(a, b)", "json.dump(d, f)",
    "yaml.safe_dump(d, f)", 'zipfile.ZipFile(out, "w")', 'open(p, "r+")'])
def test_the_guard_catches_each_way_of_writing(code):
    assert unsafe_writes(code)


@pytest.mark.parametrize("code", [
    's.replace("a", "b")', "p.read_text()", "open(p)", 'open(log, "a")', 'p.open("rb")',
    "yaml.safe_dump(d)", "zipfile.ZipFile(path)",
    'with atomic.replacing(out) as tmp, zipfile.ZipFile(tmp, "w") as z:\n    pass'])
def test_the_guard_allows_reading_appending_and_the_helper(code):
    assert not unsafe_writes(code)
