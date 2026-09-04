"""Quiz groundedness (EVAL-15, quiz side) — offline, per-variant, with a fake critic (no model)."""

from coursekit.generate.quiz import groundedness as gnd
from coursekit.generate.quiz.groundedness_fixtures import MATERIAL, grounded_bank, model_supplied_bank


def _g(tag):
    return f"reasoning…\nGROUNDING: {tag} | because\n"


class _SeqCritic:
    """One queued reply per call (one call per variant); records the call count."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def chat(self, *, model, messages, temperature=None, max_tokens=None, seed=None):
        r = self.replies[self.calls] if self.calls < len(self.replies) else "GROUNDING: MODEL | ?"
        self.calls += 1
        return r


def test_parse_grounding_and_tag():
    assert gnd._parse_grounding("GROUNDING: GROUNDED | material says X") == ("grounded", "material says X")
    assert gnd._parse_grounding("GROUNDING: MODEL-SUPPLIED | not in source")[0] == "model"
    assert gnd._parse_grounding("GROUNDING: MODEL | outside knowledge")[0] == "model"
    assert gnd._parse_grounding("GROUNDING: GROUNDED") == ("grounded", "")   # no reason → still parses
    assert gnd._parse_grounding("**GROUNDING:** MODEL")[0] == "model"        # markdown emphasis
    assert gnd._parse_grounding("no verdict here") is None


def test_per_variant_classification_and_coverage():
    critic = _SeqCritic([_g("GROUNDED"), _g("MODEL")])
    bg = gnd.evaluate_bank_groundedness(grounded_bank(), MATERIAL, critic, "m")   # 2 variants
    assert critic.calls == 2 and bg.total == 2
    assert bg.coverage == 0.5 and len(bg.model_supplied) == 1


def test_unreadable_reply_drops_that_question():
    critic = _SeqCritic(["garbled, no grounding line", _g("GROUNDED")])
    bg = gnd.evaluate_bank_groundedness(grounded_bank(), MATERIAL, critic, "m")
    assert bg.total == 1                                     # the unparseable question is dropped


def test_critic_error_is_best_effort():
    class _Boom:
        def chat(self, **kw):
            raise RuntimeError("down")
    bg = gnd.evaluate_bank_groundedness(grounded_bank(), MATERIAL, _Boom(), "m")
    assert bg.total == 0 and bg.coverage == 0.0


def test_render_names_model_knowledge_and_lists_all_questions():
    critic = _SeqCritic([_g("GROUNDED"), _g("MODEL")])
    out = gnd.render_groundedness(gnd.evaluate_bank_groundedness(model_supplied_bank(), MATERIAL, critic, "x"))
    assert "answerable from the material" in out
    assert "model's knowledge" in out and "all 2 questions" in out


def test_evaluate_course_groundedness_writes_a_report(tmp_path):
    course = tmp_path / "course"
    (course / ".vtconfig").mkdir(parents=True)
    (course / "output").mkdir()
    (course / "output" / "week-3.md").write_text("loops material", encoding="utf-8")
    qd = course / "quizzes" / "week-3"
    qd.mkdir(parents=True)
    (qd / "bank.json").write_text(grounded_bank().model_dump_json(), encoding="utf-8")

    critic = _SeqCritic([_g("GROUNDED"), _g("MODEL")])
    results, out = gnd.evaluate_course_groundedness(course, provider=critic, model="m")
    assert results and out == course / "quizzes" / "quiz-groundedness.md" and out.exists()
    assert "answerable from the material" in out.read_text(encoding="utf-8")
