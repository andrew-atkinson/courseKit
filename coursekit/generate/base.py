"""The generator seam.

Every generator — quiz, page, and whatever comes next — has the same shape: reset per-unit state,
expose its tools, turn a transcript into messages, drive tool calls to a finalized artifact, and
report a result. `coursekit.pipeline` drives *this* protocol and knows nothing about any concrete
generator, which is what lets a second generator reuse the whole driver (the loop, the nudging, the
model-load handling, the per-unit reset) unchanged.

A generator owns three things the driver cannot know generically: which prompt `category` it uses,
what "finalized" means for its artifact, and how to phrase a corrective nudge in its own vocabulary.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from coursekit.discover import Unit


@dataclass
class RunResult:
    """The outcome of one unit. `counts` is generator-specific (quizzes count groups/variants;
    pages will count blocks), kept as a dict so the shared driver stays generic."""

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
        """Clear per-unit state (the IR singleton, tool state, call log) before a run."""
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

    def result(self, unit: Unit, out_dir: Path, reply: str) -> RunResult:
        """Summarise the finished (or unfinished) run."""
        ...
