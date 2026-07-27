# The course domain profile

A local model knows a lot, fuzzily. Asked to organise a week on creative coding, it blends p5.js with Processing because they share an API vocabulary — and a **transcript can drift the same way**. The domain profile is how a course pins the model to the right domain, tells it **what a page should center on**, and corrects a drifting source.

It is one file — `<course root>/.vtconfig/domain.md` — a short paragraph you write in your own words. It is prepended, as authoritative, to the system prompt of **every** generator: pages _and_ quizzes, because a quiz can slip into the wrong dialect just as easily as a page.

## What it does

- **States the domain** (what the course _is_) and its **negative space** (what it is _not_, and the adjacent things it gets confused with).
- **Says what a page centers on.** The shipped prompts are discipline-neutral on purpose — they don't assume code. The profile is where a course declares its _content shape_: a coding course centers on code and worked programs; a photography course on technique, images, and visual analysis; a seminar on cases and argument. This is what keeps a photo course from getting a page that hunts for code that isn't there.
- **Silently corrects** material that drifts — a transcript that says `size(400,400)` / `int x` gets presented as `createCanvas(400,400)` / `let x`, with no note about the discrepancy. It is a correction layer, not just a description.

It is **prose, not rules** — deliberately. Banning tokens like `int` doesn't work (`int` is a fine variable name); the profile describes the _domain_, and the model applies judgement.

## How to write one

Describe the domain positively, say what its pages should foreground, draw its negative space, then give a few concrete do/don't pairs. Keep it short.

A coding course, where the correction job matters most:

```markdown
<!-- <course root>/.vtconfig/domain.md -->

This course teaches creative coding in **p5.js** — JavaScript running in the p5.js library. Pages center on code and the sketches it produces.

It is **not** Processing (Java) and not "Processing.js". Where source material uses Processing conventions, express the same idea in p5.js:

- Declare variables with `let` / `const` — never `int`, `float`, or `void`.
- Create the canvas with `createCanvas(w, h)` — never `size(w, h)`.
- Structure with `function setup() {…}` and `function draw() {…}`.
- Shape signatures are p5.js: `circle(x, y, d)`, `ellipse(x, y, w, h)`, `rect(x, y, w, h)`.

All code shown to students must be valid p5.js / JavaScript. Where the material has code, a
**code-completion** quiz question (read code with a gap, pick what belongs) fits well.
```

A non-coding course, where the content-shape job matters most:

```markdown
<!-- <course root>/.vtconfig/domain.md -->

This course teaches **digital photography and image-making** — students make, edit, and critique photographs. Pages center on **technique, visual analysis, and worked image examples**, not code: there is no programming in this course.

- Foreground how an image is made and read: exposure, composition, light, colour, editing decisions.
- "Worked examples" are annotated images and shooting/editing setups — describe them in words; the instructor supplies the actual images through the course's own files.
- Vocabulary is photographic (aperture, shutter, ISO, white balance, histogram), not computational.
- Never present a technique as code or pseudocode; describe the physical or editing steps.
```

The profile also steers **quiz question forms**, not just page content. The quiz brief is
subject-neutral by default (five concepts, a mix of types); the domain note is where a course earns
its specifics — the coding note above draws code-completion questions where code exists, while the
photo note keeps questions to identifying, comparing, and analysing images. No profile means no
steer: the neutral brief still generates, just without a discipline's slant.

That's it. There's no schema and nothing to enable — if the file exists, every generator uses it; if it doesn't, nothing changes.

## What it does not do

It steers and corrects; it does not _guarantee_. A prompt is not a hard filter, and a local model can still slip. If a domain needs a hard guarantee (say, code that must come only from the transcript, never synthesised), that is a stronger, more restrictive mode — deferred until a course needs it. For now the profile is the cheapest, most general tool, and it is the right first line: one paragraph, authored once, protecting every artifact the course generates.
