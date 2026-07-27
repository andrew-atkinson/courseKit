"""CLI shim. The CLI itself lives in `coursekit/cli.py`, also exposed as the `coursekit` command
(an editable install: `uv sync`). `python app.py <command> …` remains equivalent.

    python app.py ingest   PATH [--raw]
    python app.py generate PATH [--quizzes | --pages] [--week N ...] [--detail LEVEL] …
    python app.py emit qti  PATH [--bundle]
    python app.py emit html PATH
    python app.py emit cc   PATH
"""

import sys

from coursekit.cli import main

if __name__ == "__main__":
    sys.exit(main())
