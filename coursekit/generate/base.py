"""The generator seam.

Every generator — quiz, page, and whatever comes next — has the same shape: start a fresh run per
unit, expose its tools, turn a transcript into messages, drive tool calls to a finalized artifact, and
report a result. `coursekit.pipeline` drives *this* protocol and knows nothing about any concrete
generator, which is what lets a second generator reuse the whole driver (the loop, the nudging, the
model-load handling, the per-unit reset) unchanged.

A generator owns three things the driver cannot know generically: which prompt `category` it uses,
what "finalized" means for its artifact, and how to phrase a corrective nudge in its own vocabulary.

A run's state lives on the generator instance, never in a module: `reset` builds the unit's draft (the
artifact being built and where it saves) and its tool session (`dispatch.ToolSession`), so two
generators can run at once without touching each other's artifact (CORE-3; tests/test_isolation.py).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from coursekit.discover import Unit


@dataclass
class RunResult:
    """The outcome of one unit. `counts` is generator-specific (quizzes count groups/variants;
    pages count blocks), kept as a dict so the shared driver stays generic."""

    unit: Unit
    finalized: bool
    output_dir: Path
    counts: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    reply: str = ""

    # Named accessors the quiz path and the summary table have always used.
    @property
    def n_groups(self) -> int:
        return self.counts.get("groups", 0)

    @property
    def n_variants(self) -> int:
        return self.counts.get("variants", 0)


@runtime_checkable
class Generator(Protocol):
    """What the driver needs from a generator. The quiz generator is the reference implementation;
    the page generator is the second. Concrete generators wrap their own IR + tools + prompts."""

    category: str          # prompts/<category>/ and .vtconfig/<category>.yaml
    artifacts_subdir: str  # the output tree under the course: "quizzes", "pages", …

    def reset(self, unit: Unit, out_dir: Path) -> None:
        """Start this unit's run: a fresh draft and tool session (with its call log), replacing the last
        unit's. The driver calls it first; nothing else works on a generator until it has."""
        ...

    def tool_specs(self) -> list:
        """The tool schemas sent to the model."""
        ...

    def run_tool_calls(self, calls) -> list[tuple[str, str]]:
        """Dispatch a turn's tool calls; return (tool_call_id, result_text) pairs."""
        ...

    def build_messages(self, unit: Unit, transcript: str, cfg) -> list[dict]:
        """The initial chat messages for one unit."""
        ...

    def is_finalized(self) -> bool:
        """Has the artifact been committed? The driver checks this rather than trusting the model."""
        ...

    def nudge(self, *, stalled: bool) -> str:
        """A corrective user turn in the generator's own vocabulary, quoting true progress."""
        ...

    def postprocess(self, unit: Unit, provider, model, cfg, transcript: str) -> None:
        """Optional deterministic step AFTER the main loop finalizes — e.g. a focused second pass with
        a restricted tool set. A generator with nothing to do returns immediately."""
        ...

    def result(self, unit: Unit, out_dir: Path, reply: str) -> RunResult:
        """Summarise the finished (or unfinished) run."""
        ...
