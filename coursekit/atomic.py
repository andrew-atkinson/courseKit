"""Every file coursekit writes is written whole, or not at all (CORE-4.2).

`write(path, data)` writes a temporary file beside `path` and renames it into place (`os.replace`, atomic
within one filesystem), so a reader — or a crash, or a full disk — finds the old file or the new one, never
half of one, and no temporary file is left behind. `replacing(path)` does the same for a writer that needs
a path of its own (a zip). tests/test_atomic.py fails if code under coursekit/ writes a file any other way;
appending a line to a log (`open(path, "a")`) is the one exception, since an append can't be half-replaced.
"""

import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def replacing(path):
    """Yield a temporary path beside `path`; when the block finishes, it replaces `path`. If the block
    raises, `path` is untouched and the temporary file is removed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        yield tmp
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write(path, data: str | bytes) -> Path:
    """Replace `path` with `data` (text is written as UTF-8)."""
    with replacing(path) as tmp:
        if isinstance(data, bytes):
            tmp.write_bytes(data)
        else:
            tmp.write_text(data, encoding="utf-8")
    return Path(path)
