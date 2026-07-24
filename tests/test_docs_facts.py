"""Guardrail: keep factual claims in the docs true.

The test count in README.md went stale four times (295 -> 297 -> 315 -> 337) because it was a
number typed into prose, verified by hand or from memory. This makes it self-correcting: if the
README's claim and the live suite disagree, the suite fails and names the gap. A claim nobody can
forget to update is worth more than a more precise one nobody enforces.

Convention this enforces (see agent/architecture.md): a volatile number — a test count, a line
count — belongs in exactly ONE place, and if it appears in prose it must be under a test. Numbers
that are decorative (approximate line counts illustrating a ratio) are written with a `~` so they
read as snapshots, not asserted facts.
"""

import re
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


def _claimed_test_count() -> int | None:
    m = re.search(r"(\d+)\s+tests\b", README.read_text(encoding="utf-8"))
    return int(m.group(1)) if m else None


def _collected_test_count() -> int:
    """The live count, via a collection-only subprocess so it can't recurse into running."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT, capture_output=True, text=True,
    )
    m = re.search(r"(\d+)\s+tests?\s+collected", proc.stdout)
    if not m:
        pytest.skip(f"could not read a collected count from pytest output:\n{proc.stdout[-500:]}")
    return int(m.group(1))


def test_readme_states_a_test_count():
    assert _claimed_test_count() is not None, (
        "README.md no longer states a test count. If that is intentional, delete this test; "
        "otherwise restore the '<N> tests' line so the guardrail has something to check."
    )


def test_readme_test_count_is_current():
    claimed = _claimed_test_count()
    actual = _collected_test_count()
    assert claimed == actual, (
        f"README.md says {claimed} tests but the suite collects {actual}. "
        f"Update the number in README.md (the single source of truth for it)."
    )
