# quizbot / coursekit

Turns lecture transcripts into randomized Canvas quizzes via a local tool-calling LLM. Longer aim:
a shared spine (`coursekit/`) that future course-artifact generators reuse. See
[agent/architecture.md](agent/architecture.md) for the structural map and the migration plan — it is
the source of truth for how the pieces fit; don't duplicate its diagrams here.

**The one load-bearing idea:** `bank.json` is a canonical intermediate form. Every input converges on
it; every emitter (`gift.py`, `qti.py`) reads only it. Adding a platform is one emitter, not one
converter per input. This is why QTI export needs no model.

## Working here

- **Run the suite; don't recall its size.** `uv run pytest -q` — fully offline, no model, ~1s. There
  is never a reason to estimate a result you can run.
- Python ≥3.12, `uv`. Deps: pydantic/dotenv/rich/openai + stdlib (no video stack — that's the
  transcriber's).
- Default branch for PRs is `main`.

## Facticity — this project has been bitten by stale claims

- **Never assert a volatile number from memory** — a test count, a line count, a file size. Run the
  command or read the file. The test count went wrong four times before a guardrail was added.
- **A number in prose lives in exactly one place, under a test.** The suite's test count lives only in
  `README.md`, enforced by [tests/test_docs_facts.py](tests/test_docs_facts.py). Don't repeat it
  elsewhere — a number in two files rots in one. Decorative counts that show a ratio get a `~`.
- **Claims about the transcriber are read, not reconstructed.** Its source is on disk (below). Read it
  before stating what it does; earlier reconstructions from its *outputs* were wrong.

## Ground truth on disk

- **videotranscriber source:** `~/video_transcription` (separate repo, stays separate — it pulls
  `mlx-whisper`). The two tools meet through files in a course's `.vtconfig/`, never by importing each
  other.
- **Canvas QTI reference:** a real course export under
  `~/Desktop/courses/CC101/course export/` — the ground truth behind `qti.py`. The format notes are in
  `docs/canvasQuizStructure.md`.
- **`docs/` is gitignored.** Tracked references live in `agent/` instead (`architecture.md`,
  `GIFT_format_compact.md`). Anything in `docs/` is not in version control — don't rely on it
  surviving, and don't put the only copy of something valuable there.
- **Course artifacts live with the course, never in this repo** — a `quizzes/` tree beside the
  course's own files. The app directory holds only code and tests.

## Decisions not derivable from the code

- **Per-tool config files are separate.** `context.yaml` (course structure) is shared; the
  transcriber's `config.yaml` and quizbot's `quiz.yaml` are each private to their tool.
  `coursekit/courseconfig.py` is the shared *mechanism*; each tool owns its *file*.
- **Content boundary: instructor-authored material only, never student submissions.** Keeps the
  project out of FERPA scope. Relevant before anyone proposes auto-grading.
- **File emitters stay first-class**, even once a Canvas API emitter exists — many faculty can't get a
  token, and a reviewable `.zip` is worth more than an API call. Any API path defaults to dry-run.
- **The institutional Canvas token goes in `.env` (gitignored) only when API work begins** — never committed,
  never logged.
- **The quizbot→coursekit rename is triggered by generator #2, not a date.** Until then the spine is
  built in place. Don't do the rename mid-feature.
