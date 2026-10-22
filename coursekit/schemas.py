"""Schemas for the `.vtconfig/` files a faculty member edits (CORE-1.3).

Every coursekit-owned settings file is read through a pydantic schema. A file that is absent means
"use the defaults"; a file that is present but unreadable or invalid is an error that names the file,
the key, the value, and what is allowed — never a silent fall-back to defaults. An unknown key is an
error too (with a "did you mean"), because a mistyped `eu_questoin` that is quietly ignored is the
same silent failure.

`check(root)` validates every file at once, for `coursekit check`. The settings API (CORE-1.4) writes
through these same schemas, and a GUI can build its forms from them (`model_json_schema()`).
`context.yaml` is the transcriber's file: it is only parse-checked here, never schema-validated.
"""

from difflib import get_close_matches
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator, model_validator

from coursekit.outcomes import CoursekitError

Key = Annotated[str, BeforeValidator(str)]           # YAML reads `5:` as an int; keys are labels
Count = Annotated[int, Field(ge=0)]


class _File(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------- per-tool settings
class QuizSettings(_File):
    model: str | None = None
    questions: int | None = Field(None, ge=1)
    eu_question: bool | None = None
    system_prompt: str | None = None
    task_prompt: str | None = None


class PageSettings(_File):
    model: str | None = None
    max_pass_chars: int | None = Field(None, ge=1)
    mono_char_budget: int | None = Field(None, ge=1)
    mono_concept_budget: int | None = Field(None, ge=1)
    system_prompt: str | None = None
    task_prompt: str | None = None


class EvaluateSettings(_File):
    model: str | None = None
    reads: int | None = Field(None, ge=1)


class IngestSettings(_File):
    model: str | None = None


class AssignmentSettings(_File):
    model: str | None = None
    assignment_points: float | None = Field(None, gt=0)


class StyleSettings(_File):
    theme: str | None = None
    accent: str | None = None                  # WCAG-checked against the theme in style.load_style
    density: Literal["comfortable", "compact"] | None = None
    recap_label: str | None = None
    glossary_label: str | None = None

    @field_validator("theme")
    @classmethod
    def _known_theme(cls, v):
        from coursekit.generate.page.style import available_themes
        themes = available_themes()
        if v is not None and v not in themes:
            guess = get_close_matches(v, themes, 1)
            raise ValueError(f"unknown theme{f' — did you mean {guess[0]!r}?' if guess else ''} "
                             f"(available: {', '.join(themes)})")
        return v


# --------------------------------------------------------------- page supplements (.vtconfig/pages/*.yaml)
class Reference(_File):
    label: str | None = None
    url: str


class Example(_File):
    label: str | None = None
    url: str | None = None
    iframe: str | None = None
    embed: bool = False
    width: int | None = Field(None, ge=1)
    height: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def _has_a_target(self):
        if not self.url and not self.iframe:
            raise ValueError("needs a `url` or a pasted `iframe` snippet")
        if self.iframe:
            from coursekit.generate.page.renderer import _parse_iframe
            if not _parse_iframe(self.iframe):
                raise ValueError("the `iframe` snippet has no readable src=\"…\"")
        return self


class Image(_File):
    url: str
    ref: str | None = None
    alt: str | None = None
    caption: str | None = None

    @model_validator(mode="after")
    def _accessible(self):
        if not self.ref and not (self.alt or self.caption):
            raise ValueError("an image without a `ref` needs `alt` text (or a `caption`) — it can't "
                             "ship without one")
        return self


class Supplements(_File):
    references: list[Reference] = []
    examples: list[Example] = []
    images: list[Image] = []


# --------------------------------------------------------------- the structure overlay
class Source(_File):
    path: str | None = None
    filename: str | None = None                # the transcriber's spelling of `path`
    title: str | None = None
    kind: str | None = None
    role: str | None = None

    @model_validator(mode="after")
    def _names_a_file(self):
        if not (self.path or self.filename):
            raise ValueError("a source needs a `path`")
        return self


class UnitEntry(_File):
    doc: str | None = None
    sources: list[Source] = []
    title: str | None = None
    module: str | None = None


class GradingGroup(_File):
    name: str = Field(min_length=1)
    weight: float = Field(0, ge=0)

    @field_validator("weight", mode="before")
    @classmethod
    def _percent(cls, v):
        if isinstance(v, str) and v.strip().endswith("%"):     # `20%` means 20 — unambiguous
            return v.strip()[:-1].strip()
        return v


class Grading(_File):
    groups: list[GradingGroup] = []
    placement: dict[Key, str] = {}

    @model_validator(mode="after")
    def _placements_name_declared_groups(self):
        names = [g.name for g in self.groups]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"group names must be unique (repeated: {', '.join(dupes)})")
        unknown = sorted({v for v in self.placement.values() if names and v not in names})
        if unknown:
            raise ValueError(f"placement names a group that isn't declared: {', '.join(unknown)} "
                             f"(groups: {', '.join(names)})")
        return self


class ExpectationRule(_File):
    scope: Literal["week", "module", "course"]
    artifact: str = Field(min_length=1)
    count: Count = 1


class ExpectationOverrides(_File):
    week: dict[Key, dict[Key, Count]] = {}
    module: dict[Key, dict[Key, Count]] = {}


class Expectations(_File):
    defaults: list[ExpectationRule] = []
    overrides: ExpectationOverrides = ExpectationOverrides()


class StructureOverlay(_File):
    weeks: dict[Key, UnitEntry | None] = {}
    grading: Grading | None = None
    expect: Expectations | None = None


# Which schema governs which `.vtconfig/` file.
SETTINGS: dict[str, type[_File]] = {
    "quiz.yaml": QuizSettings,
    "page.yaml": PageSettings,
    "evaluate.yaml": EvaluateSettings,
    "ingest.yaml": IngestSettings,
    "assignment.yaml": AssignmentSettings,
    "style.yaml": StyleSettings,
    "structure.coursekit.yaml": StructureOverlay,
}


def _field_names(model, seen=None) -> set[str]:
    seen = seen if seen is not None else set()
    if model in seen:
        return set()
    seen.add(model)
    names = set(model.model_fields)
    for f in model.model_fields.values():
        for arg in getattr(f.annotation, "__args__", ()) + (f.annotation,):
            if isinstance(arg, type) and issubclass(arg, BaseModel):
                names |= _field_names(arg, seen)
    return names


_KNOWN_KEYS = sorted(set().union(*(_field_names(m) for m in (*SETTINGS.values(), Supplements))))
_HOME = {k: name for name, m in SETTINGS.items() for k in m.model_fields}   # top-level key → its file


# --------------------------------------------------------------- reading
def read_yaml(path) -> dict:
    """A YAML mapping, or {} when the file doesn't exist. Present but unreadable — bad YAML, or not a
    mapping at the top — is an error naming the file and the line."""
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        problem = getattr(e, "problem", None) or str(e)
        raise CoursekitError(f"{path} is not valid YAML{where}: {problem}", code="config.unreadable",
                             details={"path": str(path), "line": mark.line + 1 if mark else None}) from e
    except (OSError, UnicodeDecodeError) as e:
        raise CoursekitError(f"{path} could not be read: {e}", code="config.unreadable",
                             details={"path": str(path)}) from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise CoursekitError(f"{path} should hold `key: value` settings, not a {type(data).__name__}",
                             code="config.unreadable", details={"path": str(path)})
    return data


def _loc(parts) -> str:
    out = ""
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out


def problems(err: ValidationError) -> list[str]:
    """Pydantic's errors as one line each: the key path, the problem, and the value given."""
    out = []
    for e in err.errors():
        loc = _loc(e["loc"])
        if e["type"] == "extra_forbidden":
            key = str(e["loc"][-1])
            if len(e["loc"]) == 1 and key in _HOME:                # right key, wrong file
                out.append(f"{loc}: belongs in {_HOME[key]}, not this file")
                continue
            guess = get_close_matches(key, _KNOWN_KEYS, 1)
            out.append(f"{loc}: unknown key{f' — did you mean {guess[0]!r}?' if guess else ''}")
            continue
        msg = e["msg"].removeprefix("Value error, ")
        given = e.get("input")
        shown = "" if e["type"] == "missing" or isinstance(given, (dict, list)) else f" (got {given!r})"
        out.append(f"{loc}: {msg}{shown}" if loc else f"{msg}{shown}")
    return out


def validate(path, data: dict, model: type[BaseModel]) -> BaseModel:
    try:
        return model.model_validate(data)
    except ValidationError as e:
        found = problems(e)
        raise CoursekitError(f"{path} has {len(found)} problem(s):\n" + "\n".join(f"  - {p}" for p in found),
                             code="config.invalid", details={"path": str(path), "problems": found},
                             hint="Run `coursekit check <course>` to see every settings file at once.") from e


def load(path, model: type[BaseModel]) -> dict:
    """Read and validate one settings file → its settings as a plain dict ({} when absent)."""
    data = read_yaml(path)
    if not data:
        return {}
    return validate(path, data, model).model_dump(exclude_none=True)


# --------------------------------------------------------------- checking a whole course
def check(root) -> tuple[list[Path], list[CoursekitError]]:
    """Validate every coursekit settings file under `<root>/.vtconfig/`. Returns (files checked,
    errors) — every file is checked, so one bad file doesn't hide the next."""
    from coursekit.generate.page.concept_map import ConceptMap

    vt = Path(root) / ".vtconfig"
    targets = [(vt / name, model) for name, model in SETTINGS.items() if (vt / name).is_file()]
    targets += [(p, Supplements) for p in sorted((vt / "pages").glob("*.y*ml"))]
    targets += [(p, ConceptMap) for p in sorted((vt / "concepts").glob("*.yaml"))]
    if (vt / "context.yaml").is_file():
        targets.append((vt / "context.yaml", None))            # the transcriber's: parse-check only
    errors = []
    for path, model in targets:
        try:
            data = read_yaml(path)
            if model is not None and data:
                validate(path, data, model)
        except CoursekitError as e:
            errors.append(e)
    return [p for p, _ in targets], errors
