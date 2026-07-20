# Authoring course pages

A page has **two authors**, and keeping them apart is what keeps the page trustworthy:

- **The model** writes the teaching outline from the week's transcript — headings, concept bullets,
  code, glossary, callouts. It never writes a link.
- **You** supply everything that carries a URL — references, example works, and embeds (p5 sketches,
  slideshows, videos) — in a small YAML file. These are merged in when the page is *rendered*, so
  they survive a regeneration of the model's part and their URLs land exactly as you wrote them.

The model's part is `page.json`; your part is a YAML file in `<course root>/.vtconfig/pages/`.

**You don't have to guess the exact slug.** The file is matched by **week identity**, not an exact
name — any file in that folder whose name resolves to the same week works. For Week 3, all of these
match: `week-3.yaml`, `week-3-repetition.yaml`, `week 3.yaml`. Name it whatever reads well to you.

(The generated page itself is named from the week title — `Week 3: Repetition` →
`week-3-repetition.html` — so it matches how the page appears in Canvas.)

## The supplements file

Every key is optional. A minimal file is just a couple of references.

```yaml
# <course root>/.vtconfig/pages/week-3-repetition.yaml

# Curated references — anything you want students to read or look at.
references:
  - label: "Casey Reas — Process Compendium"
    url:   "https://reas.com/"
  - label: "p5.js reference — for()"
    url:   "https://p5js.org/reference/p5/for/"

# Example works and class samples. `embed: true` renders as an <iframe> when the host is on the
# allowlist (below); otherwise it degrades to a plain link, so a page never emits an iframe that
# Canvas would strip.
examples:
  - label: "Week 3 — Loops (collection)"
    url:   "https://editor.p5js.org/andrew-atkinson/collections/cIwulq5Dk"
    # no `embed:` → a link

  - label: "Grid of circles"
    embed: true
    url:   "https://editor.p5js.org/andrew-atkinson/full/SOlYONlUZ"
    width: 410       # optional; defaults to 600 x 400
    height: 240

  # Or just paste the whole embed snippet a site gives you (Google Slides, Panopto, YouTube…):
  # the src, width, and height are read out of it and re-emitted as a clean, allowlisted iframe.
  - label: "Lecture slides"
    iframe: >
      <iframe src="https://docs.google.com/presentation/d/e/ABC/embed?start=false"
              width="960" height="569" allowfullscreen></iframe>
```

Two ways to give an embed, whichever is handier: the structured `url` + `embed: true` (+ optional
`width`/`height`), **or** an `iframe:` key holding the exact snippet the site hands you. Either way
the host must be on the allowlist below, or it renders as a plain link.

**Allowlisted embed hosts** (anything else becomes a link): `editor.p5js.org`, `youtube.com`,
`youtu.be`, `vimeo.com` / `player.vimeo.com`, `docs.google.com`, `drive.google.com`, `panopto.com`.
A Canvas-relative link (e.g. `$WIKI_REFERENCE$/files/…`) is fine as a `url` too — Canvas resolves it
on import.

You never edit `page.json` by hand: regenerating the page rewrites it, but never touches this file.

### Iterating without re-running the model

Adding or changing a supplement shouldn't cost a model run. After you've generated a page once, edit
its YAML and re-render everything, model-free:

```bash
uv run python app.py --to-html "<course root>/pages"
```

This reads each `page.json` and its current supplements and rewrites the HTML — instant, no model.
Refresh the page in your browser to see the change.

## What makes a good page

The model is prompted to build a **teaching outline**, not a transcript recap. A strong week page
tends to run:

1. A short **REVIEW** — what earlier weeks set up, as a few bullets (only when the week builds on
   them).
2. One **section per key concept** — a heading, a few concept bullets, and a code example where the
   week shows code.
3. A **glossary** of the week's terms.
4. A **callout** for a common pitfall.

Your references and examples render **below** all of that, as their own sections. So the shape a
student sees is: the model's outline, then your curated links and embeds.

### Steering the model per course

The page prompts are files, and a course can override them. Drop a replacement at
`<course root>/.vtconfig/prompts/page/task.md` (or `system.md`) to change the brief for that course
only — heading house style, how much detail, which sections to include — without touching anyone
else's pages. Anything you don't override falls back to the shipped prompt.

To keep the model in the right *knowledge* domain — the right language, framework, or vocabulary, and
to correct a transcript that drifts out of it — write a **[domain profile](domain-profile.md)**
(`.vtconfig/domain.md`). It applies to pages and quizzes alike.
