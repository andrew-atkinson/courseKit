"""A run owns its state (CORE-3): two jobs in one process never touch each other's artifact.

Two halves. The guard keeps module-level state out of `coursekit/generate/` for good, as
`test_outcomes.py` keeps prints out of library code. The proof runs two jobs on separate threads, made
to take strict turns at every model call, and checks each is byte-identical to the same job run alone.
"""

import ast
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import coursekit
from coursekit.discover import find_units
from coursekit.generate.page.generator import PageGenerator
from coursekit.generate.quiz.generator import QuizGenerator
from coursekit.pipeline import run_unit
from coursekit.providers.base import Reply, ToolCall

GENERATE = Path(coursekit.__file__).parent / "generate"
_MUTATORS = {"append", "extend", "insert", "pop", "remove", "clear", "update", "setdefault", "add",
             "discard", "popitem", "sort", "reverse"}


# ------------------------------------------------------------------ the guard

def _module_state_problems(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    where = lambda n: f"{path.relative_to(GENERATE.parent)}:{n.lineno}"
    module_names = {t.id for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))
                    for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
    classes = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    imported = {(a.asname or a.name).split(".")[0] for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))
                for a in n.names}
    problems = []
    for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        local = {a.arg for a in fn.args.args + fn.args.kwonlyargs} | {
            t.id for n in ast.walk(fn) if isinstance(n, (ast.Assign, ast.AnnAssign, ast.For, ast.With))
            for t in ast.walk(n) if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store)}
        shared = module_names - local
        for n in ast.walk(fn):
            if isinstance(n, ast.Global):
                problems.append(f"{where(n)} `global {', '.join(n.names)}`")
            elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in _MUTATORS
                  and isinstance(n.func.value, ast.Name) and n.func.value.id in shared):
                problems.append(f"{where(n)} mutates module-level `{n.func.value.id}`")
            elif (isinstance(n, ast.Subscript) and isinstance(n.ctx, (ast.Store, ast.Del))
                  and isinstance(n.value, ast.Name) and n.value.id in shared):
                problems.append(f"{where(n)} writes into module-level `{n.value.id}`")
            elif (isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store) and isinstance(n.value, ast.Name)
                  and n.value.id in (classes | imported) - local):
                problems.append(f"{where(n)} sets `{n.value.id}.{n.attr}`, state shared by every run")
    return problems


def test_nothing_under_generate_keeps_state_in_a_module():
    problems = [p for f in sorted(GENERATE.rglob("*.py")) for p in _module_state_problems(f)]
    assert problems == [], ("a run's state belongs in its draft or tool session, passed as an argument "
                            "(see agent/core-3-design.md §4):\n  " + "\n  ".join(problems))


def test_the_guard_sees_each_way_state_gets_shared(tmp_path):
    bad = tmp_path / "generate" / "bad.py"
    bad.parent.mkdir()
    bad.write_text("import pathlib\nclass Tools: pass\n_log = None\nchecklist = []\ncache = {}\n"
                   "def a():\n    global _log\n    _log = 1\n"
                   "def b(x):\n    checklist.append(x)\n    cache[x] = 1\n"
                   "def c(d):\n    Tools.shared = d\n    pathlib.default = d\n"
                   "def fine(checklist):\n    checklist.append(1)\n    local = {}\n    local['k'] = 1\n")
    global GENERATE
    real, GENERATE = GENERATE, tmp_path / "generate"
    try:
        found = _module_state_problems(bad)
    finally:
        GENERATE = real
    assert [p.split(" ", 1)[1] for p in found] == [
        "`global _log`", "mutates module-level `checklist`", "writes into module-level `cache`",
        "sets `Tools.shared`, state shared by every run", "sets `pathlib.default`, state shared by every run"]


# ------------------------------------------------------------------ the proof

class _Turns:
    """Lets exactly one job act between two model calls, in strict rotation, so their tool calls interleave
    one for one. A job that has finished drops out of the rotation."""

    def __init__(self, jobs: int):
        self.cond, self.jobs, self.turn, self.done, self.trace = threading.Condition(), jobs, 0, set(), []

    def _pass_on(self, me: int) -> None:
        for step in range(1, self.jobs + 1):
            nxt = (me + step) % self.jobs
            if nxt not in self.done:
                self.turn = nxt
                break
        self.cond.notify_all()

    def take(self, me: int, first: bool) -> None:
        with self.cond:
            if not first:
                self._pass_on(me)
            assert self.cond.wait_for(lambda: self.turn == me, timeout=10), "jobs stopped taking turns"
            self.trace.append(me)

    def finish(self, me: int) -> None:
        with self.cond:
            self.done.add(me)
            if self.turn == me:
                self._pass_on(me)


class _Scripted:
    """One tool call per model turn, from a script, then prose. Thread-local by construction: one per job."""

    def __init__(self, script, turns: _Turns, me: int):
        self.script, self.turns, self.me, self.calls = list(script), turns, me, 0

    def chat_with_tools(self, *, model, messages, tools, **kw):
        self.turns.take(self.me, first=self.calls == 0)
        self.calls += 1
        if not self.script:
            return Reply(finish_reason="stop", content="done")
        name, args = self.script.pop(0)
        return Reply(finish_reason="tool_calls", tool_calls=[ToolCall(str(self.calls), name, json.dumps(args))])

    def append_assistant(self, messages, reply):
        messages.append({"role": "assistant", "content": reply.content or ""})

    def append_tool_results(self, messages, results):
        messages.extend({"role": "tool", "content": c} for _, c in results)

    def append_user(self, messages, text):
        messages.append({"role": "user", "content": text})

    def check_fit(self, model):
        return None, ""


def _quiz_script(tag):
    variant = lambda label, correct: ("add_multiple_choice_variant", {
        "group_id": tag, "variant_label": label, "question_text": f"Question {label} about {tag}?",
        "variant_summary": f"{tag} angle {label}", "options": ["a", "b", "c", "d"], "correct_index": correct})
    return [("create_checklist", {"descriptions": [f"{tag} group"]}),
            ("create_question_group", {"group_id": tag, "concept_title": tag, "question_type": "multiple_choice"}),
            variant("A", 0), variant("B", 0), variant("B", 1), ("mark_complete", {"index": 1, "completion_notes": tag}),
            ("get_bank_report", {}), ("finalize_bank", {})]


def _page_script(tag):
    return [("add_heading", {"block_id": f"{tag}-h", "text": tag, "role": "concept"}),
            ("add_paragraph", {"block_id": f"{tag}-p", "text": f"About `{tag}`."}),
            ("add_paragraph", {"block_id": f"{tag}-p", "text": f"More about `{tag}`, revised."}),
            ("add_details", {"block_id": f"{tag}-d", "summary": "Predict?", "text": tag}),
            ("get_page_report", {}), ("finalize_page", {})]


JOBS = {"quiz": (QuizGenerator, _quiz_script, "quizzes"), "page": (PageGenerator, _page_script, "pages")}


def _course(root: Path, tag: str, theme: str) -> Path:
    (root / ".vtconfig").mkdir(parents=True)
    (root / ".vtconfig" / "style.yaml").write_text(f"theme: {theme}\n", encoding="utf-8")
    doc = root / "output" / "week-3.md"
    doc.parent.mkdir()
    doc.write_text(f"This unit is about {tag}.", encoding="utf-8")
    return doc


def _files(d: Path) -> dict:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


def _run(kind, tasks, where: Path, together: bool):
    """Run each (tag, theme) job; `together` puts them on threads taking turns, else one after another."""
    make, script, subdir = JOBS[kind]
    turns = _Turns(len(tasks) if together else 1)

    def job(i, tag, theme):
        unit = find_units(_course(where / tag / "course", tag, theme))[0]
        try:
            res = run_unit(unit, _Scripted(script(tag), turns, i if together else 0), "m", make())
        finally:
            turns.finish(i if together else 0)
            if not together:
                turns.done.clear()
        return res.finalized, res.counts, _files(unit.course_root / subdir)

    if not together:
        return [job(i, *t) for i, t in enumerate(tasks)], turns.trace
    with ThreadPoolExecutor(len(tasks)) as pool:
        return [f.result() for f in [pool.submit(job, i, *t) for i, t in enumerate(tasks)]], turns.trace


@pytest.mark.parametrize("kind", ["quiz", "page"])
def test_two_jobs_taking_turns_on_threads_each_match_running_alone(tmp_path, kind):
    tasks = [("loops", "terminal"), ("arrays", "bauhaus")]
    alone, _ = _run(kind, tasks, tmp_path / "alone", together=False)
    together, trace = _run(kind, tasks, tmp_path / "together", together=True)

    assert trace[:6] == [0, 1, 0, 1, 0, 1]           # the two jobs really did alternate, call by call
    assert all(finalized for finalized, _, _ in alone)
    assert together == alone                          # every file of each job, byte for byte
