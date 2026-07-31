# Evaluating and fixing — the audit → repair loop

Most tools generate and stop. coursekit also **measures** whether what it made is sound, and **repairs** what isn't. This is the part of the workflow that turns an unreliable local model into trustworthy output: you generate, audit, fix, then ship — not generate-and-pray.

Three commands, in the order you'd use them: **`analyze`** (understand the content), **`evaluate`** (find the problems), **`fix`** (repair them).

## `analyze` — the concept map that grounds everything

```bash
uv run coursekit analyze "/path/to/course"          # every week
uv run coursekit analyze "/path/to/course" --week 7 # one week
uv run coursekit analyze "/path/to/course" --dry-run  # no model; shows what it would read
```

`analyze` builds a per-week **concept map** — the teaching concepts, the knowledge components under each, and the one enduring understanding above them — and writes it to `.vtconfig/concepts/week-N.yaml`. It reads the transcriber's `knowledge.json` when present, or the week text when not.

The map is **yours to edit.** Open the YAML and correct anything off — the concepts, the enduring understanding, which material a concept needs. Generation and evaluation both read it: the page generator uses it as a checklist it can't skip a concept from, and the evaluator scores against that fixed list instead of re-guessing.

## `evaluate` — the cold read

```bash
uv run coursekit evaluate "/path/to/course"          # facticity: quizzes + pages
uv run coursekit evaluate "/path/to/course" --pages  # only pages (--quizzes for only quizzes)
uv run coursekit evaluate "/path/to/course" --all    # + pedagogy (form) + concept-delivery
```

`evaluate` reads each finished quiz question and page section back in a **fresh conversation** (a cold read — not the generator grading its own homework) and reports three kinds of problem:

- **Facticity** — is each item *correct*? Wrong answer keys, definitions that contradict the material, code that won't run.
- **Pedagogy** (`--all`) — does the page *scan, signal, and engage*? A 0–3 rubric, coaching rather than pass/fail.
- **Concept-delivery** (`--all`) — does the page actually *teach* each concept the week is meant to cover?

It writes `quiz-review.md`, `page-review.md`, and (with `--all`) `page-pedagogy.md` / `page-concepts.md` beside the course. Nothing is changed — a human stays in the loop.

A realistic result on a full course: a small local model marks a wrong answer or writes a buggy code block a few percent of the time, and the cold read catches them — the errors that would otherwise ship to students silently.

## `fix` — repair in place

```bash
uv run coursekit fix "/path/to/course"           # quizzes AND pages
uv run coursekit fix "/path/to/course" --pages   # only pages (--quizzes for only quizzes)
uv run coursekit fix "/path/to/course" --week 7  # one week
```

`fix` closes the loop. By default it acts on the **last review** (`quiz-review.md` / `page-review.md`) and repairs exactly what was flagged — no re-audit, so right after a `generate` that flagged one question, `fix` repairs just that one in seconds. (Pass `--reaudit` to cold-read the whole course afresh instead.) For every flagged item it hands the model the material, the flawed question or section, and the reviewer's exact concern, and takes a correction committed through the **same tool with the same id** — so it overwrites that one variant or block and leaves the rest untouched. Then it cold-reads the fix once more to confirm it now passes. Progress prints as it goes, so you can watch it work.

The summary marks each item **fixed ✓** (repaired and now passes), **revised, still flagged** (changed but the critic still isn't happy — worth a human look), or **could not fix** (the model never produced a valid replacement). It updates `bank.json` + GIFT and `page.json` + HTML in place.

> **Re-emit after fixing.** `fix` updates the canonical IR and the standalone artifacts, but not the Canvas package. Re-run `coursekit emit qti` / `emit course` to refresh the `.zip` / `.imscc` you import.

## The whole loop

```bash
uv run coursekit analyze  "/path/to/course"   # 1. understand the content (edit the maps)
uv run coursekit generate "/path/to/course"   # 2. draft quizzes + pages
uv run coursekit evaluate "/path/to/course" --all   # 3. audit
uv run coursekit fix      "/path/to/course"   # 4. repair the flags
uv run coursekit emit     course "/path/to/course"  # 5. package for Canvas
```

Steps 3–4 are the safety net that makes step 2 trustworthy on a model you host yourself.
