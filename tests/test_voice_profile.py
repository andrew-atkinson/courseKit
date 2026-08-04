"""The instructor voice profile: `.vtconfig/voice.md` prose prepended to the PROSE generators (pages,
quizzes, and their fix loops) so output sounds like the instructor — but NOT to the critics, since
voice is a matter of tone, not correctness."""

from coursekit import courseconfig as cc
from coursekit.discover import find_units
from coursekit.generate.page import evaluate as pev
from coursekit.generate.page import page as pagemod
from coursekit.generate.page.fix import _fixer_body as page_fixer_body
from coursekit.generate.page.generator import PageGenerator
from coursekit.generate.quiz import bank as bankmod
from coursekit.generate.quiz import evaluate as ev
from coursekit.generate.quiz.fix import _fixer_body as quiz_fixer_body
from coursekit.generate.quiz.generator import QuizGenerator

VOICE = "Conversational and warm. Open with 'All right, let's…'. Keep the hedges: 'kind of', 'roughly'."


def _course(tmp_path, voice=None):
    root = tmp_path / "course"
    (root / ".vtconfig").mkdir(parents=True)
    if voice is not None:
        (root / ".vtconfig" / "voice.md").write_text(voice, encoding="utf-8")
    f = root / "output" / "week-3.md"
    f.parent.mkdir(parents=True)
    f.write_text("This week covers loops.", encoding="utf-8")
    return find_units(f)[0]


# ---------------------------------------------- courseconfig reads it

def test_voice_read_from_the_course(tmp_path):
    assert "hedges" in _course(tmp_path, voice=VOICE).config.voice


def test_voice_absent_is_empty(tmp_path):
    unit = _course(tmp_path)                  # marker, no voice.md
    assert unit.config.voice == ""
    assert cc.voice_preface("") == ""         # and no preface is produced


def test_preface_governs_tone_and_guards_precision():
    p = cc.voice_preface(VOICE)
    assert "INSTRUCTOR VOICE" in p and "Keep the hedges" in p
    assert "TONE" in p                         # tone only …
    assert "never overrides correctness" in p  # … subordinate to correctness
    assert "quiz question stem" in p           # explicit precision guard for assessed content


# ------------------------------- injected into BOTH generators' prompts

def test_voice_reaches_the_page_prompt(tmp_path):
    unit = _course(tmp_path, voice=VOICE)
    sys = PageGenerator().build_messages(unit, "TRANSCRIPT", unit.config)[0]["content"]
    assert "INSTRUCTOR VOICE" in sys and "Keep the hedges" in sys


def test_voice_reaches_the_quiz_prompt(tmp_path):
    unit = _course(tmp_path, voice=VOICE)
    sys = QuizGenerator().build_messages(unit, "TRANSCRIPT", unit.config)[0]["content"]
    assert "INSTRUCTOR VOICE" in sys and "Keep the hedges" in sys


def test_no_voice_no_preface_in_prompt(tmp_path):
    unit = _course(tmp_path)                  # no voice.md
    sys = PageGenerator().build_messages(unit, "TRANSCRIPT", unit.config)[0]["content"]
    assert "INSTRUCTOR VOICE" not in sys


def test_domain_leads_voice_when_both_present(tmp_path):
    unit = _course(tmp_path, voice=VOICE)
    (unit.course_root / ".vtconfig" / "domain.md").write_text("p5.js only.", encoding="utf-8")
    unit = find_units(unit.transcript_path)[0]     # reload so the new domain.md is picked up
    sys = PageGenerator().build_messages(unit, "TRANSCRIPT", unit.config)[0]["content"]
    assert sys.index("COURSE DOMAIN") < sys.index("INSTRUCTOR VOICE")   # domain, then voice, then rules


# ------------------------------- reaches the fix loops too

def test_voice_reaches_the_fix_prompts(tmp_path):
    unit = _course(tmp_path, voice=VOICE)
    assert "INSTRUCTOR VOICE" in page_fixer_body(unit.course_root)
    assert "INSTRUCTOR VOICE" in quiz_fixer_body(unit.course_root)


# ------------------------------- but NOT the critics (voice is not a correctness axis)

class _RecordingCritic:
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


def test_voice_does_not_reach_the_quiz_critic(tmp_path):
    unit = _course(tmp_path, voice=VOICE)
    rec = _RecordingCritic()
    ev.evaluate_bank(_one_group_bank(), "transcript", rec, "m", project_root=unit.course_root)
    assert "INSTRUCTOR VOICE" not in rec.system     # the critic judges correctness, not tone


def test_voice_does_not_reach_the_page_critic(tmp_path):
    unit = _course(tmp_path, voice=VOICE)
    pagemod.reset()
    pagemod.init("p1", None)
    pagemod.put_block(pagemod.build_block("paragraph", block_id="b1", text="A loop repeats a block."))
    rec = _RecordingCritic()
    pev.evaluate_page(pagemod.get(), "transcript", rec, "m", project_root=unit.course_root)
    assert "INSTRUCTOR VOICE" not in rec.system
