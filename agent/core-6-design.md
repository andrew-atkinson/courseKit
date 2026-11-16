# CORE-6 design — authority as data (2026-11-16)

The sixth step of [structure-review.md](structure-review.md) (§3.4): a value can come from the faculty (declared), from a rule in coursekit (derived), or from coursekit's draft that nobody has accepted yet (proposed), and wherever more than one is possible, coursekit records which.
The point is that a value coursekit drafted is never reported or emitted as the faculty's decision.
Facts below were read from `main` at `69bf1f1` and from both real courses (read only); counts are snapshots.

## 1. What exists today

**Artifacts already say who made them.**
Since CORE-4 every step in an artifact's record carries `by` — `model`, `coursekit`, or `instructor` (an edit found by hash) — and status is worked out when asked.
CORE-6 does not touch artifacts as wholes; it is about **settings** and **values inside an artifact** that can come from more than one place.

**Two values already record their authority.**

| Value | Field | Values | Read by |
| --- | --- | --- | --- |
| what the census expects of each unit | `census.json` `expectation_basis` | `declared` (an `expect:` block exists) / `modal` (the course's own majority) | the census report's wording and gap count |
| a quiz's question order | `quiz.json` `order_from` | `default` (as written, open questions last) / `instructor` (set by `bank.set_order`) | `BankDraft.quiz_groups`, so a later run keeps an instructor's order |

**The gap: a proposal becomes a declaration the moment it is written.**
`propose`, `propose --grading`, and `propose --expectations` each write a section of `structure.coursekit.yaml` through one function, `settings.propose_section`.
From then on nothing can tell that section from one the faculty wrote.
The "proposers draft; the faculty decides" rule is kept by a comment header and by refusing to clobber, but every reader treats the draft as decided:

| Section | Drafted by | What reads it as declared | What goes wrong |
| --- | --- | --- | --- |
| `grading:` | `propose --grading`: one group per artifact kind, **equal-weight placeholders** | the cartridge (`_grading_settings`) | placeholder weights go to Canvas as the course's weights, with no warning |
| `expect:` | `propose --expectations`: modal rules, plus DECISION NEEDED notes in comments | the census (`_expectation_gaps`) | the census reports `expectation_basis: declared` for coursekit's own guess; CC101's `expect:` came from the proposer |
| `units:` | `propose` (filename rules) or `propose --model` | the course model, ingest, the census | lower stakes: the faculty sees the units in every command's output |

**Values with a coded fallback (derived) that the faculty can also set.**
These are the "derived" cases; none records which it used.

| Value | Declared in | Fallback |
| --- | --- | --- |
| assignment points | `assignment.yaml` `assignment_points` | `10` (`build_assignment`), then the model's criterion weights split it |
| the unit noun | overlay `unit_noun` | `week` |
| questions per quiz | `quiz.yaml` `questions` | the generator's default |
| a unit's title | `context.yaml` / overlay `title` | `week N`, or the unit's id |
| the grading groups when none are declared | `grading:` | one `Assignments` group at weight 0 |

## 2. The rule

**Three words, one meaning each.**
- **declared** — the faculty made it theirs through a command: `coursekit accept` or `coursekit config set`.
- **derived** — coursekit worked it out by a fixed rule (a default, the modal norm, a folder scan) because nothing was declared, and says so.
- **proposed** — coursekit drafted it for the faculty to decide, and nobody has yet.

A proposal is not a kind of derivation: a proposed value may come from a rule or from the model; what makes it proposed is that it is waiting for the faculty.
A derived value never becomes declared; it stops applying once a section is declared (or proposed) in its place.

**Record authority where a reader acts on the value, not everywhere a value has a fallback.**
A derived default that no output depends on (the unit noun, a quiz's question count) needs no field.
Authority is recorded where it changes what coursekit says or emits: the census, the cartridge, and `coursekit check`.

**Nothing becomes declared by an edit alone.**
Like `git commit`, a change is made however the faculty likes — any editor — and then recorded by one command that checks it and notes who, when, and what.
That holds for a section written by hand as much as for one coursekit drafted: each goes through `accept` (or `config set`), so every declared section has an entry saying who declared it and when.

**Status is worked out from the history, never stored.**
Each section has a history of entries, newest last; the status compares the section on disk with the last entry:

| The section on disk | Status |
| --- | --- |
| absent | None |
| present, no history (written before CORE-6, or by hand and not yet accepted) | `unknown` |
| matches the last entry, which coursekit proposed | `proposed` |
| matches the last entry, which the faculty accepted or set | `declared` |
| differs from the last entry | `edited` (changed since that entry; not yet accepted) |

Every reader acts on `proposed`, `edited`, and `unknown` exactly as today — the values are still used — but flags them until they are accepted.

## 3. The design

### 3.1 Where authority lives

`.vtconfig/structure.coursekit.authority.json` — per section, a list of entries `{step, by, at, coursekit, digest, section}`:
- `step` — `proposed` (a proposer wrote it) or `accepted` (`coursekit accept`, or `config set` on a key in the section);
- `by` — `coursekit` for a proposal; for an acceptance, the login name of whoever ran the command, or `--by NAME`;
- `at` — when; `coursekit` — the version, as records note it;
- `digest` — `records.digest` of the section as parsed, so reformatting or re-ordering keys in YAML is not an edit, and changing a value is;
- `section` — a copy of the section as it was, so `accept` can show what changed since the last entry. The sections are small.

It is written only through `settings.py` and `atomic.write`, beside the overlay it describes; it is coursekit's own file, never `context.yaml`, and the overlay itself stays clean YAML the faculty edits.
`settings.authority(root, section)` is the one reader: the status (above) and the last entry.
`by` is who, as a string: today a name; later possibly an account (`UX-9`).
To keep that open, readers treat `by` as an opaque label and ignore keys they don't know in an entry, so an account can replace the name or sit beside it (an `account` key) without migrating any history.

### 3.2 Accepting

`coursekit accept PATH [SECTION ...] [--by NAME]` (`units`, `grading`, `expect`); with no section it accepts every section the overlay has, so an existing course is cleared with one command.
For each section it:
1. validates it against the schema, as `coursekit check` does, and refuses one that doesn't pass;
2. prints what changed since the last entry (`grading: Quizzes weight 50 → 30`), or that it is accepted unchanged (a proposal taken as it is), or that it has no history (a first acceptance);
3. appends an `accepted` entry.

There is no "are you sure?" prompt: running the command is the yes, as with `git commit`.
Accepting a section that is already `declared` and unchanged adds nothing and says so.
`coursekit config set` on a key inside a section validates and writes as it does today, then appends an `accepted` entry for that section, so the settings API is the other way through the process.
`propose --force` appends a `proposed` entry, as it writes a new draft.

### 3.3 Who reads it

- **`coursekit check`:** each overlay section with its status, who, and when — `grading  edited since andrew accepted it on 2026-11-16 — coursekit accept PATH grading`.
- **The census:** `expectation_basis` becomes `declared` / `proposed` / `edited` / `unknown` / `modal`; any of the first four drives the gaps exactly as declared does today, and the report says who set the expectations, or that they are coursekit's draft or not yet accepted, and how to accept them.
- **The cartridge:** grading that is not `declared` is emitted as it is today, with one warning through `outcomes.warn` naming the section, its status, and `coursekit accept`. File emitters stay reviewable; nothing refuses (decision 3).

### 3.4 One vocabulary for what exists

`expectation_basis: modal` stays `modal` (it names *which* rule derived it, which the report uses) and `order_from` keeps `default` / `instructor`.
Both are already in files on disk; this design maps them (`modal`, `default` → derived; `instructor` → declared) rather than migrating stored values.

## 4. Increments

Each step is its own branch with goldens (G0 the exports, G1 generation and records) and mutation checks.

1. **The history and `accept`.**
   `settings.propose_section` appends a `proposed` entry; `coursekit accept` and `config set` append an `accepted` one; `settings.authority` works out the status; `coursekit check` shows it. `propose --help` stops saying "weeks".
   *Pass:* a fresh proposal reads `proposed`; changing a value reads `edited`, and reformatting doesn't; `accept` (one section, or all) makes it `declared` with the login name or `--by`, and prints the change from the last entry; `accept` refuses a section that fails validation and writes nothing; `config set` makes its section `declared`; a section with no history reads `unknown`, an absent one None; an entry with a key coursekit doesn't know reads as if it weren't there; every proposer goes through it (a test over all three); G0 and G1 identical.
   **Done 2026-11-16.** `settings.py` keeps each section's history in `.vtconfig/structure.coursekit.authority.json` and works out its status (`authority`, `authorities`); `propose_section` appends `proposed`, and `accept`, `set`, and `unset` append `accepted` with the login name or `--by`.
   `coursekit accept` prints what changed since the last entry (`grading.groups.Quizzes.weight: 50.0 → 30.0`); `coursekit check` lists each section's status with the command to accept it, its path quoted so it can be pasted; `propose`'s help and closing lines call its output a draft to accept. `accept` is in `docs/commands.md` and the diagram now, not left for step 4.
   An unreadable history is an error naming the file (`authority.unreadable`), as CORE-1 treats any unreadable input.
   G0: all 904 files and members identical, and both emit logs. G1: every file and record identical to `main`'s. Both real courses (read only): every section reads `unknown` — CC101's `grading` and `expect`, PH101's `units`. 9 mutations, all caught.
2. **The census says who set the expectations.**
   *Pass:* each status gives its basis and report line; the gaps are the same for all of them; on both real courses `census.json` and `census.md` differ from `main` only in the basis and that line.
   **Done 2026-11-16.** `census._compute_gaps` takes the basis from `settings.authority(root, "expect")` and keeps the last entry's `step`, `by`, and `at` in a new `expectation_set` field, so the report is still written from `census.json` alone.
   `census.basis_line` is the one sentence under "Gaps" (`Measured against coursekit's draft expectations (proposed 2026-11-16), which nobody has accepted yet — …`); the modal basis has none, since each of its gap lines already names the course's own pattern.
   `coursekit census` prints the same sentence, with the course's path quoted, until the expectations are accepted.
   An `expect:` block with no rules is still the modal basis, as before.
   Both real courses (read only, written to the scratchpad): CC101's `census.json` differs in `expectation_basis` (`declared` → `unknown`) and the new `expectation_set: null`, and its `census.md` in that one sentence; PH101's (modal) differs only in `expectation_set: null`. The gap count is the same on each.
   G0: all 904 files and members identical, and both emit logs. G1: every file and record identical to `main`'s. 13 mutations, all caught.
3. **The cartridge warns on grading nobody accepted.**
   *Pass:* emitting with grading that is not `declared` warns once, naming its status and `coursekit accept`; the package is byte-identical to emitting the same grading declared; no warning for declared or absent grading; G0 packages identical.
   **Done 2026-11-16.** `cartridge._grading_settings` calls `_warn_unless_accepted` when the overlay has a `grading:` block: one `outcomes.warn` (`grading.not_accepted`, with the status in its details) saying whose the groups and weights are and giving `coursekit accept` with the path quoted.
   Both commands that write grading go through it — `emit course` and `emit assignments` — and each warns once.
   An unreadable history stops the emit with `authority.unreadable`, as it stops `check` and the census: coursekit can't say whose the grading is, and the message says how to fix it.
   G0: all 904 files and members identical to `main`'s; the emit logs differ only by the warning, once for each of CC101's two commands (its grading reads `unknown`), and not at all for PH101 (no grading block). G1 identical. 12 mutations, all caught.
4. **Docs.**
   `docs/architecture.md` (the authority of each overlay section), `docs/commands.md` (`accept`), the census guide, `agent/architecture.md`, `docs/architecture-diagram.html`, and the roadmap.
   **Done 2026-11-16.** The statuses and `accept` are documented once, in `docs/configuration.md` ("Whose each overlay section is"); `docs/commands.md` (the census row, the `propose` and grading notes), `docs/overview.md`, and `docs/architecture.md` point to it.
   There is no separate census guide: the census is documented in the commands guide, which now says its report names who set the expectations.
   Both architecture docs gain a paragraph and the authority file in a diagram (`docs/architecture.md`: who reads it; `agent/architecture.md`: who writes it); the diagram page's census node and its "faculty decides" caption say the same; `CLAUDE.md`'s "Proposers draft; the faculty decides" names `accept`.
   The three diagrams changed use only syntax already in those files; they were not rendered in this step (the renderer could not be run), so render them once before relying on them.

*Done when:* a section becomes declared only through `accept` or `config set`, each with who and when on record; a value coursekit drafted, or one changed since it was accepted, is never reported or emitted as the faculty's — the census says so and the cartridge warns; every package and record is byte-identical to `main`'s.

## 5. Out of scope

- Assignment points (a silent default of 10 when `assignment_points` is unset) go with quiz settings as data in `STRC-8` (decision 4).
- Several people drafting and editing one course's design — roles, review, merging — is parked as `UX-9`; `by` holds a name until then.
- Quiz settings (`STRC-8`) and a unit's quiz plan (`ASMT-20`) will each be declared / proposed when they are built; they use this mechanism, they don't extend it.
- The transcriber's `context.yaml` is the faculty's (or the transcriber's); coursekit never notes authority for it.
- Concept maps: their record already says `by: model` and finds an instructor's edit; refusing to overwrite an edited map is `CORE-4.6`.
- `coursekit edit PATH SECTION` (open the section in `$EDITOR`, validate on save, accept in one step) — a convenience over `accept`, left until someone wants it.

## 6. Decisions

Settled with the user on 2026-11-16.

1. **How a proposal is told from a declaration:** a fingerprint in each history entry (3.1) — not a `proposed: true` key in the YAML.
2. **What a section with no history is:** `unknown`, flagged until accepted — not silently `declared`. Readers act on it as today; `coursekit accept PATH` clears a course in one command.
3. **What the cartridge does with grading nobody accepted:** emit and warn — not refuse, which would stop a reviewable `.zip` over a value the faculty can still fix in Canvas.
4. **Assignment points:** left for `STRC-8`, not this arc.
5. **Nothing is declared by an edit alone:** an edit reads `edited` until `accept` or `config set` records who and when; a hand-written section goes through the same command as a proposal.
6. **Who `by` is:** the login name of whoever runs the command, with `--by NAME` to override (a co-teacher at the same machine). No prompt: the command is the yes.
