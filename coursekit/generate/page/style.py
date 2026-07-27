"""Design identities for pages: themes, tokens, and the Canvas-safe style guardrails.

A **theme** is a full design identity — a type system, a color system, a spacing rhythm, a shape
language, and per-component treatments — shipped as `themes/<name>.yaml`. A course selects one (and
may apply constrained overrides) in `.vtconfig/style.yaml`. The collection of themes is meant to
read like a style guide book: each has a voice, and none of them is "a token swap" of another.

Two guardrails make the system trustworthy, in the same spirit as the no-URL rule:

- **The CSS property allowlist.** Every inline style the skin emits must use a property Canvas's
  sanitizer keeps. The list below is transcribed from Canvas's own open-source sanitizer
  (`gems/canvas_sanitize/lib/canvas_sanitize/canvas_sanitize.rb` in instructure/canvas-lms),
  intersected with what we actually need; properties also observed surviving in real exported
  course pages are marked. A property not on this list cannot ship, so a theme cannot silently
  produce styling Canvas would strip.
- **WCAG AA contrast validation.** Ink on white, accent-as-text on white, and ink on every tint
  must clear 4.5:1. A theme (or a course override) that fails is rejected loudly — accessible
  contrast is not a style preference.

Style is resolved at **render time**, exactly like supplements: `page.json` stays neutral, and a
theme change re-renders model-free via `--to-html`.
"""

from pathlib import Path

# ---------------------------------------------------------------- allowlist

# Transcribed from canvas_sanitize.rb (Canvas's sanitizer allows ~90 properties; this is the subset
# the skins are permitted to emit). "observed" = also seen surviving in real exported course pages.
ALLOWED_CSS_PROPERTIES = frozenset({
    # layout
    "display",                      # observed (inline-block, none)
    "float", "clear", "overflow", "overflow-x", "overflow-y", "vertical-align",
    # flexbox (sanitizer-confirmed)
    "flex", "flex-basis", "flex-direction", "flex-flow", "flex-grow", "flex-shrink", "flex-wrap",
    "justify-content", "align-content", "align-items", "align-self",
    "gap", "column-gap", "row-gap",
    # sizing
    "width", "height", "min-width", "max-width", "min-height", "max-height",  # width/height observed
    # spacing
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",   # observed
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",  # observed
    # borders & surfaces
    "border", "border-top", "border-right", "border-bottom", "border-left",   # observed
    "border-radius",                # observed
    "background-color",             # observed
    # typography
    "color",                        # observed
    "font-family", "font-size", "font-style", "font-weight", "line-height",
    "text-align",                   # observed
    "text-decoration", "text-indent", "white-space",
    "list-style-type",              # observed
    "cursor",                       # for action affordances (a control you press), not decoration
})


# ------------------------------------------------------------- WCAG contrast

def _srgb_channel(v: float) -> float:
    v = v / 255.0
    return v / 12.92 if v <= 0.04045 * 255 / 255 else ((v + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _srgb_channel(r) + 0.7152 * _srgb_channel(g) + 0.0722 * _srgb_channel(b)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio between two hex colors."""
    la, lb = _luminance(a), _luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _rgb_to_hex(rgb) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in rgb)


def colour_scheme(main: str) -> dict:
    """A three-colour starting scheme from one seed, for authoring a new theme's palette:

    - **main** — the seed, as given.
    - **secondary** — the main desaturated to 60% of its saturation (a quieter partner).
    - **contrast** — the main's hue rotated 117° round the wheel (a near-triad accent).

    Returns `{"main", "secondary", "contrast"}` as hex. A starting point, not a guarantee — run the
    results through `contrast_ratio` / `validate_theme` before shipping them in a theme.
    """
    import colorsys
    h, l, s = colorsys.rgb_to_hls(*_hex_to_rgb(main))
    secondary = colorsys.hls_to_rgb(h, l, s * 0.6)
    contrast = colorsys.hls_to_rgb((h + 117 / 360) % 1.0, l, s)
    return {"main": _rgb_to_hex(_hex_to_rgb(main)),
            "secondary": _rgb_to_hex(secondary),
            "contrast": _rgb_to_hex(contrast)}


WHITE = "#ffffff"   # Canvas renders pages on white. A theme may declare its own color.surface
                    # (a full-bleed panel the renderer wraps content in); contrast is then
                    # validated against that surface instead.


def validate_theme(theme: dict) -> list[str]:
    """Reasons a theme fails its guardrails. Empty list = valid.

    Checks every color parses, and the AA (4.5:1) pairs: ink/white, accent/white (kickers and
    markers set accent as text), and ink on every tint (cards and callouts put body text on tints).
    """
    problems = []
    color = theme.get("color") or {}

    def _check_hex(name, value):
        try:
            _luminance(value)
            return True
        except Exception:
            problems.append(f"color.{name} ('{value}') is not a valid hex color")
            return False

    ink = color.get("ink", "#000000")
    accent = color.get("accent", "#000000")
    surface = color.get("surface", WHITE)
    ok_ink = _check_hex("ink", ink)
    ok_accent = _check_hex("accent", accent)
    if not _check_hex("surface", surface):
        surface = WHITE

    if ok_ink and contrast_ratio(ink, surface) < 4.5:
        problems.append(f"ink {ink} fails WCAG AA on the surface ({contrast_ratio(ink, surface):.1f}:1 < 4.5:1)")
    if ok_accent and contrast_ratio(accent, surface) < 4.5:
        problems.append(f"accent {accent} fails WCAG AA as text on the surface "
                        f"({contrast_ratio(accent, surface):.1f}:1 < 4.5:1)")
    for name, tint in (color.get("tints") or {}).items():
        if _check_hex(f"tints.{name}", tint) and ok_ink and contrast_ratio(ink, tint) < 4.5:
            problems.append(f"ink on tints.{name} ({tint}) fails WCAG AA "
                            f"({contrast_ratio(ink, tint):.1f}:1 < 4.5:1)")

    frame_bg = color.get("frame_bg")
    if frame_bg and _check_hex("frame_bg", frame_bg) and ok_ink and contrast_ratio(ink, frame_bg) < 4.5:
        problems.append(f"ink on frame_bg ({frame_bg}) fails WCAG AA")

    # The recap answers (and other secondary text) are `muted` on the page ground — it must stay
    # legible there, since a recap's question is ink but its answer recedes to muted.
    page_muted = color.get("muted")
    if page_muted and _check_hex("muted", page_muted) and contrast_ratio(page_muted, surface) < 4.5:
        problems.append(f"muted {page_muted} on the surface fails WCAG AA "
                        f"({contrast_ratio(page_muted, surface):.1f}:1 < 4.5:1)")

    # A theme may give the recap its own ground (recap_bg) + palette (recap_ink question, recap_muted
    # answer) — a light-mode note on a dark identity. Validate THAT pair, not the page ink.
    recap_bg = color.get("recap_bg")
    if recap_bg and _check_hex("recap_bg", recap_bg):
        r_ink = color.get("recap_ink", ink)
        r_muted = color.get("recap_muted", color.get("muted", ink))
        if _check_hex("recap_ink", r_ink) and contrast_ratio(r_ink, recap_bg) < 4.5:
            problems.append(f"recap question {r_ink} on recap_bg {recap_bg} fails WCAG AA "
                            f"({contrast_ratio(r_ink, recap_bg):.1f}:1 < 4.5:1)")
        if _check_hex("recap_muted", r_muted) and contrast_ratio(r_muted, recap_bg) < 4.5:
            problems.append(f"recap answer {r_muted} on recap_bg {recap_bg} fails WCAG AA "
                            f"({contrast_ratio(r_muted, recap_bg):.1f}:1 < 4.5:1)")

    # Segment chips (terminal's Powerlevel10k language): role-colored pills; the chip text
    # (segment_ink) must clear AA on every chip color.
    segments = color.get("segments") or {}
    seg_ink = color.get("segment_ink", "#ffffff")
    if segments and _check_hex("segment_ink", seg_ink):
        for nm, c in segments.items():
            if _check_hex(f"segments.{nm}", c) and contrast_ratio(seg_ink, c) < 4.5:
                problems.append(f"segment_ink on segments.{nm} ({c}) fails WCAG AA "
                                f"({contrast_ratio(seg_ink, c):.1f}:1 < 4.5:1)")

    # Code blocks carry their own fg/bg pair (a dark block is a legitimate identity move).
    code_bg, code_fg = color.get("code_bg"), color.get("code_fg")
    if code_bg and code_fg and _check_hex("code_bg", code_bg) and _check_hex("code_fg", code_fg):
        if contrast_ratio(code_fg, code_bg) < 4.5:
            problems.append(f"code_fg on code_bg fails WCAG AA "
                            f"({contrast_ratio(code_fg, code_bg):.1f}:1 < 4.5:1)")
    return problems


# ---------------------------------------------------------------- loading

_SHIPPED_THEMES = Path(__file__).resolve().parents[3] / "themes"
DEFAULT_THEME = "bauhaus"


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def available_themes() -> list[str]:
    if not _SHIPPED_THEMES.is_dir():
        return []
    return sorted(p.stem for p in _SHIPPED_THEMES.glob("*.yaml"))


def load_theme(name: str) -> dict:
    """One shipped theme by name; {} when unknown (callers fall back to DEFAULT_THEME)."""
    return _read_yaml(_SHIPPED_THEMES / f"{name}.yaml")


def load_style(course_root) -> dict:
    """Resolve a course's style: `.vtconfig/style.yaml` selects a theme + constrained overrides.

    Never raises. Absent/invalid degrades to the default theme. An override that breaks a
    guardrail (e.g. an unreadable accent) is dropped with the theme's own value kept — the
    validation message is surfaced under '_problems' for the caller to show.
    """
    selection = {}
    if course_root:
        selection = _read_yaml(Path(course_root) / ".vtconfig" / "style.yaml")

    name = selection.get("theme") or DEFAULT_THEME
    theme = load_theme(name)
    if not theme:
        theme = load_theme(DEFAULT_THEME)
        name = DEFAULT_THEME
    theme = dict(theme)
    theme["_name"] = name
    problems = []

    # Constrained overrides: accent (WCAG-checked), density, radius.
    if selection.get("accent"):
        candidate = dict(theme)
        candidate["color"] = dict(theme.get("color") or {})
        candidate["color"]["accent"] = selection["accent"]
        if validate_theme(candidate):
            problems.append(f"style.yaml accent '{selection['accent']}' rejected: "
                            + "; ".join(validate_theme(candidate)))
        else:
            theme = candidate
    if selection.get("density") in ("comfortable", "compact"):
        theme.setdefault("space", {})
        theme["space"] = dict(theme["space"])
        theme["space"]["density"] = selection["density"]

    # The recap and key-terms labels are teaching-vocabulary choices, not visual ones — a course sets
    # them in style.yaml (`recap_label: "Last time"`, `glossary_label: "Vocabulary"`).
    if selection.get("recap_label"):
        theme["recap_label"] = str(selection["recap_label"])
    if selection.get("glossary_label"):
        theme["glossary_label"] = str(selection["glossary_label"])

    theme["_problems"] = problems
    return theme
