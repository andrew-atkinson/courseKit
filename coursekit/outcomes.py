"""Errors and notices as data — the reporting seam every interface renders (CORE-1.2, UX-8).

Library code never exits the process and never writes to the terminal. It raises a
`CoursekitError` (a stable `code`, structured `details`, an optional `hint`, and a `category`
that tells config problems from source problems from infrastructure), and it reports progress and
warnings as `Notice`s through `info` / `warn` / `error`.

Each notice goes to the current *sink*. The default sink is the terminal renderer in `console.py`,
so the CLI looks exactly as it always did. An app (or a test) wraps a run in `capture(sink=...)`
and gets back a `Report` of every notice; the context variable keeps concurrent runs apart.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Callable, Literal

Category = Literal["config", "source", "infra"]
Level = Literal["info", "warning", "error"]


class CoursekitError(Exception):
    """A problem the user can act on. `message` is the whole human sentence (what the CLI prints);
    `code` is stable for programs (`prompt.missing_placeholder`); `details` names the file, key, or
    value involved; `category` says whose problem it is — the user's settings or files (`config`),
    the course material (`source`), or the model/endpoint (`infra`)."""

    code = "coursekit.error"
    category: Category = "config"

    def __init__(self, message: str, *, code: str | None = None, details: dict | None = None,
                 hint: str | None = None, category: Category | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.details = details or {}
        self.hint = hint
        self.category = category or self.category


@dataclass(frozen=True)
class Notice:
    level: Level
    code: str
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class Report:
    """Every notice emitted during one captured run, in order."""

    notices: list[Notice] = field(default_factory=list)

    @property
    def warnings(self) -> list[Notice]:
        return [n for n in self.notices if n.level == "warning"]

    @property
    def errors(self) -> list[Notice]:
        return [n for n in self.notices if n.level == "error"]


def _terminal(notice: Notice) -> None:
    from coursekit import console
    console.render(notice)


_report: ContextVar[Report | None] = ContextVar("coursekit_report", default=None)
_sink: ContextVar[Callable[[Notice], None]] = ContextVar("coursekit_sink", default=_terminal)


def emit(level: Level, code: str, message: str, **details) -> Notice:
    notice = Notice(level, code, message, details)
    report = _report.get()
    if report is not None:
        report.notices.append(notice)
    _sink.get()(notice)
    return notice


def info(code: str, message: str, **details) -> Notice:
    return emit("info", code, message, **details)


def warn(code: str, message: str, **details) -> Notice:
    return emit("warning", code, message, **details)


def error(code: str, message: str, **details) -> Notice:
    """A non-fatal failure worth flagging (the run continues); raise `CoursekitError` to stop it."""
    return emit("error", code, message, **details)


@contextmanager
def capture(sink: Callable[[Notice], None] | None = None):
    """Collect every notice emitted inside the block into a `Report`. `sink` replaces the terminal
    (pass `lambda n: None` to silence it); omitted, notices still render as usual."""
    report = Report()
    r_token = _report.set(report)
    s_token = _sink.set(sink) if sink is not None else None
    try:
        yield report
    finally:
        _report.reset(r_token)
        if s_token is not None:
            _sink.reset(s_token)
