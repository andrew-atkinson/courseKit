"""Tools the model calls.

A tool call is the only way a question enters the bank. Prose is scratch.

Schemas are hand-written dicts rather than pydantic's model_json_schema(): the
description strings are prompt engineering for a small local model and get tuned
constantly, and the generator emits $defs/$ref and anyOf[..., null] that local
grammar-constrained backends handle badly. Pydantic lives behind the function, in bank.py.

Tool results are prompt. Every ack is re-sent on every later turn, so keep them terse
and leave the full listing to get_bank_report.
"""

import json
import os
from pathlib import Path
from typing import Callable
from dotenv import load_dotenv
from rich.console import Console
from coursekit.generate.quiz import bank
from coursekit.generate.quiz.bank import ValidationError

load_dotenv(override=True)

checklist = []
completed = []

_call_log: Path | None = None


def show(text, markup: bool = True):
    """markup=False for anything containing our own bracketed text.

    The bank report says "[multiple_choice]" and GIFT says "[markdown]"; Rich reads both
    as style tags and silently eats them. soft_wrap stops long report lines being folded.
    """
    try:
        Console(soft_wrap=True).print(text, markup=markup)
    except Exception:
        print(text)


def set_call_log(path: Path | None) -> None:
    """Record raw tool calls so a bad model run becomes a replayable fixture."""
    global _call_log
    _call_log = Path(path) if path else None


def reset_state() -> None:
    """Clear per-run tool state between weeks, so one week's checklist and call-log path
    do not bleed into the next. Pair with bank.init(), which resets the bank itself."""
    checklist.clear()
    completed.clear()
    set_call_log(None)


# ------------------------------------------------------------- checklist

def get_checklist_report(markup: bool = False) -> str:
    """markup=False for the model, True for the console.

    The rich version must never be returned to the model: it is re-sent every turn and
    teaches it to emit the markup the system prompt forbids.
    """
    lines = []
    for index, item in enumerate(checklist):
        done = completed[index]
        if markup:
            lines.append(f"Checklist #{index + 1}: "
                         + (f"[green][strike]{item}[/strike][/green]" if done else item))
        else:
            lines.append(f"#{index + 1} [{'x' if done else ' '}] {item}")
    return "\n".join(lines)


def create_checklist(descriptions: list[str]) -> str:
    checklist.extend(descriptions)
    completed.extend([False] * len(descriptions))
    show(get_checklist_report(markup=True))
    return get_checklist_report()


create_checklist_json = {
    "name": "create_checklist",
    "description": "Add new checklist from a list of descriptions and return the full list",
    "parameters": {
        "type": "object",
        "properties": {
            "descriptions": {
                "type": "array",
                "items": {"type": "string"},
                "title": "Descriptions of checklist items",
            }
        },
        "required": ["descriptions"],
        "additionalProperties": False,
    },
}


def mark_complete(index: int, completion_notes: str) -> str:
    if not 1 <= index <= len(checklist):
        return f"ERROR: no checklist item at #{index}. There are {len(checklist)}."
    completed[index - 1] = True
    show(completion_notes, markup=False)
    show(get_checklist_report(markup=True))
    return get_checklist_report()


mark_complete_json = {
    "name": "mark_complete",
    "description": ("Mark complete the checklist item at the given position (starting from 1) "
                    "and return the full list"),
    "parameters": {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "title": "Index",
                "description": "The 1-based index of the checklist item to mark as complete",
            },
            "completion_notes": {
                "type": "string",
                "title": "Completion Notes",
                "description": "One short plain-text sentence about how you completed the item",
            },
        },
        "required": ["index", "completion_notes"],
        "additionalProperties": False,
    },
}

# ------------------------------------------------------------ bank tools

_GROUP_ID = {"type": "string",
             "description": "The group this variant belongs to, e.g. 'c1'"}
_LABEL = {"type": "string",
          "description": "Which variant of the group this is: a single capital letter, A to D"}
_SUMMARY = {
    "type": "string",
    "description": ("A few words naming what THIS variant tests, different from the other "
                    "variants in the group, e.g. 'Purpose of the condition' or 'What the "
                    "incrementer does'. Under 60 characters. Do not repeat the question text."),
}
_TEXT_FORMAT = {
    "type": "string",
    "enum": ["plain", "markdown", "html"],
    "description": ("Use 'markdown' when the question or any option contains code, and put the "
                    "code in backticks. Otherwise 'plain'."),
}


def create_question_group(group_id: str, concept_title: str, question_type: str) -> str:
    return bank.create_group(group_id, concept_title, question_type)


create_question_group_json = {
    "name": "create_question_group",
    "description": ("Declare one question concept before adding its variants. Every variant in "
                    "the group must be the question type declared here."),
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": {"type": "string",
                         "description": "Short id for the concept, e.g. 'c1'"},
            "concept_title": {"type": "string",
                              "description": "What this concept tests, in a few words"},
            "question_type": {
                "type": "string",
                "enum": ["multiple_choice", "multiple_answer", "true_false", "short_answer",
                         "numerical", "matching"],
                "description": "The question type every variant in this group will use",
            },
        },
        "required": ["group_id", "concept_title", "question_type"],
        "additionalProperties": False,
    },
}


def add_multiple_choice_variant(group_id: str, variant_label: str, question_text: str,
                                variant_summary: str, options: list[str], correct_index: int,
                                text_format: str = "plain", feedback: str = "") -> str:
    v = bank.build_variant("multiple_choice", group_id=group_id, label=variant_label,
                           question_text=question_text, variant_summary=variant_summary, options=options,
                           correct_index=correct_index, text_format=text_format,
                           feedback=feedback or None)
    return bank.put_variant(v)


add_multiple_choice_variant_json = {
    "name": "add_multiple_choice_variant",
    "description": ("Record ONE finished multiple-choice question. Calling this again with the "
                    "same group_id and variant_label REPLACES the previous version, so this is "
                    "also how you revise. Exactly one option is correct \u2014 if more than one "
                    "is, use add_multiple_answer_variant."),
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": _GROUP_ID,
            "variant_label": _LABEL,
            "question_text": {"type": "string", "description": "The question stem"},
            "variant_summary": _SUMMARY,
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": ("The answer options, usually 4. Each must be different from the "
                                "others in meaning. Do not number or letter them."),
            },
            "correct_index": {
                "type": "integer",
                "description": ("Which option is correct, counting from 0. Across a group's "
                                "variants this must differ each time; the reply tells you which "
                                "positions are still free."),
            },
            "text_format": _TEXT_FORMAT,
            "feedback": {"type": "string",
                         "description": "Optional note shown when the student answers correctly"},
        },
        "required": ["group_id", "variant_label", "question_text", "variant_summary",
                     "options", "correct_index"],
        "additionalProperties": False,
    },
}


def add_multiple_answer_variant(group_id: str, variant_label: str, question_text: str,
                                variant_summary: str, options: list[str],
                                correct_indices: list[int], text_format: str = "plain",
                                feedback: str = "") -> str:
    v = bank.build_variant("multiple_answer", group_id=group_id, label=variant_label,
                           question_text=question_text, variant_summary=variant_summary,
                           options=options, correct_indices=correct_indices,
                           text_format=text_format, feedback=feedback or None)
    return bank.put_variant(v)


add_multiple_answer_variant_json = {
    "name": "add_multiple_answer_variant",
    "description": ("Record ONE finished 'select all that apply' question, where MORE THAN ONE "
                    "option is correct and the student ticks every correct one. If exactly one "
                    "option is correct, use add_multiple_choice_variant instead. Calling this "
                    "again with the same group_id and variant_label REPLACES the previous "
                    "version. Marks are worked out for you; do not put percentages in the text."),
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": _GROUP_ID,
            "variant_label": _LABEL,
            "question_text": {
                "type": "string",
                "description": ("The question stem. Say that more than one answer is correct, "
                                "e.g. 'Select all that apply.'"),
            },
            "variant_summary": _SUMMARY,
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": ("The answer options, usually 4. Each must be different from the "
                                "others in meaning. Do not number or letter them."),
            },
            "correct_indices": {
                "type": "array",
                "items": {"type": "integer"},
                "description": ("Which options are correct, counting from 0, e.g. [0, 2]. At "
                                "least two, and at least one option must be left wrong."),
            },
            "text_format": _TEXT_FORMAT,
            "feedback": {"type": "string",
                         "description": "Optional note shown when the student answers correctly"},
        },
        "required": ["group_id", "variant_label", "question_text", "variant_summary",
                     "options", "correct_indices"],
        "additionalProperties": False,
    },
}


def add_true_false_variant(group_id: str, variant_label: str, question_text: str,
                           variant_summary: str, correct_answer: bool,
                           text_format: str = "plain",
                           feedback_wrong: str = "", feedback_right: str = "") -> str:
    v = bank.build_variant("true_false", group_id=group_id, label=variant_label,
                           question_text=question_text, variant_summary=variant_summary,
                           correct_answer=correct_answer,
                           text_format=text_format, feedback_wrong=feedback_wrong or None,
                           feedback_right=feedback_right or None)
    return bank.put_variant(v)


add_true_false_variant_json = {
    "name": "add_true_false_variant",
    "description": ("Record ONE finished true/false question. Calling this again with the same "
                    "group_id and variant_label REPLACES the previous version."),
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": _GROUP_ID,
            "variant_label": _LABEL,
            "question_text": {"type": "string",
                              "description": "The statement the student judges true or false"},
            "variant_summary": _SUMMARY,
            "correct_answer": {"type": "boolean",
                               "description": "true if the statement is true, false if not"},
            "text_format": _TEXT_FORMAT,
            "feedback_wrong": {"type": "string",
                               "description": "Optional note shown when the student is wrong"},
            "feedback_right": {"type": "string",
                               "description": "Optional note shown when the student is right"},
        },
        "required": ["group_id", "variant_label", "question_text", "variant_summary",
                     "correct_answer"],
        "additionalProperties": False,
    },
}


def add_short_answer_variant(group_id: str, variant_label: str, question_text: str,
                             variant_summary: str, accepted_answers: list[str],
                             text_format: str = "plain", feedback: str = "") -> str:
    v = bank.build_variant("short_answer", group_id=group_id, label=variant_label,
                           question_text=question_text, variant_summary=variant_summary,
                           accepted_answers=accepted_answers,
                           text_format=text_format, feedback=feedback or None)
    return bank.put_variant(v)


add_short_answer_variant_json = {
    "name": "add_short_answer_variant",
    "description": ("Record ONE finished short-answer question, where the student types the "
                    "answer. Calling this again with the same group_id and variant_label "
                    "REPLACES the previous version."),
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": _GROUP_ID,
            "variant_label": _LABEL,
            "question_text": {"type": "string", "description": "The question stem"},
            "variant_summary": _SUMMARY,
            "accepted_answers": {
                "type": "array",
                "items": {"type": "string"},
                "description": ("Every spelling you will accept as correct, e.g. ['four', '4']. "
                                "Matching ignores case. Cannot contain '->'."),
            },
            "text_format": _TEXT_FORMAT,
            "feedback": {"type": "string", "description": "Optional note shown to the student"},
        },
        "required": ["group_id", "variant_label", "question_text", "variant_summary",
                     "accepted_answers"],
        "additionalProperties": False,
    },
}


def add_numerical_variant(group_id: str, variant_label: str, question_text: str,
                          variant_summary: str, answer: float, tolerance: float = 0.0,
                          text_format: str = "plain", feedback: str = "") -> str:
    v = bank.build_variant("numerical", group_id=group_id, label=variant_label,
                           question_text=question_text, variant_summary=variant_summary,
                           answer=answer, tolerance=tolerance,
                           text_format=text_format, feedback=feedback or None)
    return bank.put_variant(v)


add_numerical_variant_json = {
    "name": "add_numerical_variant",
    "description": ("Record ONE finished numerical question, where the student types a number. "
                    "Calling this again with the same group_id and variant_label REPLACES the "
                    "previous version."),
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": _GROUP_ID,
            "variant_label": _LABEL,
            "question_text": {"type": "string", "description": "The question stem"},
            "variant_summary": _SUMMARY,
            "answer": {"type": "number", "description": "The correct number"},
            "tolerance": {"type": "number",
                          "description": ("How far off the student may be and still be right. "
                                          "Use 0 for an exact answer.")},
            "text_format": _TEXT_FORMAT,
            "feedback": {"type": "string", "description": "Optional note shown to the student"},
        },
        "required": ["group_id", "variant_label", "question_text", "variant_summary",
                     "answer"],
        "additionalProperties": False,
    },
}


def add_matching_variant(group_id: str, variant_label: str, question_text: str,
                         variant_summary: str, pairs: list[dict],
                         text_format: str = "plain") -> str:
    v = bank.build_variant("matching", group_id=group_id, label=variant_label,
                           question_text=question_text, variant_summary=variant_summary,
                           pairs=pairs, text_format=text_format)
    return bank.put_variant(v)


add_matching_variant_json = {
    "name": "add_matching_variant",
    "description": ("Record ONE finished matching question, where the student pairs each item on "
                    "the left with one on the right. Calling this again with the same group_id "
                    "and variant_label REPLACES the previous version. Matching questions cannot "
                    "have feedback."),
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": _GROUP_ID,
            "variant_label": _LABEL,
            "question_text": {"type": "string",
                              "description": "The instruction, e.g. 'Match each term to its use.'"},
            "variant_summary": _SUMMARY,
            "pairs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "left": {"type": "string",
                                 "description": "The prompt item. Cannot contain '->'."},
                        "right": {"type": "string", "description": "The item it matches"},
                    },
                    "required": ["left", "right"],
                    "additionalProperties": False,
                },
                "description": "At least 2 pairs; 3 or more is better. Each left must be unique.",
            },
            "text_format": _TEXT_FORMAT,
        },
        "required": ["group_id", "variant_label", "question_text", "variant_summary",
                     "pairs"],
        "additionalProperties": False,
    },
}


def get_bank_report() -> str:
    report = bank.report()
    show(report, markup=False)
    return report


get_bank_report_json = {
    "name": "get_bank_report",
    "description": ("List every group and variant recorded so far, and whether the bank is ready "
                    "to finalize. Call this once when you think you are done."),
    "parameters": {"type": "object", "properties": {}, "required": [],
                   "additionalProperties": False},
}


def finalize_bank() -> str:
    result = bank.finalize()
    show(result, markup=False)
    return result


finalize_bank_json = {
    "name": "finalize_bank",
    "description": ("Check the whole bank and write it out. Call this last. If it reports "
                    "problems, fix them with more add_ calls and then call it again."),
    "parameters": {"type": "object", "properties": {}, "required": [],
                   "additionalProperties": False},
}


# ------------------------------------------------------------- dispatch

TOOL_REGISTRY: dict[str, Callable[..., str]] = {
    "create_checklist": create_checklist,
    "mark_complete": mark_complete,
    "create_question_group": create_question_group,
    "add_multiple_choice_variant": add_multiple_choice_variant,
    "add_multiple_answer_variant": add_multiple_answer_variant,
    "add_true_false_variant": add_true_false_variant,
    "add_short_answer_variant": add_short_answer_variant,
    "add_numerical_variant": add_numerical_variant,
    "add_matching_variant": add_matching_variant,
    "get_bank_report": get_bank_report,
    "finalize_bank": finalize_bank,
}

_SCHEMAS = {
    "create_checklist": create_checklist_json,
    "mark_complete": mark_complete_json,
    "create_question_group": create_question_group_json,
    "add_multiple_choice_variant": add_multiple_choice_variant_json,
    "add_multiple_answer_variant": add_multiple_answer_variant_json,
    "add_true_false_variant": add_true_false_variant_json,
    "add_short_answer_variant": add_short_answer_variant_json,
    "add_numerical_variant": add_numerical_variant_json,
    "add_matching_variant": add_matching_variant_json,
    "get_bank_report": get_bank_report_json,
    "finalize_bank": finalize_bank_json,
}

# Neutral specs — {name, description, parameters}. The provider wraps them for the wire, so
# this stays vendor-agnostic. `tools` is the pre-wrapped OpenAI form, kept for anything still
# talking to the SDK directly.
TOOL_SPECS = [_SCHEMAS[name] for name in TOOL_REGISTRY]
tools = [{"type": "function", "function": spec} for spec in TOOL_SPECS]


def _fmt_errors(e: ValidationError) -> str:
    """Pydantic's own text is jargon ('Input should be a valid integer [type=int_type...]').
    A small model needs the field and the problem, nothing else."""
    out = []
    for err in e.errors()[:4]:
        loc = ".".join(str(p) for p in err["loc"] if p != "value_error")
        msg = err["msg"].removeprefix("Value error, ")
        out.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(out)


def _dispatch_one(name: str, raw_args: str | None) -> str:
    """Never raise. A malformed call at iteration 17 must not lose the first 16 variants."""
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return f"ERROR: no tool named '{name}'. Available: {', '.join(TOOL_REGISTRY)}"
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
        return f"ERROR: {_fmt_errors(e)}"
    except TypeError as e:
        return f"ERROR: wrong arguments for '{name}': {e}"
    except Exception as e:
        return f"ERROR: {name} failed: {type(e).__name__}: {e}"


def run_tool_calls(tool_calls) -> list[tuple[str, str]]:
    """Dispatch neutral ToolCalls -> [(tool_call_id, content)].

    Returns pairs rather than provider-shaped messages: how a tool result is represented in a
    conversation is the provider's business (OpenAI keys it by tool_call_id, Anthropic uses
    tool_result blocks), while what the tool *did* is ours.

    Content is a plain string, never json.dumps'd — wrapping an ack in quotes and escaping it
    costs tokens on every subsequent turn and reads worse to a small model.
    """
    results = []
    finalized = False
    for tc in tool_calls:
        # Stop at the first successful finalize: the driver only checks after a whole turn's batch,
        # but a model can emit its whole build (and then rebuild) in one turn. Anything after the
        # finalize is a runaway; ignore it so the artifact is the one the model first committed to.
        if finalized:
            results.append((tc.id, "(ignored: the artifact is already finalized)"))
            continue
        if _call_log is not None:
            _call_log.parent.mkdir(parents=True, exist_ok=True)
            with open(_call_log, "a", encoding="utf-8") as f:
                f.write(json.dumps({"name": tc.name, "arguments": tc.arguments}) + "\n")
        content = _dispatch_one(tc.name, tc.arguments)
        results.append((tc.id, content))
        if tc.name == "finalize_bank" and not content.startswith("ERROR"):
            finalized = True
    return results


def replay(path) -> list[str]:
    """Feed a recorded calls.jsonl back through dispatch with no model attached."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            out.append(_dispatch_one(rec["name"], rec["arguments"]))
    return out
