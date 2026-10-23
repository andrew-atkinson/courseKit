"""Prompt library.

Prompts are Markdown files with YAML frontmatter, organised by category — the same scheme the
videotranscriber uses, so the two tools share one mechanism rather than each inventing its own:

    prompts/
        quiz/
            system.md
            task.md

    ---
    name: system
    category: quiz
    description: The rules governing how the model records questions
    ---
    You write assessment items for a university course...

Two roots are consulted, **project override first, shipped default second**, so an instructor
or a department can drop `<course>/.vtconfig/prompts/quiz/task.md` to change the brief without
touching the tool. That override path is what "shared prompt libraries" means in practice: the
prompt is governed content, versioned next to the course, not a string buried in code.

Bodies may contain `{placeholders}` filled by the caller — kept explicit rather than templated
here, because a missing placeholder should be the caller's error, not a silent empty string.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from coursekit.outcomes import CoursekitError

# Shipped defaults live beside the repo root, matching the transcriber's layout.
_SHIPPED = Path(__file__).resolve().parent.parent / "prompts"
_OVERRIDE_SUBDIR = Path(".vtconfig") / "prompts"


_PLACEHOLDER = re.compile(r"\{(\w+)\}")


class PromptNotFound(LookupError):
    """No prompt of that category/name in any root."""


@dataclass(frozen=True)
class Prompt:
    name: str
    category: str
    description: str
    body: str
    path: Path

    def render(self, **values) -> str:
        """Fill the named `{placeholders}` given in `values`, in ONE pass over the template (inserted
        text is never re-scanned). Every other brace is left exactly as written — a course's prompt
        override may contain example code (`for (...) { }`, `f"{i}"`, `{{ }}`). Deliberately NOT
        `str.format`, which parses every brace and crashes on literal ones. A placeholder no caller
        fills stays visible in the text rather than raising (it can't be told apart from code)."""
        if not values:
            return self.body
        return _PLACEHOLDER.sub(
            lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), self.body)


def require(prompt: Prompt, *names: str) -> None:
    """Refuse a prompt whose template lacks a placeholder the caller fills with essential content —
    e.g. a course override of system.md that dropped `{transcript}` would otherwise send the model no
    course material at all, silently. A user-config error, raised with an actionable message before any
    model call."""
    missing = [n for n in names if "{" + n + "}" not in prompt.body]
    if missing:
        tags = ", ".join("{" + n + "}" for n in missing)
        raise CoursekitError(
            f"prompt {prompt.path} has no {tags} placeholder, so that content would never reach the "
            f"model. Add {tags} where it belongs — the shipped prompts in prompts/{prompt.category}/ "
            f"show the expected placement.",
            code="prompt.missing_placeholder", details={"path": str(prompt.path), "missing": missing})


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter, body). Frontmatter is optional; a file without it is all body."""
    if not text.startswith("---"):
        return {}, text.strip()
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text.strip()
    raw, body = text[3:end], text[end + 4:]
    import yaml
    meta = yaml.safe_load(raw) or {}
    return (meta if isinstance(meta, dict) else {}), body.strip()


def _roots(project_root=None) -> list[Path]:
    roots = []
    if project_root:
        roots.append(Path(project_root) / _OVERRIDE_SUBDIR)
    roots.append(_SHIPPED)
    return roots


def load(category: str, name: str = "default", *, project_root=None) -> Prompt:
    """Load one prompt. Project overrides win over shipped defaults."""
    for root in _roots(project_root):
        path = root / category / f"{name}.md"
        if path.is_file():
            meta, body = _split_frontmatter(path.read_text(encoding="utf-8"))
            return Prompt(name=meta.get("name", name),
                          category=meta.get("category", category),
                          description=meta.get("description", ""),
                          body=body, path=path)
    tried = ", ".join(str(r / category / f"{name}.md") for r in _roots(project_root))
    raise PromptNotFound(f"no prompt '{category}/{name}'. Looked in: {tried}")


def available(category: str, *, project_root=None) -> list[str]:
    """Every prompt name in a category, overrides and defaults merged."""
    names = set()
    for root in _roots(project_root):
        d = root / category
        if d.is_dir():
            names.update(p.stem for p in d.glob("*.md"))
    return sorted(names)
