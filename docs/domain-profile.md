# The course domain profile

A local model knows a lot, fuzzily. Asked to organise a week on creative coding, it blends p5.js with
Processing because they share an API vocabulary — and a **transcript can drift the same way**. The
domain profile is how a course pins the model (and corrects a drifting source) to the right knowledge
domain.

It is one file — `<course root>/.vtconfig/domain.md` — a short paragraph you write in your own words.
It is prepended, as authoritative, to the system prompt of **every** generator: pages *and* quizzes,
because a quiz can slip into the wrong dialect just as easily as a page.

## What it does

- **States the domain** (what the course *is*) and its **negative space** (what it is *not*, and the
  adjacent things it gets confused with).
- Instructs the model to **silently correct** material that drifts — a transcript that says
  `size(400,400)` / `int x` gets presented as `createCanvas(400,400)` / `let x`, with no note about
  the discrepancy. It is a correction layer, not just a description.

It is **prose, not rules** — deliberately. Banning tokens like `int` doesn't work (`int` is a fine
variable name); the profile describes the *domain*, and the model applies judgement.

## How to write one

Describe the domain positively, then draw its negative space, then give a few concrete do/don't
pairs. Keep it short.

```markdown
<!-- <course root>/.vtconfig/domain.md -->
This course teaches creative coding in **p5.js** — JavaScript running in the p5.js library.

It is **not** Processing (Java) and not "Processing.js". Where source material uses Processing
conventions, express the same idea in p5.js:

- Declare variables with `let` / `const` — never `int`, `float`, or `void`.
- Create the canvas with `createCanvas(w, h)` — never `size(w, h)`.
- Structure with `function setup() {…}` and `function draw() {…}`.
- Shape signatures are p5.js: `circle(x, y, d)`, `ellipse(x, y, w, h)`, `rect(x, y, w, h)`.

All code shown to students must be valid p5.js / JavaScript.
```

That's it. There's no schema and nothing to enable — if the file exists, every generator uses it; if
it doesn't, nothing changes.

## What it does not do

It steers and corrects; it does not *guarantee*. A prompt is not a hard filter, and a local model can
still slip. If a domain needs a hard guarantee (say, code that must come only from the transcript,
never synthesised), that is a stronger, more restrictive mode — deferred until a course needs it. For
now the profile is the cheapest, most general tool, and it is the right first line: one paragraph,
authored once, protecting every artifact the course generates.
