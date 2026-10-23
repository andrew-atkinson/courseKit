# coursekit

Turns a course's own material (transcripts, readings, slides) into Canvas/Moodle-ready quizzes, pages, and assignments via a local tool-calling LLM.
It also evaluates what it made (the critics) and inventories the whole course (the census).
See [agent/architecture.md](agent/architecture.md) for the structural map — it is the source of truth for how the pieces fit; don't duplicate its diagrams here.
The forward plan and dated history live in [agent/roadmap.md](agent/roadmap.md).

**The one load-bearing idea:** every artifact has a canonical intermediate form — `bank.json` (quizzes), `page.json` (pages), `assignment.json` (assignments), `census.json` (the census).
Every input converges on the IR; every emitter (`gift.py`, `qti.py`, the cartridge, the census report) reads only it.
Adding a platform is one emitter, not one converter per input — which is why emitting needs no model.

## Working here

- **Run the suite; don't recall its size.**
  `uv run pytest -q` — fully offline, no model, a few seconds.
  There is never a reason to estimate a result you can run.
- Python ≥3.12, `uv`.
  The package imports pydantic, python-dotenv, rich, openai, jinja2, pyyaml, pypdf, python-pptx + stdlib (no video stack — that's the transcriber's).
  `pyproject.toml` `dependencies` is exactly that set; add a package there only with the import that needs it.
  Notebook-only packages live in the `notebook` dependency group (`uv sync --group dev --group notebook`).
- **Library code never exits or prints.**
  It raises `CoursekitError` (a stable `code`, `details`, a `category`) and reports progress and warnings through `coursekit.outcomes` (`info` / `warn` / `error`); the CLI and the per-module `main()` scripts render them via `console.py`.
  [tests/test_outcomes.py](tests/test_outcomes.py) enforces it.
- **coursekit writes its own `.vtconfig` settings only through `coursekit/settings.py`** — validated against `coursekit/schemas.py`, atomic, never `context.yaml`.
  New code that changes a setting calls the settings API; it never dumps YAML into `.vtconfig/` itself.
- Default branch for PRs is `main`.

## Facticity — this project has been bitten by stale claims

- **Never assert a volatile number from memory** — a test count, a line count, a file size.
  Run the command or read the file.
  The test count went wrong four times before a guardrail was added.
- **A number in prose lives in exactly one place, under a test.**
  The suite's test count lives only in `README.md`, enforced by [tests/test_docs_facts.py](tests/test_docs_facts.py).
  Don't repeat it elsewhere — a number in two files rots in one.
  Decorative counts that show a ratio get a `~`.
- **Claims about the transcriber are read, not reconstructed.**
  Its source is on disk (below).
  Read it before stating what it does; earlier reconstructions from its _outputs_ were wrong.

## Ground truth on disk

- **videotranscriber source:** `~/video_transcription` (separate repo, stays separate — it pulls `mlx-whisper`).
  The two tools meet through files in a course's `.vtconfig/`, never by importing each other.
- **Canvas exports (ground truth for the emitters):** real `.imscc` course exports live in `reference/` (gitignored — large, real course content).
  They are the ground truth behind `qti.py`, the page/assignment CC emitters, and the grading-group XML.
  Format notes: `docs/canvasQuizStructure.md`.
- **`docs/` holds the tracked user-facing guides** (`*.md`; the README's Documentation section lists them); everything else there is gitignored.
  `reference/` is fully gitignored — don't rely on its contents surviving, and don't put the only copy of anything valuable there.
  `agent/` holds the tracked internal references (`architecture.md`, `roadmap.md`, `local-canvas-testing.md`, `GIFT_format_compact.md`).
- **Course artifacts live with the course, never in this repo** — `quizzes/`, `pages/`, `assignments/` beside the course's own files.
  The app directory holds only code and tests.

## Decisions not derivable from the code

- **Per-tool config files are separate.**
  `context.yaml` (course structure) is shared and owned by the transcriber; coursekit's own files (`quiz.yaml`, `page.yaml`, `structure.coursekit.yaml`, …) are private to it.
  coursekit never writes `context.yaml` — its declared structure, grading groups, and expectations go in its own overlay.
  `coursekit/courseconfig.py` is the shared _mechanism_; each tool owns its _file_.
- **Proposers draft; the faculty decides.**
  `propose` (structure, `--grading`, `--expectations`) writes a commented draft the faculty owns by editing, and refuses to clobber it without `--force`.
  A pedagogic choice the faculty hasn't made (a cadence, whether/how EUs are assessed) is a flagged DECISION NEEDED, never a pre-filled rule.
- **The census is presence, not quality.**
  It answers "is there an artifact for X?" offline; "is X any good?" needs the model and belongs to the evaluators.
- **Content boundary: instructor-authored material only, never student submissions.**
  Keeps the project out of FERPA scope.
  Relevant before anyone proposes auto-grading.
- **File emitters stay first-class**, even once a Canvas API emitter exists — many faculty can't get a token, and a reviewable `.zip` is worth more than an API call.
  Any API path defaults to dry-run.
- **The unit is the course's teaching block; a week is only one cadence.**
  Courses meet twice a week, in blocks, by quarter, or self-paced, so new code and docs say *unit* and give it its own identity (id, order, label, optional module, optional calendar slot).
  "Week" survives only as a label, a legacy alias (`--week`, `week_ref`, `weeks:` in `context.yaml`), or an existing on-disk name — never as something to parse meaning from.
  See [agent/structure-review.md](agent/structure-review.md).
- **Real institution and course names stay out of tracked files and commit messages.**
  Use stand-ins (`CC101` for the creative-coding course, `PH101` for the photography course).
- **The repo was called quizbot until 2026-10.**
  "quizbot" in older docs and history is the same tool.
