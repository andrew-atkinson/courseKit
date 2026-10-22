"""The terminal renderer — the one place coursekit's library output reaches the screen.

Library code reports through `coursekit.outcomes` (info / warn / error notices); this module is the
default sink that draws them. An app supplies its own sink instead. Rich reads bracketed text like
`[multiple_choice]` as style tags and silently eats it, so notice text is never parsed as markup —
colour comes from the notice's level.
"""

import sys

from rich.console import Console

_STYLE = {"warning": "yellow", "error": "red"}


def render(notice) -> None:
    style = _STYLE.get(notice.level)
    if style is None:
        print(notice.message)          # info: exactly what a plain print() always showed
        return
    try:
        Console(soft_wrap=True, highlight=False).print(notice.message, style=style, markup=False)
    except Exception:
        print(notice.message)


def run(entry) -> int:
    """Run a terminal entry point. A `CoursekitError` becomes its message on stderr and an exit code —
    2 for infrastructure (the model or endpoint), 1 otherwise — instead of a traceback."""
    from coursekit.outcomes import CoursekitError
    try:
        return entry()
    except CoursekitError as e:
        print(e.message, file=sys.stderr)
        return 2 if e.category == "infra" else 1
