"""Console output for the spine.

A tiny wrapper so the driver can print status without reaching into a generator's module. Rich
reads bracketed text like `[multiple_choice]` as style tags and silently eats it, so callers pass
`markup=False` for anything containing our own brackets.
"""

from rich.console import Console


def show(text, markup: bool = True) -> None:
    try:
        Console(soft_wrap=True).print(text, markup=markup)
    except Exception:
        print(text)
