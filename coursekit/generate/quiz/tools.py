"""Tools the model calls.

A tool call is the only way a question enters the bank. Prose is scratch.

Schemas are hand-written dicts rather than pydantic's model_json_schema(): the
description strings are prompt engineering for a small local model and get tuned
constantly, and the generator emits $defs/$ref and anyOf[..., null] that local
grammar-constrained backends handle badly. Pydantic lives behind the function, in bank.py.

Tool results are prompt. Every ack is re-sent on every later turn, so keep them terse
and leave the full listing to get_bank_report.
"""

from pathlib import Path
from dotenv import load_dotenv
from coursekit import outcomes
from coursekit.generate import dispatch
from coursekit.generate.quiz import bank

load_dotenv(override=True)

# ------------------------------------------------------------- schemas

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

get_bank_report_json = {
    "name": "get_bank_report",
    "description": ("List every group and variant recorded so far, and whether the bank is ready "
                    "to finalize. Call this once when you think you are done."),
    "parameters": {"type": "object", "properties": {}, "required": [],
                   "additionalProperties": False},
}

finalize_bank_json = {
    "name": "finalize_bank",
    "description": ("Check the whole bank and write it out. Call this last. If it reports "
                    "problems, fix them with more add_ calls and then call it again."),
    "parameters": {"type": "object", "properties": {}, "required": [],
                   "additionalProperties": False},
}

add_open_response_variant_json = {
    "name": "add_open_response_variant",
    "description": ("Record ONE open-response (essay) question — an open-ended prompt the student "
                    "writes an answer to, graded by a human, not auto-scored. Use this ONLY for the "
                    "enduring-understanding transfer task when the brief asks for it. Calling this "
                    "again with the same group_id and variant_label REPLACES the previous version."),
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": _GROUP_ID,
            "variant_label": _LABEL,
            "question_text": {"type": "string",
                              "description": ("The open-ended prompt — a task asking the student to "
                                              "apply the idea to a NEW situation and explain their "
                                              "thinking")},
            "variant_summary": _SUMMARY,
            "rubric_criteria": {
                "type": "array",
                "items": {"type": "string"},
                "description": ("3-4 short criteria a grader looks for, e.g. ['applies the concept "
                                "correctly', 'justifies the choice']. Shown to the student as what "
                                "the response is assessed on."),
            },
            "text_format": _TEXT_FORMAT,
        },
        "required": ["group_id", "variant_label", "question_text", "variant_summary"],
        "additionalProperties": False,
    },
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
    "add_open_response_variant": add_open_response_variant_json,
    "get_bank_report": get_bank_report_json,
    "finalize_bank": finalize_bank_json,
}

# Neutral specs — {name, description, parameters}. The provider wraps them for the wire, so
# this stays vendor-agnostic. `tools` is the pre-wrapped OpenAI form, kept for anything still
# talking to the SDK directly.
TOOL_SPECS = list(_SCHEMAS.values())
tools = [{"type": "function", "function": spec} for spec in TOOL_SPECS]


# ------------------------------------------------------------- the tools

class QuizTools(dispatch.ToolSession):
    """The tools the model calls to build one bank, and that run's checklist."""

    SCHEMAS = _SCHEMAS
    TERMINAL = frozenset({"finalize_bank"})

    def __init__(self, draft: bank.BankDraft, call_log: Path | None = None):
        self.draft = draft
        self.checklist: list[str] = []
        self.completed: list[bool] = []
        super().__init__(call_log)

    def get_checklist_report(self) -> str:
        """The self.checklist as plain text — the same lines for the model and the console. (No rich markup:
        it is re-sent every turn and would teach the model to emit the markup the system prompt forbids.)"""
        return "\n".join(f"#{index + 1} [{'x' if done else ' '}] {item}"
                         for index, (item, done) in enumerate(zip(self.checklist, self.completed)))

    def create_checklist(self, descriptions: list[str]) -> str:
        self.checklist.extend(descriptions)
        self.completed.extend([False] * len(descriptions))
        report = self.get_checklist_report()
        outcomes.info("quiz.checklist", report)
        return report

    def mark_complete(self, index: int, completion_notes: str) -> str:
        if not 1 <= index <= len(self.checklist):
            return f"ERROR: no checklist item at #{index}. There are {len(self.checklist)}."
        self.completed[index - 1] = True
        outcomes.info("quiz.checklist_note", completion_notes)
        report = self.get_checklist_report()
        outcomes.info("quiz.checklist", report)
        return report

    def create_question_group(self, group_id: str, concept_title: str, question_type: str) -> str:
        return self.draft.create_group(group_id, concept_title, question_type)

    def add_multiple_choice_variant(self, group_id: str, variant_label: str, question_text: str,
                                    variant_summary: str, options: list[str], correct_index: int,
                                    text_format: str = "plain", feedback: str = "") -> str:
        v = bank.build_variant("multiple_choice", group_id=group_id, label=variant_label,
                               question_text=question_text, variant_summary=variant_summary, options=options,
                               correct_index=correct_index, text_format=text_format,
                               feedback=feedback or None)
        return self.draft.put_variant(v)

    def add_multiple_answer_variant(self, group_id: str, variant_label: str, question_text: str,
                                    variant_summary: str, options: list[str],
                                    correct_indices: list[int], text_format: str = "plain",
                                    feedback: str = "") -> str:
        v = bank.build_variant("multiple_answer", group_id=group_id, label=variant_label,
                               question_text=question_text, variant_summary=variant_summary,
                               options=options, correct_indices=correct_indices,
                               text_format=text_format, feedback=feedback or None)
        return self.draft.put_variant(v)

    def add_true_false_variant(self, group_id: str, variant_label: str, question_text: str,
                               variant_summary: str, correct_answer: bool,
                               text_format: str = "plain",
                               feedback_wrong: str = "", feedback_right: str = "") -> str:
        v = bank.build_variant("true_false", group_id=group_id, label=variant_label,
                               question_text=question_text, variant_summary=variant_summary,
                               correct_answer=correct_answer,
                               text_format=text_format, feedback_wrong=feedback_wrong or None,
                               feedback_right=feedback_right or None)
        return self.draft.put_variant(v)

    def add_short_answer_variant(self, group_id: str, variant_label: str, question_text: str,
                                 variant_summary: str, accepted_answers: list[str],
                                 text_format: str = "plain", feedback: str = "") -> str:
        v = bank.build_variant("short_answer", group_id=group_id, label=variant_label,
                               question_text=question_text, variant_summary=variant_summary,
                               accepted_answers=accepted_answers,
                               text_format=text_format, feedback=feedback or None)
        return self.draft.put_variant(v)

    def add_numerical_variant(self, group_id: str, variant_label: str, question_text: str,
                              variant_summary: str, answer: float, tolerance: float = 0.0,
                              text_format: str = "plain", feedback: str = "") -> str:
        v = bank.build_variant("numerical", group_id=group_id, label=variant_label,
                               question_text=question_text, variant_summary=variant_summary,
                               answer=answer, tolerance=tolerance,
                               text_format=text_format, feedback=feedback or None)
        return self.draft.put_variant(v)

    def add_matching_variant(self, group_id: str, variant_label: str, question_text: str,
                             variant_summary: str, pairs: list[dict],
                             text_format: str = "plain") -> str:
        v = bank.build_variant("matching", group_id=group_id, label=variant_label,
                               question_text=question_text, variant_summary=variant_summary,
                               pairs=pairs, text_format=text_format)
        return self.draft.put_variant(v)

    def get_bank_report(self) -> str:
        report = self.draft.report()
        outcomes.info("quiz.bank_report", report)
        return report

    def finalize_bank(self) -> str:
        result = self.draft.finalize()
        outcomes.info("quiz.finalize", result)
        return result

    def add_open_response_variant(self, group_id: str, variant_label: str, question_text: str,
                                  variant_summary: str, rubric_criteria: list[str] | None = None,
                                  text_format: str = "plain") -> str:
        v = bank.build_variant("open_response", group_id=group_id, label=variant_label,
                               question_text=question_text, variant_summary=variant_summary,
                               rubric_criteria=rubric_criteria or [], text_format=text_format)
        return self.draft.put_variant(v)
