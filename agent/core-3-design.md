# CORE-3 design — generator state in instances (2026-11-04)

The third step of [structure-review.md](structure-review.md): the artifact being built lives in an object a job owns, not in a module every job shares.
The decisions in §6 were settled with the user on 2026-11-04; the step notes in §5 record what each increment found.
**Complete 2026-11-05.** All five increments landed; the one follow-up left is enforcing tool subsets (`CORE-3.1`).
Facts below were read from `main` at `b816b8e` and from both real courses (read only); counts are snapshots.

## 1. What exists today

**Three builders keep their state in module globals, and everything reaches them by import.**

| Module | Module-level state |
| --- | --- |
| `generate/quiz/bank.py` | `_bank`, `_out_dir`, `_staged` |
| `generate/quiz/tools.py` | `checklist`, `completed`, `_call_log` |
| `generate/page/page.py` | `_page`, `_out_dir`, `_staged` |
| `generate/page/tools.py` | `_call_log` |
| `generate/assignment/build.py` | `_state`, `_out_dir`, `_finalized` |
| `generate/page/renderer.py` | `_INLINE_CODE_STYLE`, set by `render_body`, read by the `md_inline` Jinja filter |

Sequential jobs stay correct only because each one remembers to reset first.
Some functions state the dependency in prose: `fix_one` says the bank must "already be present in `bank.get()` (the caller loads the bank first)".

**Two jobs in one process corrupt each other silently.**
Run on `main`: job A calls `bank.init`, job B calls `bank.init`, then job A calls `create_group`.
A's call returns `OK`, the group lands in B's bank, and B's file on disk now holds A's question.
Nothing raises and nothing warns.
The renderer has the same shape: two courses rendering at once can take each other's inline-code colours.

**What is already safe.**
`outcomes` keeps its report and sink in `ContextVar`s, so it needs no change.
The tool schemas, `build_variant`, and `build_block` hold no state.
The `Generator` classes are already instances, so `pipeline.py` barely changes: only what they point at moves (step 3 found the one exception, `loop`'s default generator).

**The size of the move** (counted with an import-aware AST scan).

- ~95 calls to the stateful API in ~17 package files: the generators, tools, `fix`, `eu`, `decompose`, `glossary`.
- ~460 calls in ~33 test files, mostly fixtures that build a bank or page to test something else.
- `evals/` builds `Bank` and `Page` directly and makes no stateful calls.

**The proof that nothing changes is already on disk.**
Both real courses hold recorded `calls.jsonl` logs from real model runs (~20 artifacts, ~5,000 calls), and `dispatch.replay` feeds them back with no model.
§7 records what they do and do not cover.

## 2. Goals and non-goals

**Goals.**

- A job owns its state: two jobs can interleave in one process and each produces exactly what it would have produced alone.
- A function that needs the artifact takes it as an argument, so "the caller loads it first" stops being a rule people must remember.
- No behaviour change: same files, same bytes, same text sent back to the model.

**Non-goals.**

- **Running jobs concurrently.** No job queue, cancellation, threads in the CLI, or progress API: those are CORE-7 and the app. This makes them possible.
- **Provider thread safety.** The proof uses fake providers. Whether a real provider or LM Studio tolerates two jobs at once is a question for CORE-7.
- **Two jobs writing one output folder.** Isolated state does not stop them overwriting each other's files; whatever schedules jobs must refuse that.
- **Reshaping the seam.** The `Generator` protocol keeps its shape, and decompose keeps its own section loop.
- **Renaming `week`.** That is CORE-5.
- **Enforcing which tools a pass may call.** The EU, fix, decompose, and glossary passes offer the model a subset of the tools, but dispatch accepts all of them: on `main`, the EU pass offers only `add_open_response_variant` and still runs `create_question_group`. Closing that changes behaviour, so it is a follow-up, and a session makes it a small one.

## 3. The shape

**A draft is an artifact being built and where it saves.**
`Bank` and `Page` stay plain IR; a draft wraps one and carries what the IR must not serialize.

```python
class BankDraft:
    bank: Bank
    out_dir: Path | None
    staged: bool

    @classmethod
    def new(cls, run_id, out_dir=None, title="Question bank", source=None): ...   # was bank.init
    @classmethod
    def adopt(cls, bank, out_dir=None): ...                                       # was bank.load

    # was the module function of the same name:
    def create_group(...), put_variant(...), report(), validate_final(), pick_quiz(...), finalize(...)
```

`bank.get()` becomes `draft.bank`, and `bank.reset()` (a test hook) goes away.
`PageDraft` is the same shape; the assignment builder becomes a small `AssignmentDraft`.
`build_variant` and `build_block` stay module functions, because they hold no state.

**A tool session is one run's tools, bound to one draft.**
`dispatch.ToolSession` is a small base class that owns the registry, the call log, the terminal-tool stop, and replay, so quiz, page, and assignment stop carrying copies of them.
Each generator's tools become ordinary methods on a subclass:

```python
class QuizTools(ToolSession):
    SCHEMAS = _SCHEMAS
    TERMINAL = {"finalize_bank"}

    def __init__(self, draft, call_log=None):
        super().__init__(call_log)
        self.draft = draft
        self.checklist, self.completed = [], []

    def add_true_false_variant(self, group_id, variant_label, ...) -> str:
        v = bank.build_variant("true_false", ...)
        return self.draft.put_variant(v)
```

The hand-tuned schemas stay module constants in the same file, in today's order, with their text untouched, so the fix, EU, decompose, and glossary subsets of `TOOL_SPECS` keep working.
They move out from between the functions to above the class; the existing signature tests (`test_schema_matches_function_signature` and its page twin) keep each method and its schema from drifting apart.
A wrong-argument error would otherwise gain the class name (`QuizTools.add_x()`), so `dispatch` removes that prefix and the model keeps seeing today's text.

**The owners.**

- A generator builds its draft and session in `reset()` and keeps them on `self`. `run_course` keeps reusing one generator for its units in sequence; a concurrent job uses its own generator.
- `fix_one`, `generate_eu_question`, and decompose's helpers take the session as an argument.
- `fix_course` and `build_glossary_page` create one per artifact, as they already reset one today.

**The renderer** keeps its templates: `render_body` works out the inline-code style as it does today and passes it to each template as a `code_style` variable, beside the theme they already receive.
The `md_inline` filter reads it with Jinja's `@pass_context`, and `render_body`'s one direct call passes it as an argument.
The style comes from `code_style`, not the template's `t`, because the recap fallback renders with a different `t` and must keep today's colours.

## 4. The rules that keep it this way

- **No `global` statement under `coursekit/generate/`, and no module-level mutable state there beyond constants.** A test enforces it, as `tests/test_outcomes.py` enforces "library code never prints".
- **A draft is never reachable by import.** If a function needs one, it is in the signature.
- **One draft per artifact per run.** Nothing is shared by reference between jobs.

## 5. Increments — one branch each, each with a pass criterion

Every step must keep these **goldens** identical to `main`, captured once before step 1 into the scratchpad:

- **G0, what the model is offered.** `TOOL_SPECS` for every generator, as JSON, byte for byte.
- **G1, replay.** Every recorded `calls.jsonl` from both real courses, copied out and replayed into a fresh folder, plus a short hand-written log for the tools the real logs never call: each tool's returned text and every file written.
- **G2, driver.** The same logs fed through `run_unit` by a fake provider, one call per turn: the artifacts, `reply.txt`, the new `calls.jsonl`, and the messages sent back to the model.
- **G3, render.** Every real `page.json` from both courses (read only) rendered in all four themes, in a mixed order, including a recap-role page: every byte of HTML.

Every step must also keep the **test guard**: no test removed, and the number of `assert` statements per test file unchanged, because test edits should touch setup, not assertions.

1. **`core-3-assignment` — the pattern, on the smallest builder.**
   `AssignmentDraft` and the shared `dispatch.ToolSession`, with `build.py` and `tests/test_assignment_gen.py` moved.
   *Pass:* G0 for assignments; a scripted assignment run is byte-identical to `main` (assignments have no recorded logs); two interleaved assignments each come out correct; the guards hold.
   **Done 2026-11-04.** All goldens identical to `main`, and the only assert change is the new tests. `dispatch.ToolSession` is the shared base; the error-text fix is `dispatch._without_class`, and both a test and the goldens catch its removal. The pattern held with no changes to the design.
2. **`core-3-page` — pages.**
   `PageDraft` and `PageTools`, with the generator, decompose, glossary, fix, and their tests moved; `page.py` loses its globals.
   *Pass:* G0, G1, G2, and G3 for pages; one generator reused for two units keeps them separate, and that test fails if a helper keeps the first unit's draft; the guards hold.
   **Done 2026-11-04.** All goldens identical to `main`, and the only assert changes are the new tests.
   The goldens turned out not to reach decompose, glossary, or `fix`, and no test runs a whole decompose, so this step added a scripted comparison against an extracted copy of `main`: decompose (finalized, with pass errors and empty sections, unfinished), glossary (one chunk, several), `fix_course_pages` over two pages, and `decompose.main --review --fix`. All byte-identical. Step 3 needs the same for the EU pass and quiz `fix`.
   `decompose.main --fix` keeps an unfinished page staged, so it can't replace the last good `page.json`; the comparison catches that if it is changed to `adopt`.
   One difference on purpose: on `main`, the call log outlived a run, so a `fix` in the same process as a generation appended to that generation's `calls.jsonl`. No CLI path does both, and now `fix` simply has no log.
3. **`core-3-quiz` — quizzes.**
   `BankDraft` and `QuizTools`, including the checklist, with the generator, EU pass, fix, and their tests moved.
   *Pass:* G0, G1, and G2 for quizzes, including `.gift` and `quiz.json`; the same two-unit test; the guards hold.
   The docs that name `bank.finalize` and `bank.load` (`CLAUDE.md`, both architecture files) move with it, and `dispatch.py`'s docstring loses its stale line about the quiz generator keeping its own copy.
   **Done 2026-11-04.** All goldens identical to `main`, and the only assert changes are the new tests.
   As in step 2, this step added a scripted comparison against an extracted copy of `main`: `run_unit` with the EU pass (added, prose, wrong tool, no map, no text), an unfinished re-run, auto-finalize, one generator over two units, a targeted quiz, `fix_course` over two banks, and `eu.main`. All byte-identical, and it caught a real slip while moving the code: a rename had changed the text of an error message the model reads.
   `pipeline.loop` no longer defaults to a new `QuizGenerator`: nobody could reset that generator, and it only worked because the state lived in the module. Nothing outside the tests relied on it.
   **Follow-up, 2026-11-05 (`core-3-loop-generator`, user's call).** `run_unit` and `run_course` lost their defaults too: leaving out the generator silently ran quizzes, in a driver whose docstring says it knows nothing about quizzes. All three now refuse with a `TypeError`, and a test also checks `pipeline.py` names no concrete generator. A generator passed to `loop` without being reset still fails only after its first model call, with an `AttributeError`; no code path in the package can do that, so it stays as it is.
   Mutation checks found the suite didn't notice the EU pass or `eu.main` dropping the call log, so two more tests pin that.
   One difference on purpose, the same as pages: `fix` no longer inherits a call log left by an earlier run in the same process. No CLI path does both.
4. **`core-3-renderer` — the inline-code style.**
   *Pass:* G3 identical; a new test renders two themes alternating inside one template pass and each keeps its own colours.
   **Done 2026-11-05.** G3 and the other goldens are identical to `main`, plus a scripted comparison of assignment HTML and cartridge page HTML in every theme, which G3 doesn't reach. `render_body` passes `code_style` to the two template calls that use `md_inline`; `supplements.html.j2` doesn't use the filter, so it isn't passed there. A second test checks every inline-code chip on a page, recap questions and recap fallback included, because a call site that forgets `code_style` renders a bare `<code>` with no error.
5. **`core-3-isolation` — the proof, and the docs.**
   The new tests that make this permanent: two quiz jobs and two page jobs on separate threads, forced to alternate at every tool call by a barrier, each byte-identical to the same job run alone; and the §4 guard.
   `agent/architecture.md` and the seam's docstrings are refreshed, the §4 rules join `CLAUDE.md`, and the roadmap closes CORE-3 with its Shipped line.
   *Pass:* the new tests pass, and fail when a global is put back (mutation check).
   **Done 2026-11-05.** `tests/test_isolation.py` holds both. The threaded test runs each pair alone, then on two threads that take strict turns at every model call, and compares every file of every job byte for byte; it also checks the turns really alternated.
   The guard flags a `global`, a module-level container a function mutates, and a class attribute or imported module attribute set inside a function; a second test checks it sees each of those in a deliberately bad file.
   Mutation checks: a `global` in the renderer and a page-tools class attribute were caught by the guard (the second by the page threads too); a module-level list of quiz drafts by both; and quiz drafts shared through a helper's default argument, which the guard cannot see, by the quiz threads alone.
   The renderer is not exercised by the threads, because a page renders once, after its last tool call; step 4's test covers it, a second render inside the first.
   The §4 rules are now in `CLAUDE.md`, beside "library code never prints", and the seam's docstrings no longer describe module state.

## 6. Decisions

1. **Explicit instances, not `ContextVar`s. Accepted by the user, 2026-11-04.**
   A `ContextVar` behind the existing `bank.*` functions would isolate jobs with almost no diff, but "the caller loads it first" would remain a rule, and CORE-7's library functions would have no object to pass or return.
2. **Remove the module functions outright, no compatibility shim. Accepted.**
   A shim that forwards `bank.put_variant` to a "current" draft is the old global under another name, and leaves two ways to do everything.
   Nothing outside this repo calls these functions, and `evals/` makes no stateful calls, so nothing needs a bridge.
3. **Tools become methods on a `ToolSession` subclass. Accepted, revised after the user questioned the first proposal.**
   The first proposal, plain functions bound with `partial`, was chosen for a smaller diff, and its cost was overstated: methods re-indent ~150 lines of function bodies, not ~500, because the schemas can stay where they are as module constants.
   Methods are the ordinary Python a reader expects, `partial` is used nowhere else in the package, tests read `session.add_x(...)`, and a new generator (discussions are next) copies a clear pattern.
   What it costs: a function no longer sits beside its schema (the signature tests guard the match), and the error text needs one small fix in `dispatch`.
4. **Pass the style to the templates; no `ContextVar`. Accepted, revised.**
   The first proposal said a Jinja filter cannot be handed a style. That was wrong: `@pass_context` lets a filter read a template variable, shown working in a scratch check with themes alternating through one template.
   This also keeps the state explicit, like decision 1, with no template files edited.
5. **Order: assignment → page → quiz. Accepted.**
   This is the order of the code changes and says nothing about course content.
   The three builders share no state, so any order works; assignment comes first because it is small enough to expose a bad pattern cheaply, and quiz last because it has the most tests and the most delicate output.
6. **`load_dotenv(override=True)` stays in `quiz/tools.py` for now (user's call).**
   Importing that module overwrites the process environment, and the file reads no environment variables itself, so it is worth revisiting before an app embeds this code. It is not part of CORE-3.

## 7. Risks, and what testing them found

Tested on `main` on 2026-11-04, replaying the real logs in the scratchpad.

| Risk | Test | Result |
| --- | --- | --- |
| The text a model sees could change | Called each tool shape with bad arguments | Real, not theoretical: bound methods add the class name, and the real logs contain such errors (at least 10). `dispatch` strips the prefix; G1 and a pinned test check it. |
| Rarely used tools could escape the goldens | Compared the logs with the registries | `add_numerical_variant` and `get_page_report` never appear, and assignments have no logs. G1 adds a hand-written log; step 1 uses a scripted run. |
| Logs may span several runs | Counted finalize calls per log | Confirmed: one page log holds 15 finalize calls and ends unfinalized, and 2 of the 9 page logs end unfinalized. G1 remains a fair old-versus-new check, but it does not reproduce the shipped artifact, so G3 renders the real `page.json` files instead. |
| Test churn could hide a behaviour change | Saved `assert` counts per test file (64 files) | Baseline saved; each step compares against it. |
| A stale reference after `reset()` | Cannot run until the code exists | Steps 2 and 3 add a two-unit test, mutation-checked. |
| A global creeps back later | Cannot run until the code exists | Step 5's guard test, mutation-checked. |
| The renderer's recap path uses a different theme dict | Read the code | Found while checking decision 4: the style must not be recomputed from the template's `t`. G3 includes a recap-role page. |
