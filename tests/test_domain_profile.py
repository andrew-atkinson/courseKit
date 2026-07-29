"""The course domain profile: prose injected into every generator's prompt to keep output in the
right domain and correct a drifting source."""

from coursekit import courseconfig as cc
from coursekit.discover import find_units
from coursekit.generate.page import evaluate as pev
from coursekit.generate.page import page as pagemod
from coursekit.generate.page.generator import PageGenerator
from coursekit.generate.quiz import bank as bankmod
from coursekit.generate.quiz import evaluate as ev
from coursekit.generate.quiz.generator import QuizGenerator


def _course(tmp_path, domain=None):
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    if domain is not None:
        (root / ".vtconfig" / "domain.md").write_text(domain, encoding="utf-8")
    f = root / "output" / "week-3.md"
    f.parent.mkdir(parents=True)
    f.write_text("This week covers loops.", encoding="utf-8")
    return find_units(f)[0]


# ---------------------------------------------- courseconfig reads it

def test_domain_read_from_the_course(tmp_path):
    unit = _course(tmp_path, domain="This course is p5.js (JavaScript), not Processing.")
    assert "p5.js" in unit.config.domain


def test_domain_absent_is_empty(tmp_path):
    unit = _course(tmp_path)                 # marker, no domain.md
    assert unit.config.domain == ""
    assert cc.domain_preface("") == ""       # and no preface is produced


def test_preface_is_a_correction_instruction():
    p = cc.domain_preface("This is p5.js, not Processing.")
    assert "COURSE DOMAIN" in p
    assert "This is p5.js, not Processing." in p
    assert "correct it silently" in p        # correction, not just description


# ------------------------------- injected into BOTH generators' prompts

def test_domain_reaches_the_page_prompt(tmp_path):
    unit = _course(tmp_path, domain="p5.js only. Never Processing or Java.")
    msgs = PageGenerator().build_messages(unit, "TRANSCRIPT", unit.config)
    sys = msgs[0]["content"]
    assert "COURSE DOMAIN" in sys
    assert "Never Processing or Java." in sys
    # the domain leads the system prompt, before the shipped rules
    assert sys.index("COURSE DOMAIN") < sys.index("THE ONLY WAY TO ADD CONTENT")


def test_domain_reaches_the_quiz_prompt(tmp_path):
    unit = _course(tmp_path, domain="p5.js only. Never Processing or Java.")
    msgs = QuizGenerator().build_messages(unit, "TRANSCRIPT", unit.config)
    assert "Never Processing or Java." in msgs[0]["content"]


def test_no_domain_no_preface_in_prompt(tmp_path):
    unit = _course(tmp_path)                 # no domain.md
    msgs = PageGenerator().build_messages(unit, "TRANSCRIPT", unit.config)
    assert "COURSE DOMAIN" not in msgs[0]["content"]


# ------------------------- broadened: content shape, not only knowledge-domain correction

def test_preface_frames_content_shape_and_still_corrects():
    p = cc.domain_preface("This course centers on photographs, not code.")
    assert "center on" in p                  # the profile can steer what a page foregrounds
    assert "correct it silently" in p        # and still carries the drift-correction job


def test_shipped_page_prompt_does_not_assume_code(tmp_path):
    # with no domain profile the prompt stays discipline-neutral: code is optional, not the spine
    unit = _course(tmp_path)
    sys = PageGenerator().build_messages(unit, "TRANSCRIPT", unit.config)[0]["content"]
    assert "worked examples, images, cases" in sys            # neutral framing, not code-first
    assert "only when the material actually contains code" in sys   # code is optional


def test_non_coding_domain_reaches_the_page_prompt(tmp_path):
    domain = ("This course teaches digital photography. Pages center on technique and image "
              "analysis, not code; there is no programming in this course.")
    unit = _course(tmp_path, domain=domain)
    sys = PageGenerator().build_messages(unit, "TRANSCRIPT", unit.config)[0]["content"]
    assert "COURSE DOMAIN" in sys
    assert "no programming in this course" in sys


# ---- the domain profile now reaches the CRITICS too (facticity), not just the generators ----

class _RecordingCritic:
    """Records the system message it is handed, then PASSes — to inspect what the critic sees."""
    def __init__(self):
        self.system = ""

    def chat(self, *, model, messages, temperature=None, max_tokens=None, seed=None):
        self.system = messages[0]["content"]
        return "VERDICT: PASS\nCONCERN:\nFIX:"


def _one_group_bank():
    bankmod.reset()
    bankmod.init("run", None)
    bankmod.create_group("c1", "Loops", "multiple_choice")
    bankmod.put_variant(bankmod.MCVariant(
        group_id="c1", label="A", variant_summary="angle", question_text="What does the loop do here?",
        options=["a", "b", "c", "d"], correct_index=0))
    return bankmod.get()


def test_critic_domain_preface_is_review_framed():
    assert cc.critic_domain_preface("") == ""
    p = cc.critic_domain_preface("This is a p5.js course.")
    assert "COURSE DOMAIN" in p and "p5.js" in p
    assert "do NOT flag" in p and "correct it silently" not in p   # review-framed, not generation


def test_domain_reaches_the_quiz_critic(tmp_path):
    unit = _course(tmp_path, domain="This course teaches p5.js; `width` and `height` are globals.")
    rec = _RecordingCritic()
    ev.evaluate_bank(_one_group_bank(), "transcript", rec, "m", project_root=unit.course_root)
    assert "COURSE DOMAIN" in rec.system and "p5.js" in rec.system


def test_domain_reaches_the_page_critic(tmp_path):
    unit = _course(tmp_path, domain="This course teaches p5.js; `width` is a global.")
    pagemod.reset()
    pagemod.init("p1", None)
    pagemod.put_block(pagemod.build_block("paragraph", block_id="b1", text="A loop repeats a block."))
    rec = _RecordingCritic()
    pev.evaluate_page(pagemod.get(), "transcript", rec, "m", project_root=unit.course_root)
    assert "COURSE DOMAIN" in rec.system and "p5.js" in rec.system


def test_no_domain_means_no_domain_block_in_the_critic(tmp_path):
    unit = _course(tmp_path)   # no domain.md
    rec = _RecordingCritic()
    ev.evaluate_bank(_one_group_bank(), "t", rec, "m", project_root=unit.course_root)
    assert "COURSE DOMAIN" not in rec.system
