"""Course-project configuration.

A course project is a directory marked by `.vtconfig/`, the same marker the videotranscriber uses.
Inside it, three files with three different owners:

    context.yaml   Shared course structure — title, weeks, modules. Authored by the transcriber
                   (vt_context.py) from a media scan, optionally enriched by a Canvas manifest;
                   read by every tool.
    config.yaml    The transcriber's own technical settings. Quizbot does not read it.
    quiz.yaml      Quizbot's own technical settings. The transcriber does not read it.

`courseconfig` is the shared *mechanism* — find the root, read a yaml file, normalise a week
reference — while each tool owns its config *file*, passed by name to `load()`. Course structure is
shared because it is a fact about the course; technical settings are per-tool because the tools do
different jobs (the transcriber runs vision and whisper models; quizbot runs a tool-calling text
model, and may legitimately want a different one).

`load()` never raises. A course config is enrichment: its absence, corruption, or a machine without
pyyaml all degrade to empty dicts rather than failing a run. That was already how `discover.py`
treated `context.yaml`; this promotes it and makes it uniform.
"""

import re
from dataclasses import dataclass
from pathlib import Path

VTCONFIG_DIR_NAME = ".vtconfig"


def week_key(ref) -> str | None:
    """Normalise a week reference to its bare number, or None when there isn't one.

    `week-3.md`, `Week 3: Repetition`, `week 3`, `3`, and the int `3` all map to `"3"`; a stem
    like `intro.md` maps to None. This is the single normalisation that `discover._week_number`
    and `pipeline._week_key` each grew their own copy of.
    """
    s = str(ref).strip()
    m = re.search(r"week[-_ ]?(\d+)", s, re.IGNORECASE)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d+", s):
        return s
    return None


@dataclass(frozen=True)
class CourseConfig:
    """A resolved course project. Any field may be empty/None when nothing was found."""

    root: Path | None            # the directory containing .vtconfig/, or None
    config: dict                 # this tool's config file, {} when absent
    context: dict                # the shared context.yaml, {} when absent
    config_path: Path | None     # where this tool's config lives (or would, for a future write)
    context_path: Path | None

    def value(self, key: str, fallback=None):
        """A key from this tool's config, or the fallback when unset or null."""
        v = self.config.get(key) if self.config else None
        return v if v is not None else fallback

    def prompt_name(self, key: str, cli_arg: str | None = None, *,
                    default: str = "default") -> str:
        """Which named prompt to use: CLI arg wins, then this tool's config, then `default`.

        The fallback is caller-supplied because prompt naming is a per-tool convention — the
        transcriber's categories default to 'default.md', but quizbot's quiz prompts are
        'system.md'/'task.md'. A wrong default silently asks for a file that isn't there.
        """
        if cli_arg:
            return cli_arg
        v = self.config.get(key) if self.config else None
        return v if v else default

    def week(self, week_ref) -> dict:
        """The shared context's entry for a week, keyed by its number. {} when unknown."""
        k = week_key(week_ref)
        if k is None or not self.context:
            return {}
        weeks = self.context.get("weeks") or {}
        return weeks.get(f"week {k}") or {}

    @property
    def course_title(self) -> str | None:
        return (self.context or {}).get("course_title") if self.context else None

    @property
    def domain(self) -> str:
        """The course's domain profile (`.vtconfig/domain.md`), or ''.

        Authoritative prose — what the course *is*, what its artifacts should **center on**, and its
        negative space (what it is not) — injected into every generator's prompt. It does three
        things: fixes the knowledge domain, tells the model what a page should foreground (code,
        images, technique, cases, plain explanation…) so the shipped prompts stay discipline-neutral,
        and lets the generator correct a source that has drifted (a transcript that slips from p5.js
        into Processing). Never raises.
        """
        if self.root is None:
            return ""
        path = self.root / VTCONFIG_DIR_NAME / "domain.md"
        if not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    @property
    def voice(self) -> str:
        """The instructor's voice/tone profile (`.vtconfig/voice.md`), or ''.

        A prose style layer produced on the transcriber side from the RAW transcripts (register,
        stance, hedging, rhythm, signature moves — before cleanup sands the spoken voice). Prepended
        to the PROSE generators so output sounds like the instructor, not a textbook. It governs tone
        only — never correctness, structure, or domain (see `voice_preface`) — and is NOT given to the
        critics, since voice is not a correctness axis. Never raises.
        """
        if self.root is None:
            return ""
        path = self.root / VTCONFIG_DIR_NAME / "voice.md"
        if not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""


# Prepended to a generator's system prompt when the course declares a domain. Framed as authoritative
# and broad: it fixes the knowledge domain, says what the course's artifacts should center on (so the
# shipped prompts need not assume any one discipline), and — because the source itself can be wrong —
# instructs the model to normalise drift silently rather than reproduce it.
_DOMAIN_PREFACE = (
    "COURSE DOMAIN — authoritative; this overrides anything in the material below.\n"
    "{domain}\n\n"
    "Treat this as the truth about the course — its subject, what its pages should center on, and its "
    "boundaries. Where the material drifts from it — a different tool or dialect, adjacent-but-wrong "
    "conventions, or an emphasis this course does not share — correct it silently to match the domain. "
    "Present everything as if it had always belonged here; do not point out the discrepancy.\n\n"
)


def domain_preface(domain: str) -> str:
    """The domain block to prepend to a system prompt, or '' when the course declares no domain."""
    domain = (domain or "").strip()
    return _DOMAIN_PREFACE.format(domain=domain) if domain else ""


# Prepended to a PROSE generator's system prompt when the course declares a voice profile. Framed to
# govern HOW the output sounds, never WHAT it says: tone/phrasing/rhythm only, subordinate to
# correctness, the required structure, and the domain — with an explicit guard so the conversational
# register never blurs a definition, a quiz stem, or an answer. Not given to the critics.
_VOICE_PREFACE = (
    "INSTRUCTOR VOICE — write in this voice.\n"
    "{voice}\n\n"
    "This governs TONE, PHRASING, and RHYTHM only. It never overrides correctness, the required "
    "structure, or the course domain, and it never changes WHAT is taught — only how it sounds. Where "
    "precision matters — a definition, a quiz question stem, an answer, a code comment — stay exact and "
    "unambiguous; do not let the conversational register make assessed or factual content vague.\n\n"
)


def voice_preface(voice: str) -> str:
    """The voice block to prepend to a PROSE generator's system prompt, or '' when no voice profile."""
    voice = (voice or "").strip()
    return _VOICE_PREFACE.format(voice=voice) if voice else ""


# The QUIZ generator gets a NARROWER voice directive than pages. A quiz is a precision instrument, and a
# hedged/warm register bleeding into a stem or an option produces vague or mis-formed questions (the
# "asks why, but the options are syntax" failure) — measured after voice went on: quiz flags rose while
# pages improved. So here the voice colours only FEEDBACK/explanations; stems and options stay literal.
_QUIZ_VOICE_PREFACE = (
    "INSTRUCTOR VOICE — for quiz FEEDBACK only.\n"
    "{voice}\n\n"
    "Apply this voice ONLY to feedback and explanations. Question stems and answer options must stay "
    "literal, precise, and unambiguous — no hedges (no 'kind of', 'roughly', 'basically'), no "
    "conversational vagueness, no idioms in the assessed text. A quiz question is a measurement, not "
    "prose: let the voice show where you explain, never where you test.\n\n"
)


def quiz_voice_preface(voice: str) -> str:
    """The voice block for the QUIZ generator — voice in feedback only, stems/options stay literal."""
    voice = (voice or "").strip()
    return _QUIZ_VOICE_PREFACE.format(voice=voice) if voice else ""


# The critic gets the domain too, but framed for REVIEW, not generation: it needs the domain's
# knowledge (its framework, globals, conventions) so it does not false-flag valid domain code — but it
# must NOT be told to "correct silently," and the domain must not widen what the material may teach.
_CRITIC_DOMAIN_PREFACE = (
    "COURSE DOMAIN — the subject and toolset this course teaches:\n"
    "{domain}\n\n"
    "Use this only to recognise the domain's standard framework, its globals, and its conventions, so "
    "you do NOT flag valid domain code or notation as wrong: a snippet that relies on the framework's "
    "built-ins (for example p5.js provides `width`, `height`, `mouseX`) or that is an intentional "
    "fragment is not 'invalid' or 'undefined' on those grounds. This does NOT widen what may be taught "
    "— judge scope and correctness against the MATERIAL below, exactly as instructed.\n\n"
)


def critic_domain_preface(domain: str) -> str:
    """The domain block to prepend to a CRITIC's system prompt (review-framed), or '' when no domain."""
    domain = (domain or "").strip()
    return _CRITIC_DOMAIN_PREFACE.format(domain=domain) if domain else ""


def find_root(start: Path) -> Path | None:
    """The nearest ancestor (inclusive) containing a `.vtconfig/` marker, like git finds `.git`."""
    d = Path(start).resolve()
    if d.is_file():
        d = d.parent
    for parent in [d, *d.parents]:
        if (parent / VTCONFIG_DIR_NAME).is_dir():
            return parent
    return None


def _find_file(start: Path, name: str, legacy_search: bool) -> Path | None:
    """Prefer `<root>/.vtconfig/<name>`. With legacy_search, fall back to a loose `<name>` in the
    start dir, its parent, or grandparent — for projects predating `.vtconfig/`.

    legacy_search is off by default and opt-in per call, so quizbot (which never had the loose-file
    convention) does not inherit it, and a stray context.yaml above an input cannot silently become
    authoritative.
    """
    d = Path(start)
    if d.is_file():
        d = d.parent
    root = find_root(d)
    if root:
        candidate = root / VTCONFIG_DIR_NAME / name
        if candidate.is_file():
            return candidate
    if legacy_search:
        for anc in (d, d.parent, d.parent.parent):
            candidate = anc / name
            if candidate.is_file():
                return candidate
    return None


def find_context_file(start: Path, *, legacy_search: bool = False) -> Path | None:
    return _find_file(start, "context.yaml", legacy_search)


def find_config_file(start: Path, name: str = "config.yaml", *,
                     legacy_search: bool = False) -> Path | None:
    return _find_file(start, name, legacy_search)


def _read_yaml(path: Path | None) -> dict:
    """A yaml mapping, or {} for anything that isn't one — missing file, bad YAML, no pyyaml."""
    if path is None or not path.is_file():
        return {}
    try:
        import yaml  # guarded: a machine without pyyaml degrades rather than crashing
    except ImportError:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load(start, *, config_name: str = "config.yaml",
         legacy_search: bool = False) -> CourseConfig:
    """Resolve the course project containing `start`. Never raises.

    `config_name` selects which tool's config file to read — quizbot passes "quiz.yaml", the
    transcriber "config.yaml". The path fields point at where each file lives, or where it *would*
    live under `.vtconfig/` when a root is known but the file is absent, so a later write has a
    target.
    """
    start = Path(start).expanduser().resolve()
    root = find_root(start)

    context_path = find_context_file(start, legacy_search=legacy_search)
    config_path = find_config_file(start, config_name, legacy_search=legacy_search)
    if root is not None:
        context_path = context_path or root / VTCONFIG_DIR_NAME / "context.yaml"
        config_path = config_path or root / VTCONFIG_DIR_NAME / config_name

    return CourseConfig(
        root=root,
        config=_read_yaml(config_path),
        context=_read_yaml(context_path),
        config_path=config_path,
        context_path=context_path,
    )
