"""Deterministic synthesis of labelled flawed quiz questions, for calibrating the critic.

evaluate.py's critic is only as trustworthy as the statistics behind it, and hand-authoring flawed
questions does not scale past a couple dozen (the examples/synthetic hand-set is 24). This module
mass-produces labelled cases: from a few SOUND seed questions per domain — each grounded in that
domain's week transcript — it derives the four flaw types the critic exists to catch, with one exact
label per question. The label IS the construction, not a second file that can drift out of step.

What is mechanical vs authored, stated honestly:
  * wrong-answer    — a pure mutation: move the marked answer to a wrong option. Perfectly labelled.
  * garbled-syntax  — an ANSWER-CRITICAL span of the stem is mangled into a corrupted rendering
                      (`_garble`: mojibake), so the information needed to answer is present-but-
                      unreadable. Distinct from missing-context, where the information is simply absent.
                      (First pass unbalanced a bracket instead, which left the answer derivable — the
                      critic reasonably PASSed it, so the corruption now destroys answerability.)
  * missing-context — authored per seed: the answer-determining specifics are removed so the stem is
                      unanswerable. A believable version is domain-specific, so it is written.
  * out-of-scope    — an authored pool per domain: well-formed, correct questions about material the
                      week's transcript does not cover. "Outside the material" is a property of the
                      transcript, not a token you can corrupt.

Nothing here runs a model. The output is Bank objects + an expected-verdict map, ready for the critic
(evaluate.evaluate_bank) to be scored against; the scoring/stats harness is a separate step.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from coursekit.generate.quiz.bank import Bank, Group, MCVariant

# The four labels the critic is meant to catch, matching examples/synthetic/*/expected.json.
FLAWS = ("wrong-answer", "missing-context", "garbled-syntax", "out-of-scope")


@dataclass(frozen=True)
class Seed:
    """A sound multiple-choice question, structured so its flaw derivations are exact.

    `stripped` is the missing-context rendering: the same question with the answer-determining
    specifics removed, so it cannot be answered as written. `garble` is an answer-critical span that
    occurs verbatim in `text`; `_garble` mangles it into an unreadable rendering, so the garbled
    variant is unanswerable because the key content is corrupt (not merely ugly).
    """
    concept: str
    text: str
    options: tuple[str, ...]
    correct: int
    stripped: str
    garble: str

    def __post_init__(self) -> None:
        if not 0 <= self.correct < len(self.options):
            raise ValueError(f"seed {self.concept!r}: correct index {self.correct} out of range")
        if self.garble not in self.text:
            raise ValueError(f"seed {self.concept!r}: garble token {self.garble!r} not in text")
        if _garble(self.garble) == self.garble:
            raise ValueError(f"seed {self.concept!r}: garble token {self.garble!r} did not corrupt")


@dataclass(frozen=True)
class OutOfScope:
    """A well-formed, correct question about material outside the week's transcript."""
    concept: str
    text: str
    options: tuple[str, ...]
    correct: int


def _garble(token: str) -> str:
    """A corrupted-rendering artifact standing in for an answer-critical span — the real failure modes
    this project has hit (mojibake, a span that failed to render). The original characters do NOT
    survive, so the information the question needed is present-but-unreadable. A short run rather than
    one glyph so it reads as 'this text is corrupt', not a single typo."""
    return "�" * max(3, min(len(token), 7))


def _mc(group_id: str, text: str, options: tuple[str, ...], correct: int, concept: str) -> MCVariant:
    return MCVariant(
        group_id=group_id,
        label="A",
        question_text=text,
        variant_summary=concept,          # neutral; evaluate._format_question never shows the critic this
        text_format="plain",
        options=list(options),
        correct_index=correct,
    )


@dataclass(frozen=True)
class Case:
    variant: MCVariant
    verdict: str            # "PASS" | "FLAG"
    flaw: str | None


def _cases_for_seed(seed: Seed, gid) -> list[Case]:
    """The four labelled questions one sound seed yields: the sound original plus three flaws."""
    wrong = (seed.correct + 1) % len(seed.options)
    garbled = seed.text.replace(seed.garble, _garble(seed.garble), 1)
    return [
        Case(_mc(gid(), seed.text, seed.options, seed.correct, seed.concept), "PASS", None),
        Case(_mc(gid(), seed.text, seed.options, wrong, seed.concept), "FLAG", "wrong-answer"),
        Case(_mc(gid(), seed.stripped, seed.options, seed.correct, seed.concept), "FLAG", "missing-context"),
        Case(_mc(gid(), garbled, seed.options, seed.correct, seed.concept), "FLAG", "garbled-syntax"),
    ]


@dataclass(frozen=True)
class DomainSpec:
    name: str
    transcript: str
    seeds: tuple[Seed, ...]
    out_of_scope: tuple[OutOfScope, ...]


@dataclass(frozen=True)
class DomainSet:
    name: str
    transcript: str
    bank: Bank
    expected: dict[str, dict]


def synthesize_domain(spec: DomainSpec) -> DomainSet:
    """Turn a domain's seeds into a labelled Bank + expected-verdict map. Deterministic: same spec in,
    identical bank out (group ids are assigned in a fixed order)."""
    n = 0

    def gid() -> str:
        nonlocal n
        n += 1
        return f"c{n}"

    cases: list[Case] = []
    for seed in spec.seeds:
        cases += _cases_for_seed(seed, gid)
    for oos in spec.out_of_scope:
        cases.append(Case(_mc(gid(), oos.text, oos.options, oos.correct, oos.concept),
                          "FLAG", "out-of-scope"))

    groups: dict[str, Group] = {}
    expected: dict[str, dict] = {}
    for c in cases:
        g = c.variant.group_id
        groups[g] = Group(group_id=g, concept_title=c.variant.variant_summary,
                          question_type="multiple_choice", variants={"A": c.variant})
        expected[g] = {"verdict": c.verdict, "flaw": c.flaw}

    bank = Bank(run_id=f"synthetic-{spec.name}", title=f"Synthetic — {spec.name}",
                source="week-1.md", groups=groups)
    return DomainSet(spec.name, spec.transcript, bank, expected)


def synthesize_all() -> dict[str, DomainSet]:
    """Every domain's labelled set, keyed by name. This is what a scoring harness imports."""
    return {spec.name: synthesize_domain(spec) for spec in DOMAINS}


def write_fixtures(root: Path) -> list[Path]:
    """Dump the sets to disk in the examples/synthetic layout, for human inspection. Regenerable — the
    committed source of truth is this module, so the output dir is gitignored."""
    written: list[Path] = []
    for ds in synthesize_all().values():
        base = Path(root) / ds.name
        (base / "quizzes" / "week-1").mkdir(parents=True, exist_ok=True)
        (base / "output").mkdir(parents=True, exist_ok=True)
        bank_p = base / "quizzes" / "week-1" / "bank.json"
        bank_p.write_text(json.dumps(ds.bank.model_dump(), indent=2), encoding="utf-8")
        exp_p = base / "expected.json"
        exp_p.write_text(json.dumps(ds.expected, indent=2), encoding="utf-8")
        tx_p = base / "output" / "week-1.md"
        tx_p.write_text(ds.transcript, encoding="utf-8")
        written += [bank_p, exp_p, tx_p]
    return written


# ---------------------------------------------------------------------------
# The seed content. Each transcript matches examples/synthetic/<name>/output/week-1.md; the seeds and
# out-of-scope pools are grounded in it (in-scope answers derivable from the material; out-of-scope
# questions about material the transcript explicitly does not cover).
# ---------------------------------------------------------------------------

_CODING = DomainSpec(
    name="coding",
    transcript=(
        "# Week 1 — Loops in p5.js\n\n"
        "A `for` loop repeats a block a set number of times: `for (let i = 0; i < 5; i++) { ... }`.\n"
        "Initialization `let i = 0` runs once; the condition `i < 5` is checked before each pass and\n"
        "the loop runs while it is true; the increment `i++` runs after each pass. So this loop runs\n"
        "the body 5 times, with i taking 0, 1, 2, 3, 4. After it ends, i is 5 — the value that first\n"
        "failed the condition.\n\n"
        "We use i to vary something each pass — e.g.\n"
        "`for (let i = 0; i < 5; i++) { circle(i * 40, 50, 20); }` draws a row of five circles.\n"
    ),
    seeds=(
        Seed(
            concept="loop iteration count",
            text="How many times does the body of `for (let i = 0; i < 5; i++)` run?",
            options=("3", "4", "5", "6"), correct=2,
            stripped="How many times does the body of the loop run?",
            garble="i < 5",
        ),
        Seed(
            concept="final loop variable value",
            text="After `for (let i = 0; i < 5; i++) {}` finishes, what value does `i` hold?",
            options=("4", "5", "6", "0"), correct=1,
            stripped="After the loop finishes, what value does `i` hold?",
            garble="i < 5",
        ),
        Seed(
            # Replaced the old "increment timing" seed: its stripped stem was universally
            # answerable ("after each pass" regardless of the loop), so it was never really
            # missing-context. This one's answer depends on the loop's bound, which the stripped
            # version omits.
            concept="values the counter takes",
            text="Through `for (let i = 0; i < 5; i++)`, which values does `i` take inside the body?",
            options=("0, 1, 2, 3", "0, 1, 2, 3, 4", "1, 2, 3, 4, 5",
                     "0, 1, 2, 3, 4, 5"), correct=1,
            stripped="Which values does `i` take inside the loop body?",
            garble="i < 5",
        ),
        Seed(
            concept="loop drawing a row",
            text="`for (let i = 0; i < 5; i++) { circle(i * 40, 50, 20); }` draws how many circles?",
            options=("1", "4", "5", "10"), correct=2,
            stripped="The loop draws how many circles?",
            garble="i < 5",
        ),
    ),
    out_of_scope=(
        OutOfScope(
            concept="p5.FFT audio analysis",
            text="In `new p5.FFT(0.8, 512)`, what does the second argument set?",
            options=("Smoothing", "Frequency bins", "Sample rate", "Gain"), correct=1,
        ),
        OutOfScope(
            concept="mouse event handling",
            text="Which p5.js function runs once each time the mouse is pressed?",
            options=("draw()", "setup()", "mousePressed()", "loop()"), correct=2,
        ),
    ),
)

_BIOLOGY = DomainSpec(
    name="biology",
    transcript=(
        "# Week 1 — Moving substances across the cell membrane\n\n"
        "The membrane is selectively permeable. **Passive diffusion** is net movement of a substance\n"
        "from higher to lower concentration, down its gradient, using no energy. **Osmosis** is\n"
        "diffusion of water across a selectively permeable membrane from lower to higher solute\n"
        "concentration (water moves toward the more concentrated solution). **Facilitated diffusion**\n"
        "moves substances down their gradient through channel or carrier proteins, still with no\n"
        "energy. **Active transport** moves a substance *against* its gradient, from low to high\n"
        "concentration, and requires energy from ATP — the sodium–potassium pump is the classic\n"
        "example.\n"
    ),
    seeds=(
        Seed(
            concept="active transport energy",
            text="Active transport (moving a substance up its gradient) requires which of these?",
            options=("No energy at all", "Energy from ATP", "Only osmosis",
                     "A lower temperature"), correct=1,
            stripped="This process requires which of the following?",
            garble="up its gradient",
        ),
        Seed(
            # Stripped stem drops the process name, making it genuinely ambiguous across the
            # material: a *solute* diffuses toward lower concentration, whereas *water* in osmosis
            # moves toward higher — so without "osmosis"/"water" it cannot be answered.
            concept="osmosis direction",
            text="In osmosis, water crosses a selectively permeable membrane toward the side with "
                 "which solute level?",
            options=("Higher solute concentration", "Lower solute concentration",
                     "Equal on both sides", "Zero solute"), correct=0,
            stripped="A substance crosses the membrane toward the side with which solute level?",
            garble="selectively permeable membrane",
        ),
        Seed(
            concept="facilitated diffusion energy",
            text="Facilitated diffusion moves a substance down its gradient (through channel or "
                 "carrier proteins). How much energy does it need?",
            options=("Energy from ATP", "No energy", "Energy from sunlight",
                     "Energy from heat"), correct=1,
            stripped="How much energy does this kind of diffusion need?",
            garble="How much energy does it need",
        ),
        Seed(
            concept="passive diffusion direction",
            text="Passive diffusion is net movement of a substance (down its concentration gradient) "
                 "from where to where?",
            options=("Low to high concentration", "High to low concentration",
                     "Only across proteins", "Against the gradient"), correct=1,
            stripped="This movement goes from where to where?",
            garble="from where to where",
        ),
    ),
    out_of_scope=(
        OutOfScope(
            concept="glycolysis yield",
            text="In glycolysis, splitting one glucose molecule yields how many pyruvate molecules?",
            options=("One", "Two", "Three", "Six"), correct=1,
        ),
        OutOfScope(
            concept="DNA base pairing",
            text="In DNA, adenine pairs with which base?",
            options=("Guanine", "Cytosine", "Thymine", "Uracil"), correct=2,
        ),
    ),
)

_PRELAW = DomainSpec(
    name="prelaw",
    transcript=(
        "# Week 1 — Forming a contract\n\n"
        "A valid contract requires three elements: **offer**, **acceptance**, and **consideration**.\n"
        "An offer is a clear expression of willingness to contract on specified terms. Acceptance is\n"
        "the offeree's unqualified agreement to those terms; under the **mirror-image rule** it must\n"
        "match the offer exactly, and a reply that changes the terms is a counter-offer, not an\n"
        "acceptance. Consideration is the bargained-for exchange of value — each side must give\n"
        "something of value. This week covers formation only, not defences, breach, or remedies.\n"
    ),
    seeds=(
        Seed(
            concept="consideration definition",
            text="Consideration in contract law (as taught this week) is best described as what?",
            options=("A bargained-for exchange of value", "A written signature",
                     "A cooling-off period", "A government filing"), correct=0,
            stripped="It is best described as what?",
            garble="best described as what",
        ),
        Seed(
            concept="mirror-image counter-offer",
            text="Under the mirror-image rule, a reply that changes the offer's terms (rather than "
                 "matching them) is what?",
            options=("An acceptance", "A counter-offer", "Consideration",
                     "A binding contract"), correct=1,
            stripped="Is this reply an acceptance or a counter-offer?",
            garble="a reply that changes the offer's terms",
        ),
        Seed(
            concept="offer definition",
            text="An offer (in the formation of a contract) is best described as what?",
            options=("A clear expression of willingness to contract on specified terms",
                     "A completed payment", "A judge's ruling", "An exchange of value"), correct=0,
            stripped="How is it best described?",
            garble="best described as what",
        ),
        Seed(
            # Replaced the old "acceptance and the terms" seed: its stripped stem was still a
            # complete, answerable rule question. This one's answer depends on a specific reply that
            # the stripped version does not show.
            concept="acceptance validity in a scenario",
            text="A reply agrees to every one of the offer's terms without changing any of them. "
                 "Is it a valid acceptance?",
            options=("Yes, it is a valid acceptance", "No, it is a counter-offer",
                     "Only if notarized", "Only with new consideration"), correct=0,
            stripped="Is the reply a valid acceptance?",
            garble="every one of the offer's terms",
        ),
    ),
    out_of_scope=(
        OutOfScope(
            concept="expectation damages",
            text="Which measure of damages puts the injured party where they would have been had the "
                 "contract been performed?",
            options=("Reliance damages", "Expectation damages", "Nominal damages",
                     "Punitive damages"), correct=1,
        ),
        OutOfScope(
            concept="duress as a defence",
            text="A contract signed under an unlawful threat may be voidable on the ground of what?",
            options=("Consideration", "Duress", "Acceptance", "Offer"), correct=1,
        ),
    ),
)

_PHOTO = DomainSpec(
    name="photo",
    transcript=(
        "# Week 1 — Exposure: the three controls\n\n"
        "A photograph's brightness (exposure) is set by three controls together. **Aperture** is the\n"
        "lens opening, written as an f-number: a *smaller* f-number (f/2.8) is a wider opening letting\n"
        "in *more* light and giving shallow depth of field; a *larger* f-number (f/16) is a narrower\n"
        "opening letting in *less* light. **Shutter speed** is how long the sensor is exposed: longer\n"
        "lets in more light but adds motion blur. **ISO** is sensitivity: higher ISO is brighter but\n"
        "adds visible noise. This week covers only exposure — not composition, colour, or file\n"
        "formats.\n"
    ),
    seeds=(
        Seed(
            concept="aperture and light",
            text="A smaller f-number (for example f/2.8) means the lens opening is what?",
            options=("Narrower, letting in less light", "Wider, letting in more light",
                     "Closed completely", "Unrelated to light"), correct=1,
            stripped="The lens opening is what?",
            garble="smaller f-number",
        ),
        Seed(
            concept="shutter speed trade-off",
            text="A longer shutter speed (all else equal) lets in more light but introduces what?",
            options=("More noise", "Motion blur", "A shallower depth of field",
                     "A higher f-number"), correct=1,
            stripped="It lets in more light but introduces what?",
            garble="longer shutter speed",
        ),
        Seed(
            concept="ISO trade-off",
            text="Raising the ISO (the sensor's sensitivity) makes the image brighter but adds what?",
            options=("Motion blur", "Visible noise", "A wider aperture",
                     "Depth of field"), correct=1,
            stripped="Raising it makes the image brighter but adds what?",
            garble="Raising the ISO",
        ),
        Seed(
            concept="aperture and depth of field",
            text="A wider aperture (a smaller f-number such as f/2.8) gives which depth of field?",
            options=("Deep depth of field", "Shallow depth of field", "No depth of field",
                     "Depth of field is set by ISO"), correct=1,
            stripped="Which depth of field does it give?",
            garble="wider aperture",
        ),
    ),
    out_of_scope=(
        OutOfScope(
            concept="rule of thirds",
            text="The rule of thirds is a guideline primarily concerned with what?",
            options=("Exposure", "Composition and framing", "ISO noise",
                     "Shutter speed"), correct=1,
        ),
        OutOfScope(
            concept="RAW vs JPEG",
            text="Compared with JPEG, a RAW file primarily gives the photographer more of what?",
            options=("Shutter speed", "Editing latitude in post-processing", "Aperture range",
                     "ISO sensitivity"), correct=1,
        ),
    ),
)

DOMAINS: tuple[DomainSpec, ...] = (_CODING, _BIOLOGY, _PRELAW, _PHOTO)


if __name__ == "__main__":  # pragma: no cover - a convenience dump for eyeballing the fixtures
    import sys

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("examples/synthetic/generated")
    paths = write_fixtures(root)
    print(f"wrote {len(paths)} files under {root}")
