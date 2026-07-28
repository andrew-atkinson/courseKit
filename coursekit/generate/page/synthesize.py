"""Deterministic synthesis of labelled flawed PAGE sections, for calibrating the page critic.

The page critic (page/evaluate.py) needs the same statistical grounding the quiz critic got: labelled
sections whose flaw IS the construction, not a guess. From a few sound FACTS per domain — grounded in
the same week transcripts the quiz set uses — it derives the three flaws the page critic exists to
catch, one exact label each:

  * contradiction — a claim that contradicts the material (an authored false version of a true fact).
  * garbled       — an answer-critical span mangled into unreadable mojibake (reuses quiz `_garble`).
  * out-of-scope  — a well-formed claim about material the week never taught (authored pool).

The true version of each fact is the sound (PASS) case. Everything is a paragraph block: facticity is a
property of the text, and per-block-kind formatting is already covered by the page evaluator's own
tests. Nothing here runs a model.
"""

from __future__ import annotations

from dataclasses import dataclass

from coursekit.generate.page.page import Page, build_block
from coursekit.generate.quiz.synthesize import DOMAINS as _QUIZ_DOMAINS
from coursekit.generate.quiz.synthesize import _garble

PAGE_FLAWS = ("contradiction", "garbled", "out-of-scope")

# Reuse the quiz set's transcripts verbatim — same material, so the page facts stay consistent with it.
_TRANSCRIPTS = {d.name: d.transcript for d in _QUIZ_DOMAINS}


@dataclass(frozen=True)
class Fact:
    true: str       # supported by the material -> a sound (PASS) section
    false: str      # contradicts the material  -> a contradiction section (FLAG)
    garble: str     # a span of `true` to mangle -> a garbled section (FLAG)

    def __post_init__(self) -> None:
        if self.garble not in self.true:
            raise ValueError(f"garble {self.garble!r} is not a span of the true statement")


@dataclass(frozen=True)
class PageSpec:
    name: str
    facts: tuple[Fact, ...]
    out_of_scope: tuple[str, ...]


@dataclass(frozen=True)
class PageDomain:
    name: str
    transcript: str
    page: Page
    expected: dict[str, dict]


def _para(bid: str, text: str):
    return build_block("paragraph", block_id=bid, text=text)


def synthesize_page_domain(spec: PageSpec) -> PageDomain:
    """Turn a domain's facts into a labelled Page (one paragraph block per case) + expected map."""
    blocks, expected = [], {}
    n = 0

    def bid() -> str:
        nonlocal n
        n += 1
        return f"b{n}"

    for fact in spec.facts:
        b = bid(); blocks.append(_para(b, fact.true)); expected[b] = {"verdict": "PASS", "flaw": None}
        b = bid(); blocks.append(_para(b, fact.false))
        expected[b] = {"verdict": "FLAG", "flaw": "contradiction"}
        garbled = fact.true.replace(fact.garble, _garble(fact.garble), 1)
        b = bid(); blocks.append(_para(b, garbled))
        expected[b] = {"verdict": "FLAG", "flaw": "garbled"}
    for claim in spec.out_of_scope:
        b = bid(); blocks.append(_para(b, claim))
        expected[b] = {"verdict": "FLAG", "flaw": "out-of-scope"}

    page = Page(page_id=f"synthetic-{spec.name}", title=f"Synthetic — {spec.name}",
                blocks={b.block_id: b for b in blocks})
    return PageDomain(spec.name, _TRANSCRIPTS[spec.name], page, expected)


# ---------------------------------------------------------------------------
# The facts. Each `true` is supported by that domain's transcript; each `false` contradicts it; each
# out-of-scope claim is correct-but-untaught (about material the week never covers).
# ---------------------------------------------------------------------------

_CODING = PageSpec(
    name="coding",
    facts=(
        Fact(true="A for loop with condition `i < 5` runs its body 5 times.",
             false="A for loop with condition `i < 5` runs its body 4 times.",
             garble="i < 5"),
        Fact(true="After `for (let i = 0; i < 5; i++)` finishes, `i` holds the value 5.",
             false="After `for (let i = 0; i < 5; i++)` finishes, `i` holds the value 4.",
             garble="i < 5"),
        Fact(true="The increment `i++` runs after each pass through the loop body.",
             false="The increment `i++` runs before each pass through the loop body.",
             garble="i++"),
    ),
    out_of_scope=(
        "A p5.FFT analyses audio into frequency bins.",
        "The mousePressed() function runs once each time the mouse is pressed.",
    ),
)

_BIOLOGY = PageSpec(
    name="biology",
    facts=(
        Fact(true="Passive diffusion moves a substance from higher to lower concentration and uses no energy.",
             false="Passive diffusion moves a substance from lower to higher concentration and requires ATP.",
             garble="higher to lower concentration"),
        Fact(true="Active transport moves a substance against its gradient and requires energy from ATP.",
             false="Active transport moves a substance down its gradient and requires no energy.",
             garble="against its gradient"),
        Fact(true="In osmosis, water moves toward the side with the higher solute concentration.",
             false="In osmosis, water moves toward the side with the lower solute concentration.",
             garble="higher solute concentration"),
    ),
    out_of_scope=(
        "Glycolysis splits one glucose molecule into two pyruvate molecules.",
        "In DNA, adenine pairs with thymine.",
    ),
)

_PRELAW = PageSpec(
    name="prelaw",
    facts=(
        Fact(true="A valid contract requires offer, acceptance, and consideration.",
             false="A valid contract requires only an offer and a signature.",
             garble="offer, acceptance, and consideration"),
        Fact(true="Under the mirror-image rule, a reply that changes the offer's terms is a counter-offer, not an acceptance.",
             false="Under the mirror-image rule, a reply that changes the offer's terms is still a valid acceptance.",
             garble="mirror-image rule"),
        Fact(true="Consideration is the bargained-for exchange of value between the parties.",
             false="Consideration is a required government filing that registers the contract.",
             garble="bargained-for exchange of value"),
    ),
    out_of_scope=(
        "Expectation damages put the injured party where they would have been had the contract been performed.",
        "A contract signed under duress may be voidable.",
    ),
)

_PHOTO = PageSpec(
    name="photo",
    facts=(
        Fact(true="A smaller f-number means a wider aperture that lets in more light.",
             false="A smaller f-number means a narrower aperture that lets in less light.",
             garble="smaller f-number"),
        Fact(true="A longer shutter speed lets in more light but can add motion blur.",
             false="A longer shutter speed lets in less light and reduces motion blur.",
             garble="longer shutter speed"),
        Fact(true="Raising the ISO makes the image brighter but adds visible noise.",
             false="Raising the ISO makes the image darker and reduces noise.",
             garble="Raising the ISO"),
    ),
    out_of_scope=(
        "The rule of thirds is a guideline for composition and framing.",
        "A RAW file gives more editing latitude than a JPEG.",
    ),
)

DOMAINS: tuple[PageSpec, ...] = (_CODING, _BIOLOGY, _PRELAW, _PHOTO)


def synthesize_all_pages() -> dict[str, PageDomain]:
    """Every domain's labelled page set, keyed by name — what the page scorecard imports."""
    return {s.name: synthesize_page_domain(s) for s in DOMAINS}


# ===========================================================================
# The HARD set — subtle flaws, to find where the critic breaks (the blatant set scores 100%).
#
#   * near-miss       — a plausible-but-wrong claim: an off-by-one, a reversed direction phrased
#                       naturally, "a small amount of energy" where the answer is none. Contradicts the
#                       material, but quietly.
#   * beyond-material — a claim that is TRUE in general but the week's material never teaches (the
#                       sodium/potassium 3:2 stoichiometry, `for...of`, offer revocation). Per "trust
#                       ONLY the material" it must FLAG — this is where a model is tempted to pass what
#                       it happens to know. The likely failure mode, and the point of the set.
#
# Sound cases include statements phrased NEAR a misconception, to test precision under pressure.
# ===========================================================================

HARD_FLAWS = ("near-miss", "beyond-material")


@dataclass(frozen=True)
class HardCase:
    text: str
    flaw: str | None       # None => a sound (PASS) section


@dataclass(frozen=True)
class HardSpec:
    name: str
    cases: tuple[HardCase, ...]


def synthesize_hard_page_domain(spec: HardSpec) -> PageDomain:
    blocks, expected = [], {}
    for i, c in enumerate(spec.cases, 1):
        b = f"b{i}"
        blocks.append(_para(b, c.text))
        expected[b] = {"verdict": "PASS" if c.flaw is None else "FLAG", "flaw": c.flaw}
    page = Page(page_id=f"synthetic-hard-{spec.name}", title=f"Synthetic hard — {spec.name}",
                blocks={b.block_id: b for b in blocks})
    return PageDomain(spec.name, _TRANSCRIPTS[spec.name], page, expected)


_HARD_CODING = HardSpec("coding", (
    HardCase("A for loop runs its body once for each value of the counter from its start up to but "
             "not including its limit.", None),
    HardCase("In `for (let i = 0; i < 5; i++)`, the condition is checked before each pass and the loop "
             "stops when it becomes false.", None),
    HardCase("A for loop that starts at 0 with the condition `i <= 5` runs its body 5 times.",
             "near-miss"),   # i = 0..5 is SIX passes
    HardCase("After `for (let i = 0; i < 5; i++)` finishes, `i` holds 4 — the last value used in the "
             "body.", "near-miss"),   # i is 5 after, the value that failed the condition
    HardCase("A `for...of` loop iterates directly over an array's elements without an index counter.",
             "beyond-material"),   # true JS, but only the classic for loop is taught
    HardCase("You can stop a for loop early with a `break` statement.", "beyond-material"),
))

_HARD_BIOLOGY = HardSpec("biology", (
    HardCase("Facilitated diffusion moves substances down their gradient through channel or carrier "
             "proteins without using energy.", None),
    HardCase("Osmosis moves water across a selectively permeable membrane from lower to higher solute "
             "concentration.", None),
    HardCase("In osmosis, water moves toward the side with the higher water concentration.",
             "near-miss"),   # higher solute = LOWER water; reversed, but plausible
    HardCase("Facilitated diffusion moves substances through proteins using a small amount of ATP.",
             "near-miss"),   # it uses NO energy; "a small amount" is the trap
    HardCase("The sodium–potassium pump moves three sodium ions out of the cell and two potassium ions "
             "in during each cycle.", "beyond-material"),   # true, but the 3:2 detail isn't taught
    HardCase("Aquaporins are channel proteins that greatly speed water's movement across the membrane.",
             "beyond-material"),   # true, but aquaporins are never mentioned
))

_HARD_PRELAW = HardSpec("prelaw", (
    HardCase("Acceptance must be an unqualified agreement to the offer's terms and, under the "
             "mirror-image rule, must match the offer exactly.", None),
    HardCase("Consideration is the bargained-for exchange of value, with each side giving something of "
             "value.", None),
    HardCase("Under the mirror-image rule, an acceptance may add minor new terms as long as it agrees "
             "to the main ones.", "near-miss"),   # exact match required; adding terms = counter-offer
    HardCase("Consideration requires that both sides exchange things of roughly equal value.",
             "near-miss"),   # adequacy is NOT required, only bargained-for value
    HardCase("An offer can be revoked by the offeror at any time before it has been accepted.",
             "beyond-material"),   # true, but revocation isn't in a formation-basics week
    HardCase("Under the Statute of Frauds, certain contracts must be in writing to be enforceable.",
             "beyond-material"),   # true, but untaught
))

_HARD_PHOTO = HardSpec("photo", (
    HardCase("A smaller f-number corresponds to a wider aperture, letting in more light and giving a "
             "shallower depth of field.", None),
    HardCase("A longer shutter speed lets in more light but can introduce motion blur.", None),
    HardCase("A larger f-number gives a wider aperture and a shallower depth of field.", "near-miss"),
    # larger f-number = NARROWER aperture, DEEPER depth of field — reversed
    HardCase("Raising the ISO increases the sensor's sensitivity and slightly sharpens the image.",
             "near-miss"),   # raising ISO adds NOISE, it does not sharpen
    HardCase("Using a tripod lets you use a longer shutter speed without motion blur from camera shake.",
             "beyond-material"),   # true, but tripods/camera-shake aren't in the material
    HardCase("In aperture-priority mode, the camera sets the shutter speed once you choose the aperture.",
             "beyond-material"),   # true, but shooting modes aren't taught
))

HARD_DOMAINS: tuple[HardSpec, ...] = (_HARD_CODING, _HARD_BIOLOGY, _HARD_PRELAW, _HARD_PHOTO)


def synthesize_all_hard_pages() -> dict[str, PageDomain]:
    """The hard (subtle-flaw) page set, keyed by name."""
    return {s.name: synthesize_hard_page_domain(s) for s in HARD_DOMAINS}
