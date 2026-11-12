"""CORE-4.2: concept maps, pages (every generator), assignments, and course overviews keep a record, and a
check says whether each still matches its course — including when what it was built from is itself out
of date (upstream). Offline: one scripted model plays every pass. See agent/core-4-design.md.
"""

import json
import shutil
from pathlib import Path

import pytest

from coursekit import outcomes, records
from coursekit.discover import find_units
from coursekit.generate import overview
from coursekit.generate.assignment import build as assignment
from coursekit.generate.page import build as pagebuild
from coursekit.generate.page import consolidate
from coursekit.generate.page.concept_map import concept_map_path
from coursekit.generate.quiz.generator import QuizGenerator
from coursekit.pipeline import run_unit
from coursekit.providers import OpenAICompatProvider
from coursekit.providers.base import Reply, ToolCall
from tests.test_quiz_records import _Endpoint

MAP = {"concepts": [{"name": "Object Literals", "gist": "named values"}, {"name": "Arrays", "gist": "lists"}],
       "enduring_understanding": "Structure lets a sketch scale."}


def _call(name, **args):
    return ToolCall(f"{name}-{len(json.dumps(args))}", name, json.dumps(args))


class Model:
    """Every pass, scripted: a concept map, a segmentation, a framing line, and the tool passes of a
    monolithic page, a decomposed or glossary page, and an assignment."""

    def __init__(self, concept_map=None):
        self.n, self.map, self.seen = 0, concept_map or MAP, []    # seen: each pass's opening messages

    def chat(self, *, model, messages, temperature=None, max_tokens=None):
        self.seen.append(json.loads(json.dumps(messages)))
        user = messages[-1]["content"]
        if user.startswith("Title:"):
            return "So let's get oriented."
        if user.startswith("CONCEPTS"):
            return "[1, 2]"
        return json.dumps(self.map)

    def chat_with_tools(self, *, model, messages, tools, temperature=None, max_tokens=None):
        names = {t["name"] if "name" in t else t["function"]["name"] for t in tools}
        turn = sum(m["role"] == "assistant" for m in messages)
        self.n += 1
        if turn == 0:
            self.seen.append(json.loads(json.dumps(messages)))
        if "finalize_page" in names:
            calls = [[_call("add_heading", block_id="h", text="Objects", level=2),
                      _call("add_details", block_id="d", summary="Predict", text="Ten.")],
                     [_call("finalize_page")]]
        elif "finalize_assignment" in names:
            calls = [[_call("set_assignment", title="Make a sketch", task="Use objects."),
                      _call("add_rubric_criterion", description="Works",
                            levels=[{"description": "Yes", "points": 10}, {"description": "No", "points": 0}])],
                     [_call("finalize_assignment")]]
        elif names == {"add_glossary"}:
            calls = [[_call("add_glossary", block_id="g", entries=[{"term": "Object", "definition": "Named values."}])]]
        else:                                                    # a decomposed page's frame, section, or close
            calls = [[_call("add_details", block_id=f"d{self.n}", summary="Predict", text="Ten.")]]
        if turn >= len(calls):
            return Reply(finish_reason="stop", content="done")
        return Reply(finish_reason="tool_calls", tool_calls=calls[turn])

    def append_assistant(self, messages, reply):
        messages.append({"role": "assistant", "content": reply.content or ""})

    def append_tool_results(self, messages, results):
        for _id, content in results:
            messages.append({"role": "tool", "content": content})

    def append_user(self, messages, text):
        messages.append({"role": "user", "content": text})


def _course(tmp_path):
    root = tmp_path / "course"
    vt = root / ".vtconfig"
    vt.mkdir(parents=True)
    (vt / "context.yaml").write_text("course_title: Creative Coding\nweeks:\n"
                                     "  week 7: {title: Objects, module: Data}\n"
                                     "  week 8: {title: Classes, module: Data}\n", encoding="utf-8")
    (vt / "voice.md").write_text("Say we and let's.", encoding="utf-8")
    (vt / "domain.md").write_text("p5.js creative coding.", encoding="utf-8")
    for n, body in (("7", "Object literals bundle named values.\n\nArrays hold many of them, in order.\n"),
                    ("8", "Classes make many objects of one shape.\n")):
        d = root / "output" / f"week {n}"
        d.mkdir(parents=True)
        (d / f"week-{n}.md").write_text(body * 20, encoding="utf-8")      # long enough to split in two
        (d / "1 lecture.knowledge.json").write_text(json.dumps(
            {"concepts": [{"name": "object literal", "why_it_matters": "bundles data"}]}), encoding="utf-8")
    return root


def _unit(root, n="7", subdir="quizzes"):
    (unit,) = find_units(root / "output" / f"week {n}" / f"week-{n}.md", subdir=subdir)
    return unit


def _quiet(fn, *a, **k):
    with outcomes.capture(sink=lambda n: None):
        return fn(*a, **k)


def _analyze(root, n="7", model=None):
    return _quiet(consolidate.analyze_unit, _unit(root, n), model or Model(), "m")


def _status(path, name=records.RECORD):
    return _quiet(records.status, path, name)


def _map_status(root, n="7"):
    return _status(root / ".vtconfig" / "concepts", f"week-{n}.record.json")


def _page(root, function="teaching", generator="auto"):
    return _quiet(pagebuild.build_page_unit, _unit(root, subdir="pages"), Model(), "m", function=function,
                  generator=generator)


# --------------------------------------------------------------------------- concept maps
def test_analyze_records_the_map_and_its_material_and_reads_current(tmp_path):
    root = _course(tmp_path)
    cm, path, spans = _analyze(root)
    assert spans == 2 and path == concept_map_path(root, "7")
    rec = records.load(path.parent, "week-7.record.json")
    assert [s["step"] for s in rec["steps"]] == ["analyze", "segment"] and rec["kind"] == "concept_map"
    assert set(rec["output"]) == {"week-7.yaml", "week-7.materials.json"}
    assert "output/week 7/1 lecture.knowledge.json" in rec["steps"][0]["read"]
    assert "output/week 7/week-7.md" not in rec["steps"][0]["read"]       # built from the knowledge, not the text
    assert _map_status(root) == records.Status("current")


def test_a_new_transcription_makes_the_map_stale_and_what_was_built_from_it_upstream_stale(tmp_path):
    root = _course(tmp_path)
    _analyze(root)
    quiz = _quiet(run_unit, _unit(root), OpenAICompatProvider(client=_Endpoint(), name="f"), "m", QuizGenerator())
    page = _page(root, generator="monolithic")
    assert _status(quiz.output_dir).state == _status(page.output_dir).state == "current"

    kf = root / "output" / "week 7" / "1 lecture.knowledge.json"   # the transcriber re-extracts the lecture
    kf.write_text(json.dumps({"concepts": [{"name": "object literal"}, {"name": "array"}]}), encoding="utf-8")
    st = _map_status(root)
    assert st.state == "stale" and st.reasons == ["analyze: output/week 7/1 lecture.knowledge.json changed since it was made"]
    for made in (quiz.output_dir, page.output_dir):              # neither reads knowledge.json itself…
        st = _status(made)
        assert st.state == "stale" and any(".vtconfig/concepts/week-7.yaml, which is itself stale" in r
                                           for r in st.reasons), st.reasons
    _analyze(root, model=Model({**MAP, "concepts": MAP["concepts"] + [{"name": "Array methods"}]}))
    assert _map_status(root).state == "current"                  # re-analyzed: the map is current again…
    for made in (quiz.output_dir, page.output_dir):              # …and what was built from the old one is stale
        assert ".vtconfig/concepts/week-7.yaml changed since it was made" in _status(made).reasons[0]


def test_editing_the_map_by_hand_reads_as_edited_and_stales_its_segmentation(tmp_path):
    root = _course(tmp_path)
    _analyze(root)
    p = concept_map_path(root, "7")
    p.write_text(p.read_text().replace("Arrays", "Arrays of objects"), encoding="utf-8")
    st = _map_status(root)
    assert st.edited and st.reasons[0] == "segment: .vtconfig/concepts/week-7.yaml changed since it was made"


# --------------------------------------------------------------------------- pages, by generator
@pytest.fixture
def analyzed(tmp_path):
    root = _course(tmp_path)
    _analyze(root)
    _analyze(root, "8")
    return root


def test_a_decomposed_page_records_a_step_per_section(analyzed):
    res = _page(analyzed, generator="decompose")
    rec = records.load(res.output_dir)
    assert [s["step"] for s in rec["steps"]] == ["frame", "section: Object Literals", "section: Arrays", "close"]
    assert rec["steps"][0]["options"] == {"text": "output/week 7/week-7.md", "generator": "decompose"}
    assert _status(res.output_dir) == records.Status("current")

    mp = analyzed / ".vtconfig" / "concepts" / "week-7.materials.json"   # one concept's material changes
    mats = json.loads(mp.read_text())
    mats["Arrays"] += "\n\nAnd they can be sorted."
    mp.write_text(json.dumps(mats), encoding="utf-8")
    st = _status(res.output_dir)
    assert st.state == "stale"
    assert st.reasons[0] == "section: Arrays: .vtconfig/concepts/week-7.materials.json changed since it was made"
    assert not any(r.startswith(("frame", "close", "section: Object")) for r in st.reasons)


@pytest.mark.parametrize("neighbours", [True, False])
def test_a_decomposed_page_made_without_neighbours_is_rebuilt_without_them(analyzed, neighbours):
    from coursekit.generate.page import decompose
    unit, m = _unit(analyzed), Model()
    _quiet(decompose.generate_page_decomposed, unit, m, "m", analyzed / "pages" / "week-7", neighbours=neighbours)
    sections = [x[1]["content"] for x in m.seen if x[1]["content"].startswith("Concept:")]
    assert all(("This section follows:" in s) == neighbours for s in sections) and sections
    assert records.load(analyzed / "pages" / "week-7")["steps"][0]["options"].get("neighbours", True) == neighbours
    assert _status(analyzed / "pages" / "week-7") == records.Status("current")


def test_a_concept_dropped_from_the_map_says_so(analyzed):
    res = _page(analyzed, generator="decompose")
    p = concept_map_path(analyzed, "7")
    p.write_text(p.read_text().replace("- name: Arrays\n  gist: lists\n", ""), encoding="utf-8")
    reasons = _status(res.output_dir).reasons
    assert "section: Arrays: can't be rebuilt from today's files (LookupError: 'Arrays' is no longer in the " \
           "concept map)" in reasons and any(r.startswith("frame: .vtconfig/concepts/week-7.yaml") for r in reasons)


@pytest.mark.parametrize("function,generator,steps", [
    ("teaching", "monolithic", ["generate"]), ("teaching", "decompose", None), ("glossary", "auto", ["glossary"]),
    ("overview", "auto", ["build"]), ("recap", "auto", ["build"])])
def test_every_page_reads_current_and_only_what_it_is_built_from_stales_it(analyzed, function, generator, steps):
    res = _page(analyzed, function, generator)
    rec = records.load(res.output_dir)
    assert steps is None or [s["step"] for s in rec["steps"]] == steps
    assert rec["kind"] == "page" and set(rec["output"]) == {"page.json"}
    assert _status(res.output_dir) == records.Status("current")

    ctx = analyzed / ".vtconfig" / "context.yaml"                # another unit's entry: nothing changes
    ctx.write_text(ctx.read_text() + "  week 9: {title: Sound}\n", encoding="utf-8")
    assert _status(res.output_dir).state == "current"

    text = analyzed / "output" / "week 7" / "week-7.md"          # the unit's text: stale if the page reads it
    text.write_text(text.read_text() + "One more thing.\n", encoding="utf-8")
    st = _status(res.output_dir)
    if generator == "decompose":                                 # built from the map's material: upstream
        assert st.state == "stale" and any("week-7.materials.json, which is itself stale" in r for r in st.reasons)
    elif function in ("overview", "recap"):                      # built from the concept map alone
        assert st.state == "current"
    else:
        assert st.state == "stale" and any("output/week 7/week-7.md changed" in r for r in st.reasons)


def test_a_model_free_page_is_checked_by_rebuilding_it(analyzed):
    res = _page(analyzed, "overview")
    assert records.load(res.output_dir)["steps"][0]["by"] == "coursekit"
    page = res.output_dir / "page.json"
    page.write_text(page.read_text().replace("Structure lets", "Structure helps"), encoding="utf-8")
    assert _status(res.output_dir) == records.Status("current", edited=True,
                                                     reasons=["edited by hand since coursekit last wrote it"])
    p = concept_map_path(analyzed, "7")
    p.write_text(p.read_text().replace("Structure lets a sketch scale.", "Data has shape."), encoding="utf-8")
    assert _status(res.output_dir).state == "stale"


def test_a_page_built_with_a_newer_prompt_reads_outdated(analyzed, tmp_path, monkeypatch):
    from coursekit import prompts
    res = _page(analyzed, generator="monolithic")
    shipped = tmp_path / "pkg" / "prompts"
    shutil.copytree(prompts._SHIPPED, shipped)
    monkeypatch.setattr(prompts, "_SHIPPED", shipped)
    monkeypatch.setattr(records, "_PACKAGE", tmp_path / "pkg")
    (shipped / "page" / "system.md").write_text((shipped / "page" / "system.md").read_text() + "\nBe brief.\n")
    st = _status(res.output_dir)
    assert st.state == "outdated" and st.reasons == ["generate: made with an older coursekit "
                                                     "(coursekit:page/system.md changed)"]


# --------------------------------------------------------------------------- assignments
def test_an_assignment_records_its_brief_and_scope(analyzed):
    unit = _unit(analyzed)
    a, problems = _quiet(assignment.build_assignment, unit, Model(), "m", unit.output_dir, scope="weeks 6 and 7")
    assert not problems
    rec = records.load(unit.output_dir)
    assert rec["kind"] == "assignment" and set(rec["output"]) == {"assignment.json"}
    assert rec["steps"][0]["options"] == {"text": "output/week 7/week-7.md", "scope": "weeks 6 and 7"}
    assert _status(unit.output_dir) == records.Status("current")
    text = analyzed / "output" / "week 7" / "week-7.md"
    text.write_text("Re-transcribed.\n", encoding="utf-8")
    assert _status(unit.output_dir).reasons == ["generate: output/week 7/week-7.md changed since it was made"]


def test_an_assignment_from_material_passed_in_is_unknown_not_current(analyzed):
    unit = _unit(analyzed)
    _quiet(assignment.build_assignment, unit, Model(), "m", unit.output_dir)
    _quiet(assignment.build_assignment, unit, Model(), "m", unit.output_dir, material="A reading on arrays.")
    assert _status(unit.output_dir).state == "unknown"


def test_each_recorded_brief_is_what_the_model_was_shown(analyzed):
    from coursekit.generate.page import decompose
    digest = records.digest
    m = Model()
    _quiet(consolidate.analyze_unit, _unit(analyzed), m, "m")
    rec = records.load(analyzed / ".vtconfig" / "concepts", "week-7.record.json")
    assert [s["brief"] for s in rec["steps"]] == [digest(m.seen[0]), digest(m.seen[1])]

    for generator in ("monolithic", "decompose"):
        m = Model()
        res = _quiet(pagebuild.build_page_unit, _unit(analyzed), m, "m", generator=generator)
        briefs = [s["brief"] for s in records.load(res.output_dir)["steps"]]
        if generator == "monolithic":
            assert briefs == [digest(m.seen[0])]
        else:                                                    # each step's passes, in the order sent
            plan = decompose.plan(_unit(analyzed))
            assert [digest(x) for x in m.seen] == [digest(x) for st in plan for x in decompose.step_messages(st)]
            assert briefs == [digest(decompose.step_messages(st)) for st in plan]

    m = Model()
    res = _quiet(pagebuild.build_page_unit, _unit(analyzed), m, "m", function="glossary")
    assert records.load(res.output_dir)["steps"][0]["brief"] == digest(m.seen)
    assert all("p5.js creative coding." in x[0]["content"] for x in m.seen)     # the course's domain, each pass

    unit, m = _unit(analyzed), Model()
    _quiet(assignment.build_assignment, unit, m, "m", unit.output_dir)
    assert records.load(unit.output_dir)["steps"][0]["brief"] == digest(m.seen[0])

    m = Model()
    _quiet(overview.generate_overviews, analyzed, provider=m, model="m")
    frames = {records.load(analyzed / "overview", n)["steps"][1]["brief"]
              for n in ("week-7-overview.record.json", "week-8-overview.record.json", "module-data-overview.record.json")}
    assert frames == {digest(x) for x in m.seen}


# --------------------------------------------------------------------------- course overviews
@pytest.mark.parametrize("framing", [True, False])
def test_each_course_overview_has_its_own_record(analyzed, framing):
    written = _quiet(overview.generate_overviews, analyzed, provider=Model(), model="m", framing=framing)
    out = analyzed / "overview"
    names = sorted(p.name for p in out.glob("*.record.json"))
    assert len(names) == len(written) == 3                         # two weeks and their module
    for n in names:
        steps = [s["step"] for s in records.load(out, n)["steps"]]
        assert steps == (["build", "frame"] if framing else ["build"])
        assert _status(out, n) == records.Status("current")

    p = concept_map_path(analyzed, "7")                           # week 7's big idea changes
    p.write_text(p.read_text().replace("Structure lets a sketch scale.", "Data has shape."), encoding="utf-8")
    states = {n.removesuffix(".record.json"): _status(out, n).state for n in names}
    assert sorted(states.values()) == ["current", "stale", "stale"]   # week 7 and the module; not week 8
    assert states[next(s for s in states if "8" in s)] == "current"
    (analyzed / "output" / "week 7" / "1 lecture.knowledge.json").write_text("{}", encoding="utf-8")
    assert _status(out, next(n for n in names if "8" in n)).state == "current"   # nor upstream of week 7's map
    assert not any(k.endswith("week-8.yaml") for k in records.load(out, next(n for n in names if "7" in n))["steps"][0]["read"])


def test_the_status_command_lists_every_record(analyzed, capsys):
    _page(analyzed, "overview")
    _quiet(overview.generate_overviews, analyzed, framing=False)
    import sys
    argv, sys.argv = sys.argv, ["records", str(analyzed)]
    try:
        assert records.main() == 0
    finally:
        sys.argv = argv
    out = capsys.readouterr().out
    assert ".vtconfig/concepts/week-7" in out and "week-7-overview " in out and "current" in out
    assert Path(analyzed / "overview").is_dir()
