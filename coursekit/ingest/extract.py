"""Source document -> raw text. Deterministic, offline, no model.

Each supported type has a small extractor; heavier parsers (`pypdf`, `python-pptx`) are imported
lazily so a `.txt`/`.md` ingest needs neither installed. Extraction is deliberately shallow — it
pulls the text out and does light cosmetic cleanup; turning messy extraction into a teaching-ready
document is the optional shaping pass (`ingest.shape`), not this layer's job.
"""

import re
from pathlib import Path

_MULTISPACE = re.compile(r"[ \t]+")
_MANY_BLANKS = re.compile(r"\n{3,}")


def _clean(text: str) -> str:
    """Cosmetic only: trim trailing spaces per line, collapse runs of blank lines. Preserve the
    words — the shaping pass (or the generator) does the real structuring."""
    lines = [_MULTISPACE.sub(" ", ln).rstrip() for ln in (text or "").splitlines()]
    return _MANY_BLANKS.sub("\n\n", "\n".join(lines)).strip()


def _text(path: Path) -> str:
    return _clean(path.read_text(encoding="utf-8", errors="replace"))


def _pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return _clean("\n\n".join((page.extract_text() or "") for page in reader.pages))


def _pptx(path: Path) -> str:
    from pptx import Presentation
    blocks = []
    for slide in Presentation(str(path)).slides:
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                t = "\n".join(p.text for p in shape.text_frame.paragraphs).strip()
                if t:
                    texts.append(t)
        if texts:
            blocks.append("\n".join(texts))
    return _clean("\n\n".join(blocks))


# suffix -> extractor. The keys are also the "supported source" set.
_EXTRACTORS = {
    ".pdf": _pdf,
    ".pptx": _pptx,
    ".txt": _text,
    ".md": _text,
    ".markdown": _text,
}

SUPPORTED_SUFFIXES = frozenset(_EXTRACTORS)


def is_supported(path) -> bool:
    return Path(path).suffix.lower() in _EXTRACTORS


def extract_text(path) -> str:
    """The document's text, cleaned. Raises ValueError for an unsupported type."""
    path = Path(path)
    fn = _EXTRACTORS.get(path.suffix.lower())
    if fn is None:
        raise ValueError(
            f"unsupported source type '{path.suffix}' ({path.name}); "
            f"supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}")
    return fn(path)
