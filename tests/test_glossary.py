"""The glossary COMPANION page function (generate/page/glossary.py) + page-type-aware finalize.

Offline: a fake tool-calling provider scripts `add_glossary` calls; assembly/dedup are deterministic.
The point being pinned is the FUNCTION reframe — a glossary is a short reference artifact, so it needs
neither a teaching arc nor the retrieval foldout a teaching page requires.
"""

import json

import pytest

from coursekit.discover import find_units
from coursekit.generate.page import glossary
from coursekit.generate.page import page as pageir
from coursekit.generate.page import tools
from coursekit.providers.base import Reply, ToolCall


@pytest.fixture
def fresh():
    pageir.reset()
    tools.reset_state()
    yield
    pageir.reset()
    tools.reset_state()


class GlossaryProvider:
    """One `add_glossary` call per pass (from a queue of entry batches), then prose so the pass stops."""
    def __init__(self, *batches):
        self.batches = list(batches)
        self._i = 0

    def chat_with_tools(self, *, model, messages, tools, temperature=None, max_tokens=None):
        if messages and messages[-1].get("role") == "tool":     # already added this pass → stop
            return Reply(finish_reason="stop", content="done")
        entries = self.batches[min(self._i, len(self.batches) - 1)]
        self._i += 1
        if not entries:                                          # a flaky/empty pass
            return Reply(finish_reason="stop", content="(nothing)")
        return Reply(finish_reason="tool_calls",
                     tool_calls=[ToolCall("1", "add_glossary",
                                          json.dumps({"block_id": "g", "entries": entries}))])

    def append_assistant(self, messages, reply):
        messages.append({"role": "assistant", "content": reply.content or ""})

    def append_tool_results(self, messages, results):
        for _id, content in results:
            messages.append({"role": "tool", "content": content})

    def append_user(self, messages, text):
        messages.append({"role": "user", "content": text})


def _unit(tmp_path, body="Loops repeat a block. Arrays store ordered data.", *, quiz_yaml=""):
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    if quiz_yaml:
        (root / ".vtconfig" / "quiz.yaml").write_text(quiz_yaml, encoding="utf-8")
    f = root / "output" / "week-3.md"
    f.parent.mkdir(parents=True)
    f.write_text(body, encoding="utf-8")
    return find_units(f)[0]


# --------------------------------------------------------------- the tool surface

def test_glossary_pass_offers_only_add_glossary():
    names = {s["name"] for s in glossary._GLOSSARY_SPECS}
    assert names == {"add_glossary"}


# --------------------------------------------------------------- the function

def test_glossary_page_finalizes_without_a_retrieval_foldout(fresh, tmp_path):
    unit = _unit(tmp_path)
    prov = GlossaryProvider([{"term": "Loop", "definition": "Repeats a block of code."},
                             {"term": "Array", "definition": "An ordered collection of items."}])
    pg, problems = glossary.build_glossary_page(unit, prov, "m", unit.output_dir.parent / "wk3-glossary")

    assert problems == []                                    # finalized — no details block demanded
    assert pg.page_type == "glossary"
    assert pg.slug.endswith("-glossary")
    gloss = [b for b in pg.blocks.values() if b.kind == "glossary"]
    assert len(gloss) == 1 and len(gloss[0].entries) == 2    # one merged block, both terms
    assert not any(b.kind == "details" for b in pg.blocks.values())   # a reference page has no foldout


def test_glossary_dedups_terms_across_chunks(fresh, tmp_path):
    # tiny budget forces two chunks; the two passes share "Loop" (dedup) and add distinct terms (union)
    unit = _unit(tmp_path, "Loops repeat a block of code many times over.\n\n"
                           "Arrays store ordered data you can index into.",
                 quiz_yaml="max_pass_chars: 40\n")
    prov = GlossaryProvider(
        [{"term": "Loop", "definition": "first-wins definition"}],
        [{"term": "loop", "definition": "SECOND definition, discarded"},
         {"term": "Array", "definition": "An ordered collection."}])
    pg, problems = glossary.build_glossary_page(unit, prov, "m", unit.output_dir.parent / "g")

    assert problems == []
    entries = [b for b in pg.blocks.values() if b.kind == "glossary"][0].entries
    terms = {e.term.lower(): e.definition for e in entries}
    assert set(terms) == {"loop", "array"}                   # deduped across chunks
    assert terms["loop"] == "first-wins definition"          # first definition wins


def test_empty_glossary_does_not_finalize(fresh, tmp_path):
    unit = _unit(tmp_path)
    pg, problems = glossary.build_glossary_page(unit, GlossaryProvider([]), "m",
                                                unit.output_dir.parent / "g")
    assert problems                                          # a lone heading with no terms is not shippable


# --------------------------------------------------------------- page-type-aware validate_final

def test_reference_page_types_skip_the_retrieval_requirement(fresh):
    pageir.init(page_id="p", out_dir=None, title="T", page_type="glossary", slug="t")
    pageir.put_block(pageir.build_block("heading", block_id="h", text="Key Terms", role="review"))
    pageir.put_block(pageir.build_block("glossary", block_id="g",
                                        entries=[{"term": "X", "definition": "a thing"}]))
    assert pageir.validate_final() == []                     # glossary: no foldout required


def test_teaching_page_still_requires_the_retrieval_foldout(fresh):
    pageir.init(page_id="p", out_dir=None, title="T", page_type="week_intro", slug="t")
    pageir.put_block(pageir.build_block("heading", block_id="h", text="Loops", role="concept"))
    pageir.put_block(pageir.build_block("glossary", block_id="g",
                                        entries=[{"term": "X", "definition": "a thing"}]))
    problems = pageir.validate_final()
    assert any("retrieval" in p for p in problems)           # a teaching page must still retrieve
