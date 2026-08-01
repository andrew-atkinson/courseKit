"""Versioned storage for evaluation runs — never overwrite the evidence.

`evaluate` writes its review Markdown at the top of the `quizzes/` and `pages/` trees (the convenient
"latest"), but that gets overwritten every run. This snapshots each run IMMUTABLY to
`<course>/evals/<timestamp>/` — the run's review files plus a `summary.json` recording what/when, the
coursekit git commit that produced it, the model, and the counts — and appends one row to
`<course>/evals/log.jsonl`. So quality becomes a TREND you can read over time (did a change help? did a
regression creep in?), an audit trail, and the substrate for comparing two generation approaches (the
composable A/B). Runs live with the course, never in this repo.
"""

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


def coursekit_commit() -> str:
    """The short git SHA of the coursekit checkout, so a run records the code that produced it."""
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=Path(__file__).resolve().parent, capture_output=True, text=True,
                           timeout=5)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def archive_evaluation(course_root, *, model: str, reviews, metrics: dict) -> Path | None:
    """Snapshot one evaluation run to `<course_root>/evals/<ts>/` and append `evals/log.jsonl`.

    `reviews` — the review `.md` paths written this run (copied into the snapshot).
    `metrics` — `{artifact: {metric: value}}`, e.g. `{"quiz": {"reviewed": 192, "flagged": 4}}`.
    Returns the run directory, or None when there is nowhere to write (no course root)."""
    if not course_root:
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    evals = Path(course_root) / "evals"
    run_dir, n = evals / ts, 2
    while run_dir.exists():                 # two runs in the same second get distinct snapshots
        run_dir, n = evals / f"{ts}-{n}", n + 1
    run_dir.mkdir(parents=True, exist_ok=True)

    for rp in reviews:
        rp = Path(rp)
        if rp.exists():
            shutil.copy2(rp, run_dir / rp.name)

    commit = coursekit_commit()
    (run_dir / "summary.json").write_text(
        json.dumps({"timestamp": ts, "coursekit_commit": commit, "model": model,
                    "metrics": metrics}, indent=2), encoding="utf-8")

    # One flat row per run — a ledger you can read as a table / plot as a trend.
    row = {"timestamp": ts, "commit": commit, "model": model}
    for artifact, m in metrics.items():
        for k, v in m.items():
            row[f"{artifact}_{k}"] = v
    with open(evals / "log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return run_dir
