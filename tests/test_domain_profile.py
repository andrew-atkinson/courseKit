"""The course domain profile: prose injected into every generator's prompt to keep output in the
right domain and correct a drifting source."""

from coursekit import courseconfig as cc
from coursekit.discover import find_units
from coursekit.generate.page.generator import PageGenerator
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
