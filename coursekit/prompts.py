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

from dataclasses import dataclass
from pathlib import Path

# Shipped defaults live beside the repo root, matching the transcriber's layout.
_SHIPPED = Path(__file__).resolve().parent.parent / "prompts"
_OVERRIDE_SUBDIR = Path(".vtconfig") / "prompts"


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
        """Substitute {placeholders}. Raises KeyError naming any that are missing."""
        return self.body.format(**values) if values else self.body


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter, body). Frontmatter is optional; a file without it is all body."""
    if not text.startswith("---"):
        return {}, text.strip()
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text.strip()
    raw, body = text[3:end], text[end + 4:]
    try:
        import yaml
        meta = yaml.safe_load(raw) or {}
    except ImportError:  # degrade rather than fail — the body is what matters
        meta = {}
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
