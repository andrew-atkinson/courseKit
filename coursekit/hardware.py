"""Local-model RAM fit checks.

Extracted from quizbot (which had copied it from the videotranscriber's vt_common) so both
tools share one implementation instead of drifting. macOS-only (sysctl + vm_stat + the `lms`
CLI); everything degrades to "unknown" elsewhere rather than raising.

Reached through `Provider.check_fit()` rather than called directly: a hosted endpoint has no
local RAM budget, so the question is only meaningful for a local provider.

We only *advise* on fit — LM Studio's real load threshold depends on context size and
overhead we can't see, so the authoritative signal is LM Studio actually refusing the load
(translated in pipeline.loop). This just gives an upfront heads-up.
"""

import json
import shutil
import subprocess
from pathlib import Path

# LM Studio's own budget is looser, so keep this a warning threshold, not a hard gate.
SAFETY_FACTOR = 0.7
_LMS_FALLBACK = str(Path.home() / ".lmstudio" / "bin" / "lms")


def get_memory_info() -> tuple[float | None, float | None]:
    """(total_gb, available_gb) via sysctl + vm_stat. Either may be None on failure."""
    total_gb = None
    try:
        r = subprocess.run(["sysctl", "-n", "hw.memsize"],
                           capture_output=True, text=True, timeout=5)
        total_gb = int(r.stdout.strip()) / (1024 ** 3)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass

    available_gb = None
    try:
        r = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
        lines = r.stdout.splitlines()
        page_size = int(lines[0].split("page size of")[1].split("bytes")[0].strip())
        stats = {}
        for line in lines[1:]:
            key, _, value = line.partition(":")
            value = value.strip().rstrip(".")
            if value.isdigit():
                stats[key.strip()] = int(value)
        reclaimable = sum(stats.get(k, 0) for k in
                          ("Pages free", "Pages inactive", "Pages speculative", "Pages purgeable"))
        available_gb = reclaimable * page_size / (1024 ** 3)
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        pass

    return total_gb, available_gb


def _lms(*args) -> list[dict]:
    lms = shutil.which("lms") or _LMS_FALLBACK
    try:
        r = subprocess.run([lms, *args], capture_output=True, text=True, timeout=15)
        data = json.loads(r.stdout)
        return data if isinstance(data, list) else []
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []


def list_lm_models() -> list[dict]:
    """Downloaded LM Studio models as dicts with modelKey/sizeBytes, or [] if unavailable."""
    return _lms("ls", "--llm", "--json")


def loaded_model_keys() -> set[str]:
    """modelKeys currently resident in LM Studio. Already-loaded models fit by definition."""
    return {m.get("modelKey") for m in _lms("ps", "--json") if m.get("modelKey")}


def check_fit(model_key: str) -> tuple[bool | None, str]:
    """(verdict, message). verdict True/False/None; None means we could not determine fit."""
    # An already-loaded model needs no new allocation — the free-RAM budget doesn't apply.
    if model_key in loaded_model_keys():
        return True, f"'{model_key}' is already loaded in LM Studio"

    match = next((m for m in list_lm_models() if m.get("modelKey") == model_key), None)
    if match is None:
        return None, f"could not find '{model_key}' in the LM Studio catalog to check its size"

    _, available = get_memory_info()
    if available is None:
        return None, f"could not read available RAM to check fit for '{model_key}'"

    size_gb = match.get("sizeBytes", 0) / (1024 ** 3)
    budget = available * SAFETY_FACTOR
    if size_gb > budget:
        return False, (
            f"model '{model_key}' is ~{size_gb:.1f} GB but the fit budget is ~{budget:.1f} GB "
            f"({available:.1f} GB available x {SAFETY_FACTOR}). It may fail to load — free memory "
            f"in LM Studio, or choose a smaller model."
        )
    return True, f"'{model_key}' (~{size_gb:.1f} GB) fits the ~{budget:.1f} GB budget"
