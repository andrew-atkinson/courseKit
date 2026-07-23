# Page design — themes and the visual system

A page's *content* is neutral (`page.json`); its *look* is a **theme** resolved at render time. A
course picks one theme, the renderer draws every component in that theme's inline styles, and the
same neutral page can be re-rendered in any theme — model-free — with `--to-html`.

The system's first principle: **taste lives in the themes, not the model.** The model decides
*meaning* (what kind of section this is); the theme decides *look*. And **colour is reserved for
semantic signal, never decoration** — the accent marks what matters; a section's role picks its
colour, the way syntax highlighting colours a keyword differently from a string.

## Choosing a theme

```yaml
# <course root>/.vtconfig/style.yaml
theme:  terminal        # bauhaus (default) | terminal | plotter | studio
accent: "#0E6B59"       # optional: override the accent (WCAG-checked; a bad one is rejected + warned)
density: comfortable    # optional: comfortable | compact
```

Then generate (or re-render) pages — the theme applies at render, so switching it is instant:

```bash
uv run python app.py --to-html "<course root>/pages"
```

## The four identities

Each is a full design identity — type, colour, spacing, shape, and per-component treatment — not a
palette swap. They exist to be distinct; the collection is meant to read like a style-guide book.

| Theme | Voice | Signature move |
| --- | --- | --- |
| **bauhaus** *(default)* | Form follows function | Geometric sans, heavy weight, thick cobalt bars on headings |
| **terminal** | A Powerlevel10k reading of a page | Deep-petrol section panels; headings are role-coloured Powerline segment chips with CSS chevrons |
| **plotter** | Pen on paper, by machine | Slate + riso-teal, dashed registration hairlines framing each concept |
| **studio** | The gallery wall (for image-led courses) | Big Didot display serif, hairline frames, the images carry the colour |

## Section roles — where design meets pedagogy

A heading can carry a **role** — `review · concept · practice · example · summary` — which the model
assigns as *meaning*. Each theme renders roles its own way: terminal colours the segment chip by
role (concept → blue "path" segment, practice → amber "git" segment, summary → green "success"), and
themes may frame only certain roles (plotter boxes concepts, leaves review flat). The role is never
a style; it is a semantic marker the theme interprets. This is the Cognitive-Load-Theory idea of
*signalling* and *chunking* made visual.

## The guardrails (why a theme can't ship something broken)

Three checks, in the same spirit as the no-URL rule — enforced by tests, not vibes:

- **Canvas property allowlist.** Every inline style the renderer emits uses a CSS property Canvas's
  own sanitizer keeps (transcribed from `canvas_sanitize.rb`). A theme literally cannot emit styling
  Canvas would strip.
- **WCAG AA contrast.** Ink, accent-as-text, tints, segment chips, code, and any surface all clear
  4.5:1 — validated against each theme's own ground (terminal's dark petrol, not white). An
  unreadable accent override is rejected with a warning and falls back.
- **Accessibility of media.** Every image ships with alt text (an image with no alt or caption is
  dropped, not shipped inaccessible); every embed iframe carries a title.

## Authoring a new theme

Copy a `themes/<name>.yaml`, give it a `voice` and its five dimensions (type, color, space, shape,
glyphs), and run the suite — the WCAG and allowlist tests police it. It's available immediately as a
`theme:` choice; nothing else to register.

> **Roadmap:** the model does not generate themes yet — a course picks one. A later step lets it
> *suggest* a theme + accent from a prose brief (choosing among curated options, so the taste risk
> stays contained). Syntax-highlighting of code blocks — the same "token type → colour" idea applied
> inside code — is planned; see `agent/todo.md`.
