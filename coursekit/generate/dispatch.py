"""Shared tool-call dispatch for generators.

The machinery is identical across generators: never raise (a malformed call at iteration 17 must
not lose the first 16 commits), turn a pydantic ValidationError into a short actionable message for
a small model, and log raw calls so a bad run becomes a replayable fixture. A generator supplies its
own `{name: callable}` registry; everything else is common.

(The quiz generator predates this module and still carries its own copy; it can adopt this later.)
"""

import json
from pathlib import Path
from typing import Callable

from pydantic import ValidationError


def fmt_errors(e: ValidationError) -> str:
    """Pydantic's own text is jargon; a small model needs the field and the problem, nothing else."""
    out = []
    for err in e.errors()[:4]:
        loc = ".".join(str(p) for p in err["loc"] if p != "value_error")
        msg = err["msg"].removeprefix("Value error, ")
        out.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(out)


def dispatch_one(registry: dict[str, Callable[..., str]], name: str, raw_args: str | None) -> str:
    """Run one tool call. Never raises — returns an actionable ERROR string instead."""
    fn = registry.get(name)
    if fn is None:
        return f"ERROR: no tool named '{name}'. Available: {', '.join(registry)}"
    try:
        # Zero-argument tools commonly arrive as "" rather than "{}".
        args = json.loads(raw_args) if (raw_args or "").strip() else {}
    except json.JSONDecodeError as e:
        return f"ERROR: arguments for '{name}' were not valid JSON ({e}). Send the call again."
    if not isinstance(args, dict):
        return f"ERROR: arguments for '{name}' must be a JSON object, got {type(args).__name__}."
    try:
        return fn(**args)
    except ValidationError as e:
        return f"ERROR: {fmt_errors(e)}"
    except TypeError as e:
        return f"ERROR: wrong arguments for '{name}': {e}"
    except Exception as e:
        return f"ERROR: {name} failed: {type(e).__name__}: {e}"


def run_tool_calls(registry, tool_calls, call_log: Path | None = None,
                   *, terminal_tools=frozenset()) -> list[tuple[str, str]]:
    """Dispatch neutral ToolCalls -> [(tool_call_id, content)], logging raw calls if a path is set.

    Pairs, not provider-shaped messages: how a result sits in a conversation is the provider's
    business; what the tool did is ours. Content is a plain string, never json.dumps'd.

    Stops at the first SUCCESSFUL `terminal_tools` call (e.g. finalize_page). The driver only checks
    "is it finalized?" after a whole turn's batch, but a model can emit the whole build in one turn —
    one gemma run under `--detail full` emitted 138 calls at once, finalizing 8× and rebuilding the page
    into an orphaned mess. A well-behaved model finalizes last, so everything after the first finalize is
    a runaway rebuild: ignore it, and the finished artifact is the one the model first committed to.
    """
    results = []
    finalized = False
    for tc in tool_calls:
        if finalized:
            results.append((tc.id, "(ignored: the artifact is already finalized)"))
            continue
        if call_log is not None:
            call_log.parent.mkdir(parents=True, exist_ok=True)
            with open(call_log, "a", encoding="utf-8") as f:
                f.write(json.dumps({"name": tc.name, "arguments": tc.arguments}) + "\n")
        content = dispatch_one(registry, tc.name, tc.arguments)
        results.append((tc.id, content))
        if tc.name in terminal_tools and not content.startswith("ERROR"):
            finalized = True
    return results


def replay(registry, path) -> list[str]:
    """Feed a recorded calls.jsonl back through dispatch with no model attached."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            out.append(dispatch_one(registry, rec["name"], rec["arguments"]))
    return out
