import random
import string
import pytest
from coursekit.emit.gift import detect_gift_type, repchar, unrepchar

# Strings chosen to break GIFT. The first is the real one: every code-completion
# question in this project contains '=', which is a GIFT control character.
CORPUS = [
    "for (let x = 0; x < 10; x++)",
    "x <= 400",
    "a = b",
    "~tilde",
    "{braces}",
    "100% #hash",
    "colon: here",
    "arrow -> there",
    "back\\slash",
    "\\\\ double",
    "line1\nline2",
    "crlf\r\nhere",
    "]bracket[",
    "::title::",
    "#### general",
    "T",
    "TRUE",
    "plain text",
    "",
    "\\~ already escaped",
    "\\= already escaped",
]


@pytest.mark.parametrize("s", CORPUS)
def test_round_trip_corpus(s):
    assert unrepchar(repchar(s)) == s.replace("\r", "")


def test_round_trip_random():
    alphabet = string.printable
    rng = random.Random(20260716)
    for _ in range(2000):
        s = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        assert unrepchar(repchar(s)) == s.replace("\r", "")


def test_newline_escapes_to_literal_backslash_n():
    # Blank lines delimit questions, so a raw newline must not survive into the file.
    # repchar must produce backslash + 'n' (2 chars), not a newline.
    assert repchar("a\nb") == "a\\nb"
    assert "\n" not in repchar("a\nb")
    assert len(repchar("a\nb")) == 4


def test_carriage_return_is_dropped():
    assert repchar("a\r\nb") == "a\\nb"


def test_backslash_is_not_double_escaped():
    # Single pass: the backslash introduced by escaping '=' must not itself be escaped.
    assert repchar("=") == "\\="
    assert repchar("\\") == "\\\\"
    assert repchar("\\=") == "\\\\\\="


def test_control_chars_all_escaped():
    for ch in "\\#=~{}:":
        out = repchar(ch)
        assert out == "\\" + ch
        assert unrepchar(out) == ch


class TestDetectType:
    """Moodle's precedence, first match wins."""

    def test_description_when_no_braces(self):
        assert detect_gift_type("::T::Just a passage of text.") == "description"

    def test_essay_when_empty_braces(self):
        assert detect_gift_type("::T::Discuss. {}") == "essay"

    def test_numerical_on_leading_hash(self):
        assert detect_gift_type("::T::When? {#1822:5}") == "numerical"

    def test_multiple_choice_on_tilde(self):
        assert detect_gift_type("::T::Who? {=Grant ~no one}") == "multiple_choice"

    def test_matching_needs_both_equals_and_arrow(self):
        assert detect_gift_type("::T::Match. {=Canada -> Ottawa =Italy -> Rome}") == "matching"

    def test_true_false_uppercase_only(self):
        assert detect_gift_type("::T::Grant is buried here. {TRUE}") == "true_false"
        assert detect_gift_type("::T::Grant is buried here. {T}") == "true_false"
        assert detect_gift_type("::T::Grant is buried here. {F}") == "true_false"
        assert detect_gift_type("::T::Grant is buried here. {FALSE}") == "true_false"

    def test_lowercase_true_is_a_short_answer_not_an_error(self):
        # The silent-bug trap: {t} does not error, it becomes a short answer
        # whose accepted answer is the letter t.
        assert detect_gift_type("::T::Statement. {t}") == "short_answer"
        assert detect_gift_type("::T::Statement. {True}") == "short_answer"

    def test_short_answer_is_the_fallback(self):
        assert detect_gift_type("::T::Who? {=no one =nobody}") == "short_answer"

    def test_true_false_with_feedback(self):
        assert detect_gift_type("::T::S. {TRUE#wrong fb#right fb}") == "true_false"

    def test_general_feedback_does_not_affect_detection(self):
        assert detect_gift_type("::T::S. {TRUE####General note}") == "true_false"

    def test_escaped_tilde_does_not_become_multiple_choice(self):
        # THE test for running escapedchar_pre before detection. Moodle neutralises
        # escapes first, so a short answer containing a literal ~ stays a short answer.
        src = "::T::Name the operator. {=" + repchar("~") + "}"
        assert detect_gift_type(src) == "short_answer"

    def test_escaped_equals_in_short_answer_survives(self):
        src = "::T::Complete it. {=" + repchar("x = 1") + "}"
        assert detect_gift_type(src) == "short_answer"

    def test_escaped_arrow_source_is_still_matching(self):
        # '->' is not escapable, so it stays visible; that is correct.
        src = "::T::Match. {=a -> b =c -> d}"
        assert detect_gift_type(src) == "matching"

    def test_unbalanced_braces_raise(self):
        with pytest.raises(ValueError):
            detect_gift_type("::T::Broken {=a")
