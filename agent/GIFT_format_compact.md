# GIFT format — reference

Verified against Moodle's GIFT parser (`question/format/gift/format.php`, MOODLE_405_STABLE) and its test suite.
Where this doc states a rule, the parser enforces it.

## File rules
- UTF-8 only. Questions are delimited by **blank lines**.
- `//` comment — must be the first thing on its line. Not imported.
- A comment may carry metadata: `[id:myid]` sets the question idnumber, `[tag:algebra]` adds a tag (repeatable). Escape a literal `]` as `\]`.
- `$CATEGORY: path/to/category` on its own line sets the category for everything after it.

## Question skeleton
```
::Title::Question text {answer block}
```
- `::Title::` optional. If omitted, the title becomes the first 80 chars of the question text. Titles are truncated at 255 chars. Always supply one.
- Braces `{ }` are required (except for descriptions). Unbalanced braces = import error.
- **Missing-word format:** if text follows the closing `}`, the answer block is replaced by `_____` in the rendered question. If `}` ends the question, nothing is inserted. `Grant is {~buried =entombed ~living} in Grant's tomb.`

## Type detection — checked in this exact order
This precedence is the whole grammar.
The first match wins.

| # | Condition on the answer block | Type |
|---|---|---|
| 1 | no braces at all | description |
| 2 | `{}` empty | essay |
| 3 | first char is `#` | numerical |
| 4 | contains `~` anywhere | multichoice |
| 5 | contains both `=` and `->` | matching |
| 6 | content (minus `#feedback`) is exactly `T`/`TRUE`/`F`/`FALSE` | truefalse |
| 7 | anything else | shortanswer |

Consequences worth internalising:
- An unescaped `~` in a short answer silently makes it multiple choice. Escape as `\~`.
- T/F tokens are **case-sensitive uppercase**. `{t}` or `{True}` parse as *shortanswer*, not an error — a silent wrong-type bug.

## Feedback and weights
- `#feedback` after an answer. Applies to multichoice, shortanswer, numerical, truefalse. **Matching supports neither feedback nor weights** — a `#` there is literal text.
- `####general feedback` at the end of the answer block (last `####` wins). Shown after the question regardless of response.
- Weights are `%n%` immediately after the marker. Negative and decimal allowed: `%50%`, `%-100%`, `%33.333%`.
- **Weights attach to `~` in multiple choice, and to `=` in short answer / numerical.** In multichoice `=` always means 100% — `=%50%x` does *not* work, the `%50%` becomes literal answer text. Use `~%50%x`.

## Text format markup
Prefix any text span with `[html]`, `[moodle]`, `[plain]`, or `[markdown]`.
Valid on question text, answers, and feedback independently.
An unrecognised `[foo]` is left as literal text.
```
::Q::[html]Match the <b>activity</b>. {=[markdown]A *wiki* -> Wiki =[plain]A forum -> Forum}
```

## Escaping
Escapable: `\:` `\#` `\=` `\{` `\}` `\~` `\\` and `\n` (newline).
Note `:` is escapable (matters for `::` titles and numeric tolerances).
`->` is **not** escapable.

---

# Types

## Multiple choice — min 2 answers
One correct (`=` present → single-answer mode):
```
::Grant's tomb::Who is buried in Grant's tomb? {
=Grant #Correct.
~no one #Someone is.
~Napoleon
}
```
Inline: `::Title::Question {=Correct ~Wrong1 ~Wrong2}`

**Multiple correct answers:** use *no* `=` at all — weights on `~` only.
Presence of any `=` forces single-answer mode.
```
::Q::What two are prime? {~%50%2 ~%50%3 ~%-50%4 ~%-50%6}
```
Convention (not parser-enforced): positive weights should sum to 100.

## True/false
`{T}` `{F}` `{TRUE}` `{FALSE}` — uppercase only.
Feedback order is **wrong-response feedback first, then right-response**:
```
::Q::42 is the Answer.{TRUE#No, it is.#You got it.####General note.}
```

## Short answer — min 1 answer
Only `=` answers, no `~`.
Case-insensitive matching.
Each accepted answer gets its own `=`.
```
::Two plus two::Two plus two equals {=four =4}
```
Partial credit: `{=four =%50%4}`

## Numerical
Answer block opens with `#`.
That `#` is structural, not feedback.
```
{#4}            exact (tolerance 0)
{#4:0.5}        4 ± 0.5
{#1..5}         range → parsed as answer 3, tolerance 2
{#3:2~#Wrong}   trailing ~# gives feedback for any non-matching answer
{#=1822:0 #Right =%50%1822:2 #Half credit}
```
Weights follow `=`.
Ranges are converted to answer=(min+max)/2, tolerance=max−answer.

## Essay
Empty braces, nothing between them.
Graded manually.
```
::Essay::Explain the causes of the war. {}
```

## Matching — min 2 pairs
Pairs of `=left -> right`, no braces content other than pairs.
Every entry must contain `->` or import fails.
No feedback, no weights.
```
::Capitals::Match country to capital. {
=Canada -> Ottawa
=Italy -> Rome
=Japan -> Tokyo
}
```
Moodle's matching question type wants 3+ pairs to render sensibly; the GIFT importer only enforces 2.

## Description
No braces at all — text only.
Renders as a passage with no answer, mark 0.
```
::Intro::The following questions all refer to Figure 1.
```

---

## Divergences from `GIFT_format.md`
The original doc is wrong or misleading in three places:
1. Its symbol table lists `(` / `)` as answer delimiters; braces are correct (its own prose says so at line 34).
2. It implies `#` weights/feedback work uniformly. They do not — see the `~` vs `=` rule.
3. Its True/False section (lines 69–79) is unwritten notes. The `&nbsp;` feedback-hiding trick it mentions is a Moodle *lesson* behaviour, not a GIFT parser feature.
