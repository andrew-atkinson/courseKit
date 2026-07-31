# Command reference

The full CLI surface. For the high-level "what it's for and who it's for," see the [README](../README.md).

The CLI is four phases, in the order work flows through them, plus a review verb and the tests:

- **`ingest`** — turn a week's documents (PDF, slides, `.docx`) into the week text the generators read.
- **`analyze`** — consolidate a week's concepts into a `.vtconfig/concepts/week-N.yaml` concept map (instructor-editable) that grounds generation and evaluation.
- **`generate`** — turn that week text into quizzes and pages (the model-driven step).
- **`emit`** — package the canonical JSON into Canvas files, model-free — up to a whole-course `.imscc`.

`PATH` is a markdown file or a directory of per-week transcripts (`week-*.md`). Artifacts land beside the course (`quizzes/` and `pages/` trees), never in this repo. `python app.py <verb> …` is equivalent to `coursekit <verb> …` everywhere below.

| Ingest Commands               | What it does                                               | Uses LLM |
| ----------------------------- | ---------------------------------------------------------- | -------- |
| `coursekit ingest PATH`       | Documents (PDF/docx/odt/pptx/txt/md) → `output/week-N.md`. | ✓        |
| `coursekit ingest PATH --raw` | Same, extract only, fully offline.                         | x        |

| Analyze Commands                    | What it does                                                        | Uses LLM |
| ----------------------------------- | ------------------------------------------------------------------ | -------- |
| `coursekit analyze PATH`            | Build each week's concept map (from the transcriber's `knowledge.json`, or the week text when absent) → `.vtconfig/concepts/week-N.yaml`. | ✓ |
| `coursekit analyze PATH --dry-run`  | List the weeks and their knowledge-component counts, no model.     | x        |

| Generate Commands                               | What it does                                                     | Uses LLM |
| ----------------------------------------------- | ---------------------------------------------------------------- | -------- |
| `coursekit generate PATH`                       | Both quizzes and pages, every week found.                        | ✓        |
| `coursekit generate PATH --dry-run`             | List the weeks it would process.                                 | x        |
| `coursekit generate PATH --week 3`              | One week. `--week` is repeatable; `--weeks 3-8` a range.         | ✓        |
| `coursekit generate PATH --pages`               | Only pages (`--quizzes` for only quizzes).                       | ✓        |
| `coursekit generate PATH --pages --detail full` | Page depth: `brief` / `medium` / `full` (overrides `page.yaml`). | ✓        |
| `coursekit generate PATH --output-root DIR`     | Write elsewhere instead of with the course.                      | ✓        |
| `coursekit generate PATH --max-iters N`         | Cap model turns per week (default 80).                           | ✓        |
| `coursekit generate PATH --no-review`           | Skip the cold-read quiz review a `generate` runs by default.     | ✓        |

| Emit Commands                      | What it does                      | Uses LLM |
| ---------------------------------- | --------------------------------- | -------- |
| `coursekit emit qti PATH`          | One Canvas quiz `.zip` per week.  | x        |
| `coursekit emit qti PATH --bundle` | One `.zip` for all quizzes.       | x        |
| `coursekit emit html PATH`         | Re-render pages from `page.json`. | x        |
| `coursekit emit cc PATH`           | One Canvas `.imscc` of all pages. | x        |
| `coursekit emit course PATH`       | One Canvas `.imscc` of the whole course — pages **and** quizzes, in week modules. | x |

| Review Command                     | What it does                                                        | Uses LLM |
| ---------------------------------- | ------------------------------------------------------------------ | -------- |
| `coursekit evaluate PATH`          | Cold-read review of already-generated quizzes **and** pages → `quiz-review.md`, `page-review.md`. | ✓ |
| `coursekit evaluate PATH --pages`  | Only the pages (`--quizzes` for only quizzes).                     | ✓ |
| `coursekit evaluate PATH --all`    | Every evaluation: facticity + page **pedagogy** (form) + **concept-delivery** → `page-pedagogy.md`, `page-concepts.md`. | ✓ |

| Fix Command                        | What it does                                                       | Uses LLM |
| ---------------------------------- | ------------------------------------------------------------------ | -------- |
| `coursekit fix PATH`               | **Regenerate each item flagged by the last review in place** (quizzes **and** pages), then verify — no re-audit, so a just-flagged item is fixed at once. Updates `bank.json`/GIFT + `page.json`/HTML; re-run `emit` to refresh the Canvas package. | ✓ |
| `coursekit fix PATH --reaudit`     | Cold-read the whole course afresh instead of acting on the last review. | ✓ |
| `coursekit fix PATH --pages`       | Only the pages (`--quizzes` for only quizzes). | ✓ |
| `coursekit fix PATH --week N`      | Only that week (`--weeks A-B` for a range); `--max-turns N` caps model turns per fix. | ✓ |

| Test Command         | What it does                                                    | Uses LLM |
| -------------------- | --------------------------------------------------------------- | -------- |
| `uv run pytest`      | The offline unit suite. Deterministic, no model.                | x        |
| `uv run pytest evals/` | Model-in-the-loop evals (critic judgment). Skips without a model. | ✓ |

Exit codes: `0` success · `1` a unit failed to finalize · `2` the model could not be loaded.
