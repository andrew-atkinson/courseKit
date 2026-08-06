"""Which page generator drives a TEACHING page — monolithic vs decompose — decided by the program.

The user picks the FUNCTION and the quality bar; the program picks the mechanism. A single monolithic
pass is fine for a short, few-concept week; a long week, a week with many concepts, or one whose
largest single concept span alone overruns a pass, crowds that one pass — so it routes to the
decomposed generator (per-concept passes + sub-splitting). Deterministic and MEASURED, no model call:
three independent triggers (length · concept count · largest span), any one of which forces decompose.

The thresholds are first estimates — TUNE them per model against the run-store (the project's
"measure, don't assume" rule); they are overridable in page.yaml. On this ~26B local model a focused
pass handled ~30K chars while a monolithic page degraded on long / voice-heavy weeks.
"""

from dataclasses import dataclass

MONO_CHAR_BUDGET = 24000        # whole-week text a single monolithic pass covers reliably
MONO_CONCEPT_BUDGET = 7         # sections one pass can juggle before it starts shedding rules


@dataclass(frozen=True)
class PageSignals:
    """The measured shape of a week, from the transcript + concept map + per-concept material."""
    transcript_chars: int
    concept_count: int
    largest_span_chars: int


def signals_for(transcript: str, concept_map, materials: dict | None) -> PageSignals:
    """Measure a week: total text, number of concepts, and the largest single concept's material."""
    concepts = concept_map.concepts if (concept_map and concept_map.concepts) else []
    spans = [len(materials.get(c.name, "")) for c in concepts] if materials else []
    return PageSignals(len(transcript), len(concepts), max(spans) if spans else 0)


def decompose_reasons(sig: PageSignals, *, char_budget: int = MONO_CHAR_BUDGET,
                      concept_budget: int = MONO_CONCEPT_BUDGET, pass_budget: int | None = None) -> list[str]:
    """Every reason this week overruns a single monolithic pass (empty = monolithic is fine)."""
    reasons = []
    if sig.transcript_chars > char_budget:
        reasons.append(f"week is {sig.transcript_chars} chars (> {char_budget})")
    if sig.concept_count > concept_budget:
        reasons.append(f"{sig.concept_count} concepts (> {concept_budget})")
    if pass_budget and sig.largest_span_chars > pass_budget:
        reasons.append(f"largest concept span is {sig.largest_span_chars} chars (> per-pass {pass_budget})")
    return reasons


def choose_generator(sig: PageSignals, *, char_budget: int = MONO_CHAR_BUDGET,
                     concept_budget: int = MONO_CONCEPT_BUDGET, pass_budget: int | None = None) -> str:
    """'decompose' if any signal overruns a monolithic pass, else 'monolithic'."""
    over = decompose_reasons(sig, char_budget=char_budget, concept_budget=concept_budget,
                             pass_budget=pass_budget)
    return "decompose" if over else "monolithic"
