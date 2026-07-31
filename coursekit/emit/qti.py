"""Canvas Classic-Quiz QTI 1.2 serialisation.

bank.json -> a Canvas .imscc package: one item bank per concept, plus a quiz that draws one
variant per concept. See docs/canvasQuizStructure.md — every structure is from a real export.

Like gift.py: pure string templates with a rigorous escaper, verified by parsing the output
back. String templates (not ElementTree) because we need byte-exact namespaces and two different
schemaLocations, which ElementTree's namespace handling fights.
"""

import hashlib
import html
import re
import textwrap
import zipfile
from pathlib import Path

QTI_NS = ('xmlns="http://www.imsglobal.org/xsd/ims_qtiasiv1p2" '
          'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"')
QTI_SCHEMA = ("http://www.imsglobal.org/xsd/ims_qtiasiv1p2 "
              "http://www.imsglobal.org/xsd/ims_qtiasiv1p2p1.xsd")
# Canvas meta (assessment_meta.xml). Matches a real "QTI Quiz Export": xmlns:xsi is the
# XMLSchema-instance URL, with a separate xsi:schemaLocation.
META_NS = ('xmlns="http://canvas.instructure.com/xsd/cccv1p0" '
           'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
           'xsi:schemaLocation="http://canvas.instructure.com/xsd/cccv1p0 '
           'https://canvas.instructure.com/xsd/cccv1p0.xsd"')
# Manifest for a QTI Quiz Export (Quiz -> Export), which imports inline questions. This is
# NOT the full-course Common-Cartridge flavour, whose empty assessment stub imports empty.
MANIFEST_NS = (
    'xmlns="http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1" '
    'xmlns:lom="http://ltsc.ieee.org/xsd/imsccv1p1/LOM/resource" '
    'xmlns:imsmd="http://www.imsglobal.org/xsd/imsmd_v1p2" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:schemaLocation="http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1 '
    'http://www.imsglobal.org/xsd/imscp_v1p1.xsd '
    'http://ltsc.ieee.org/xsd/imsccv1p1/LOM/resource '
    'http://www.imsglobal.org/profile/cc/ccv1p1/LOM/ccv1p1_lomresource_v1p0.xsd '
    'http://www.imsglobal.org/xsd/imsmd_v1p2 '
    'http://www.imsglobal.org/xsd/imsmd_v1p2p2.xsd"')

_BACKTICK = re.compile(r"`([^`]*)`")
_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)   # ```lang\n …code… ``` (multi-line)
# $…$ that looks like math (contains \, _ or ^) — Canvas renders MathJax in \(…\) but NOT bare $…$,
# so `$A_m$` would ship as literal source. A prose dollar ($5) has none of those and is left alone.
_QUIZ_MATH = re.compile(r"\$([^$\n]*[\\_^][^$\n]*)\$")


def _mathjax(escaped: str) -> str:
    """Rewrite math-looking $…$ to the \\(…\\) delimiters Canvas's MathJax actually renders."""
    return _QUIZ_MATH.sub(r"\\(\1\\)", escaped)


def _fix_escapes(text: str) -> str:
    """Repair a model that wrote LITERAL `\\n`/`\\t` (backslash-n) instead of real newlines — the
    tell is literal escapes with no real newline anywhere, which left a ```` ``` ```` fence unmatched
    and the code mangled. Only fire on that signature, so real text (and `\\n` inside a code string)
    is untouched."""
    if "\\n" in text and "\n" not in text:
        text = text.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "")
    return text


# ----------------------------------------------------------------- escaping

def _md_segment(text: str) -> str:
    """A non-fenced markdown run: inline `code` → <code>, math $…$ → \\(…\\), and newlines → <br/> so
    a multi-line stem doesn't collapse to one line (HTML folds whitespace)."""
    parts, pos = [], 0
    for m in _BACKTICK.finditer(text):
        parts.append(_mathjax(html.escape(text[pos:m.start()], quote=False)).replace("\n", "<br/>"))
        parts.append(f"<code>{html.escape(m.group(1), quote=False)}</code>")
        pos = m.end()
    parts.append(_mathjax(html.escape(text[pos:], quote=False)).replace("\n", "<br/>"))
    return "".join(parts)


_LINE_COMMENT = re.compile(r"//.*$")
_STR_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`')


def _reindent(code: str, unit: str = "  ") -> str:
    """Re-indent brace-delimited code by nesting depth, discarding whatever indentation the model
    wrote — every line sits at `unit * depth`, so a block is consistent even when the model indented
    it inconsistently line-to-line. Only `{}` drive depth (parens/brackets balance within a line in
    practice), and braces inside line comments or string literals are ignored."""
    out, depth = [], 0
    for raw in code.split("\n"):
        s = raw.strip()
        if not s:
            out.append("")
            continue
        scan = _STR_LITERAL.sub("", _LINE_COMMENT.sub("", s))
        here = depth - 1 if s[0] == "}" else depth      # a line that starts by closing dedents first
        out.append(unit * max(0, here) + s)
        depth = max(0, depth + scan.count("{") - scan.count("}"))
    return "\n".join(out)


def _clean_code(code: str) -> str:
    """Tidy a fenced block's indentation before it goes in a <pre>. Models mis-indent the code they
    write — line 1 flush, the rest shoved right, and often inconsistently line-to-line (a sibling
    statement deeper than its neighbour), which a uniform dedent cannot repair.

    For brace-delimited code we re-indent from scratch by nesting depth (`_reindent`), which is robust
    to that inconsistency. For brace-less snippets we fall back to stripping a spurious common base
    off the lines after a flush first line. `textwrap.dedent` runs first for the simple uniform case.
    """
    code = textwrap.dedent(code.strip("\n"))
    if "{" in code and "}" in code:
        return _reindent(code)
    lines = code.split("\n")
    if len(lines) > 1 and lines[0][:1] not in (" ", "\t"):
        tail = [ln for ln in lines[1:] if ln.strip()]
        base = min((len(ln) - len(ln.lstrip()) for ln in tail), default=0)
        if base:
            lines = [lines[0]] + [ln[base:] if ln.strip() else ln for ln in lines[1:]]
            code = "\n".join(lines)
    return code


def _to_html(text: str, text_format: str) -> str:
    """The HTML body (level 1): real <div>/<code>/<pre> tags, content HTML-escaped so code renders.

    A fenced ```` ``` ```` block becomes a <pre> so its line breaks and indentation survive — this is
    what a code-completion question needs; without it the code collapsed to one unreadable line.
    """
    if text_format == "markdown":
        text = _fix_escapes(text)   # real newlines back, so a mis-escaped fence renders
        out, pos = [], 0
        for m in _FENCE.finditer(text):
            out.append(_md_segment(text[pos:m.start()]))
            out.append(f"<pre>{html.escape(_clean_code(m.group(1)), quote=False)}</pre>")
            pos = m.end()
        out.append(_md_segment(text[pos:]))
        body = "".join(out)
    elif text_format == "html":
        body = text  # already HTML; trust it
    else:
        body = _mathjax(html.escape(text, quote=False))   # plain: still rescue $…$ math
    return f"<div>{body}</div>"


def _xml(s: str) -> str:
    """XML-escape (level 2). '&' first, or we'd double-escape the entities we just wrote."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def mattext(text: str, text_format: str = "plain") -> str:
    """The escaped body for <mattext texttype='text/html'>: HTML, then XML-escaped to embed.

    Two levels: `x < 10` -> HTML `x &lt; 10` -> XML `x &amp;lt; 10`. This is why the export shows
    `&amp;nbsp;` — an HTML `&nbsp;` XML-escaped once.
    """
    return _xml(_to_html(text, text_format))


def attr(s: str) -> str:
    """Escape for an XML attribute value."""
    return _xml(s).replace('"', "&quot;")


# ------------------------------------------- identifiers (deterministic)

def _h(*parts) -> str:
    """32 hex chars, stable for the same inputs — so re-emitting a bank re-uses ids and a
    re-import updates rather than duplicating."""
    return hashlib.md5(":".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def qid(*parts) -> str:
    return "g" + _h(*parts)


def iid(*parts) -> str:
    return "i" + _h(*parts)


def item_id(*parts) -> str:
    return _h(*parts)


def label_id(*parts) -> str:
    h = _h(*parts)
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def bank_ident(run_id: str, group_id: str) -> str:
    """The objectbank id for a concept — the join between a bank and the quiz's sourcebank_ref."""
    return qid(run_id, "bank", group_id)


# ------------------------------------------------------------- indentation

def _indent(block: str, levels: int) -> str:
    pad = "  " * levels
    return "\n".join((pad + ln) if ln else ln for ln in block.split("\n"))


# ------------------------------------------------------------------- items

def _mc_item(v, run_id: str) -> str:
    ident = item_id(run_id, v.group_id, v.label)
    labels = [label_id(run_id, v.group_id, v.label, i) for i in range(len(v.options))]
    aqref = item_id(run_id, v.group_id, v.label, "aq")
    correct = labels[v.correct_index]

    def _choice(lab, opt):
        return (f'<response_label ident="{lab}">\n'
                f'  <material>\n'
                f'    <mattext texttype="text/html">{mattext(opt, v.text_format)}</mattext>\n'
                f'  </material>\n'
                f'</response_label>')

    choices = "\n".join(_choice(lab, opt) for lab, opt in zip(labels, v.options))

    return f'''<item ident="{ident}" title="{attr(v.variant_summary)}">
  <itemmetadata>
    <qtimetadata>
      <qtimetadatafield>
        <fieldlabel>question_type</fieldlabel>
        <fieldentry>multiple_choice_question</fieldentry>
      </qtimetadatafield>
      <qtimetadatafield>
        <fieldlabel>points_possible</fieldlabel>
        <fieldentry/>
      </qtimetadatafield>
      <qtimetadatafield>
        <fieldlabel>original_answer_ids</fieldlabel>
        <fieldentry>{",".join(labels)}</fieldentry>
      </qtimetadatafield>
      <qtimetadatafield>
        <fieldlabel>assessment_question_identifierref</fieldlabel>
        <fieldentry>{aqref}</fieldentry>
      </qtimetadatafield>
    </qtimetadata>
  </itemmetadata>
  <presentation>
    <material>
      <mattext texttype="text/html">{mattext(v.question_text, v.text_format)}</mattext>
    </material>
    <response_lid ident="response1" rcardinality="Single">
      <render_choice>
{_indent(choices, 4)}
      </render_choice>
    </response_lid>
  </presentation>
  <resprocessing>
    <outcomes>
      <decvar maxvalue="100" minvalue="0" varname="SCORE" vartype="Decimal"/>
    </outcomes>
    <respcondition continue="No">
      <conditionvar>
        <varequal respident="response1">{correct}</varequal>
      </conditionvar>
      <setvar action="Set" varname="SCORE">100</setvar>
    </respcondition>
  </resprocessing>
</item>'''


def _num_id(*parts) -> str:
    """A decimal id, matching the numeric ids Canvas uses for classic-quiz answers."""
    return str(int(_h(*parts)[:12], 16))


def _itemmeta(qtype: str, answer_ids: list[str], run_id: str, v) -> str:
    """Shared <itemmetadata>. points_possible is empty in bank items — the quiz sets points."""
    aqref = item_id(run_id, v.group_id, v.label, "aq")
    ids = ",".join(answer_ids)
    return f'''  <itemmetadata>
    <qtimetadata>
      <qtimetadatafield>
        <fieldlabel>question_type</fieldlabel>
        <fieldentry>{qtype}</fieldentry>
      </qtimetadatafield>
      <qtimetadatafield>
        <fieldlabel>points_possible</fieldlabel>
        <fieldentry/>
      </qtimetadatafield>
      <qtimetadatafield>
        <fieldlabel>original_answer_ids</fieldlabel>
        <fieldentry>{ids}</fieldentry>
      </qtimetadatafield>
      <qtimetadatafield>
        <fieldlabel>assessment_question_identifierref</fieldlabel>
        <fieldentry>{aqref}</fieldentry>
      </qtimetadatafield>
    </qtimetadata>
  </itemmetadata>'''


def _stem(v) -> str:
    return (f'    <material>\n'
            f'      <mattext texttype="text/html">{mattext(v.question_text, v.text_format)}'
            f'</mattext>\n    </material>')


def _tf_item(v, run_id):
    """INFERRED (no export ground truth): Canvas true_false_question is a 2-option MC."""
    opts = [("True", True), ("False", False)]
    labels = [_num_id(run_id, v.group_id, v.label, txt) for txt, _ in opts]
    correct = labels[0] if v.correct_answer else labels[1]
    choices = "\n".join(
        f'''<response_label ident="{lab}">
  <material>
    <mattext texttype="text/plain">{txt}</mattext>
  </material>
</response_label>'''
        for lab, (txt, _) in zip(labels, opts))
    return f'''<item ident="{item_id(run_id, v.group_id, v.label)}" title="{attr(v.variant_summary)}">
{_itemmeta("true_false_question", labels, run_id, v)}
  <presentation>
{_stem(v)}
    <response_lid ident="response1" rcardinality="Single">
      <render_choice>
{_indent(choices, 4)}
      </render_choice>
    </response_lid>
  </presentation>
  <resprocessing>
    <outcomes>
      <decvar maxvalue="100" minvalue="0" varname="SCORE" vartype="Decimal"/>
    </outcomes>
    <respcondition continue="No">
      <conditionvar>
        <varequal respident="response1">{correct}</varequal>
      </conditionvar>
      <setvar action="Set" varname="SCORE">100</setvar>
    </respcondition>
  </resprocessing>
</item>'''


def _sa_item(v, run_id):
    """short_answer_question: render_fib; every accepted answer is a varequal (OR)."""
    ans_ids = [_num_id(run_id, v.group_id, v.label, "a", i)
               for i in range(len(v.accepted_answers))]
    varequals = "\n".join(
        f'        <varequal respident="response1">{_xml(a)}</varequal>'
        for a in v.accepted_answers)
    return f'''<item ident="{item_id(run_id, v.group_id, v.label)}" title="{attr(v.variant_summary)}">
{_itemmeta("short_answer_question", ans_ids, run_id, v)}
  <presentation>
{_stem(v)}
    <response_str ident="response1" rcardinality="Single">
      <render_fib>
        <response_label ident="answer1" rshuffle="No"/>
      </render_fib>
    </response_str>
  </presentation>
  <resprocessing>
    <outcomes>
      <decvar maxvalue="100" minvalue="0" varname="SCORE" vartype="Decimal"/>
    </outcomes>
    <respcondition continue="No">
      <conditionvar>
{varequals}
      </conditionvar>
      <setvar action="Set" varname="SCORE">100</setvar>
    </respcondition>
  </resprocessing>
</item>'''


def _ma_item(v, run_id):
    """multiple_answers_question: rcardinality Multiple; all-or-nothing (<and> + <not>)."""
    labels = [_num_id(run_id, v.group_id, v.label, i) for i in range(len(v.options))]
    correct = set(v.correct_indices)
    choices = "\n".join(
        f'''<response_label ident="{lab}">
  <material>
    <mattext texttype="text/html">{mattext(opt, v.text_format)}</mattext>
  </material>
</response_label>'''
        for lab, opt in zip(labels, v.options))
    conds = []
    for i, lab in enumerate(labels):
        vq = f'<varequal respident="response1">{lab}</varequal>'
        conds.append(vq if i in correct else f'<not>\n  {vq}\n</not>')
    and_block = "\n".join(_indent(c, 4) for c in conds)
    return f'''<item ident="{item_id(run_id, v.group_id, v.label)}" title="{attr(v.variant_summary)}">
{_itemmeta("multiple_answers_question", labels, run_id, v)}
  <presentation>
{_stem(v)}
    <response_lid ident="response1" rcardinality="Multiple">
      <render_choice>
{_indent(choices, 4)}
      </render_choice>
    </response_lid>
  </presentation>
  <resprocessing>
    <outcomes>
      <decvar maxvalue="100" minvalue="0" varname="SCORE" vartype="Decimal"/>
    </outcomes>
    <respcondition continue="No">
      <conditionvar>
        <and>
{and_block}
        </and>
      </conditionvar>
      <setvar action="Set" varname="SCORE">100</setvar>
    </respcondition>
  </resprocessing>
</item>'''


def _match_item(v, run_id):
    """matching_question: one response_lid per left, a shared right-option list, Add per match."""
    left_ids = [_num_id(run_id, v.group_id, v.label, "L", i) for i in range(len(v.pairs))]
    # Right options are shared across every left; a given right text always gets the same id.
    right_id = {}
    for p in v.pairs:
        right_id.setdefault(p.right, _num_id(run_id, v.group_id, v.label, "R", p.right))
    right_choices = "\n".join(
        f'''<response_label ident="{rid}">
  <material>
    <mattext texttype="text/plain">{_xml(text)}</mattext>
  </material>
</response_label>'''
        for text, rid in right_id.items())

    blanks = []
    for lid, p in zip(left_ids, v.pairs):
        blanks.append(f'''<response_lid ident="response_{lid}">
  <material>
    <mattext texttype="text/plain">{_xml(p.left)}</mattext>
  </material>
  <render_choice>
{_indent(right_choices, 2)}
  </render_choice>
</response_lid>''')
    presentation = "\n".join(_indent(b, 2) for b in blanks)

    score = round(100 / len(v.pairs), 2)
    conds = "\n".join(
        f'''    <respcondition>
      <conditionvar>
        <varequal respident="response_{lid}">{right_id[p.right]}</varequal>
      </conditionvar>
      <setvar action="Add" varname="SCORE">{score}</setvar>
    </respcondition>'''
        for lid, p in zip(left_ids, v.pairs))

    return f'''<item ident="{item_id(run_id, v.group_id, v.label)}" title="{attr(v.variant_summary)}">
{_itemmeta("matching_question", left_ids, run_id, v)}
  <presentation>
{_stem(v)}
{presentation}
  </presentation>
  <resprocessing>
    <outcomes>
      <decvar maxvalue="100" minvalue="0" varname="SCORE" vartype="Decimal"/>
    </outcomes>
{conds}
  </resprocessing>
</item>'''


def _dec(x) -> str:
    """Canvas writes numeric answers as decimals ('4.0', '2.7175'). Round first so float
    arithmetic on the margin doesn't leak 2.7174999999999998 into the XML."""
    s = f"{round(float(x), 10):.10f}".rstrip("0")
    return s + "0" if s.endswith(".") else s


def _num_item(v, run_id):
    """numerical_question: render_fib fibtype='Decimal', answer matched exactly or within a
    margin. Canvas uses <vargt> for the lower bound when there IS a margin, but <vargte> when
    the margin is zero (otherwise an exact answer would fall outside its own bounds)."""
    ans_id = _num_id(run_id, v.group_id, v.label, "a0")
    lo_tag = "vargt" if v.tolerance > 0 else "vargte"
    return f'''<item ident="{item_id(run_id, v.group_id, v.label)}" title="{attr(v.variant_summary)}">
{_itemmeta("numerical_question", [ans_id], run_id, v)}
  <presentation>
{_stem(v)}
    <response_str ident="response1" rcardinality="Single">
      <render_fib fibtype="Decimal">
        <response_label ident="answer1"/>
      </render_fib>
    </response_str>
  </presentation>
  <resprocessing>
    <outcomes>
      <decvar maxvalue="100" minvalue="0" varname="SCORE" vartype="Decimal"/>
    </outcomes>
    <respcondition continue="No">
      <conditionvar>
        <or>
          <varequal respident="response1">{_dec(v.answer)}</varequal>
          <and>
            <{lo_tag} respident="response1">{_dec(v.answer - v.tolerance)}</{lo_tag}>
            <varlte respident="response1">{_dec(v.answer + v.tolerance)}</varlte>
          </and>
        </or>
      </conditionvar>
      <setvar action="Set" varname="SCORE">100</setvar>
    </respcondition>
  </resprocessing>
</item>'''


_ITEM_EMITTERS = {
    "multiple_choice": _mc_item,
    "true_false": _tf_item,
    "short_answer": _sa_item,
    "multiple_answer": _ma_item,
    "matching": _match_item,
    "numerical": _num_item,
}


def emit_item(v, run_id: str) -> str:
    emitter = _ITEM_EMITTERS.get(v.kind)
    if emitter is None:
        raise NotImplementedError(
            f"QTI emit for '{v.kind}' awaits the Canvas sample export (see Phase B in the plan)"
        )
    return emitter(v, run_id)


# ---------------------------------------------------------------- objectbank

def emit_objectbank(group, run_id: str) -> str:
    """One Canvas item bank holding a concept's variants."""
    items = "\n".join(_indent(emit_item(group.variants[lbl], run_id), 2)
                      for lbl in sorted(group.variants))
    return f'''<?xml version="1.0"?>
<questestinterop {QTI_NS} xsi:schemaLocation="{QTI_SCHEMA}">
  <objectbank ident="{bank_ident(run_id, group.group_id)}" canvas_item_bank="true">
    <qtimetadata>
      <qtimetadatafield>
        <fieldlabel>bank_title</fieldlabel>
        <fieldentry>{_xml(group.concept_title)}</fieldentry>
      </qtimetadatafield>
      <qtimetadatafield>
        <fieldlabel>bank_type</fieldlabel>
        <fieldentry>Course</fieldentry>
      </qtimetadatafield>
    </qtimetadata>
{items}
  </objectbank>
</questestinterop>
'''


# ---------------------------------------------------- ids & helpers for a quiz

def quiz_ident(run_id: str) -> str:
    return qid(run_id, "quiz")


def _quiz_groups(quiz: dict) -> list[dict]:
    """The [{group_id, pick_count, points}] the assessment draws from."""
    return quiz.get("groups", [])


def _points_possible(quiz: dict) -> float:
    return sum(g.get("pick_count", 1) * g.get("points", 1) for g in _quiz_groups(quiz))


# ------------------------------------------------- the assessment (the draw)

def emit_assessment(bank, quiz: dict) -> str:
    """The assessment: root_section with one question group per concept.

    Each group is a <section> holding the concept's variant <item>s INLINE, with a
    <selection_ordering> that picks selection_number of them. Inline (not a sourcebank_ref
    to a separate objectbank) because separate item-bank files do not re-import as banks —
    Canvas dropped them into course Files and the quiz came up empty. This is Canvas's
    'question group with questions defined in the group' model.
    """
    run_id = bank.run_id
    sections = []
    for g in _quiz_groups(quiz):
        gid = g["group_id"]
        group = bank.groups[gid]
        items = "\n".join(_indent(emit_item(group.variants[lbl], run_id), 1)
                          for lbl in sorted(group.variants))
        sections.append(
            f'''<section ident="{qid(run_id, "section", gid)}" title="{attr(group.concept_title)}">
  <selection_ordering>
    <selection>
      <selection_number>{g.get("pick_count", 1)}</selection_number>
      <selection_extension>
        <points_per_item>{float(g.get("points", 1)):.1f}</points_per_item>
      </selection_extension>
    </selection>
  </selection_ordering>
{items}
</section>''')
    body = "\n".join(_indent(s, 3) for s in sections)
    return f'''<?xml version="1.0"?>
<questestinterop {QTI_NS} xsi:schemaLocation="{QTI_SCHEMA}">
  <assessment ident="{quiz_ident(run_id)}" title="{attr(quiz.get("title", "Quiz"))}">
    <qtimetadata>
      <qtimetadatafield>
        <fieldlabel>cc_maxattempts</fieldlabel>
        <fieldentry>1</fieldentry>
      </qtimetadatafield>
    </qtimetadata>
    <section ident="root_section">
{body}
    </section>
  </assessment>
</questestinterop>
'''


def _description(bank, quiz: dict, points: float) -> str:
    """A human quiz description with the grading criteria. HTML, then XML-escaped for the
    text/html field."""
    n = len(_quiz_groups(quiz))
    src = f" from the lecture <em>{html.escape(bank.source)}</em>" if bank.source else ""
    html_body = (
        f"<p>Auto-generated quiz{src}. It covers {n} concept"
        f"{'s' if n != 1 else ''}, with one question drawn from each.</p>"
        f"<p><strong>Grading:</strong> {points:.0f} point"
        f"{'s' if points != 1 else ''} total, 1 point per question, single attempt.</p>"
    )
    return _xml(html_body)


def emit_assessment_meta(bank, quiz: dict) -> str:
    """Canvas quiz settings. Safe defaults; the assignment block omits assignment_group so a
    minimal import lands in the default group (to confirm against the Canvas sample)."""
    run_id = bank.run_id
    points = _points_possible(quiz)
    return f'''<?xml version="1.0"?>
<quiz {META_NS} identifier="{quiz_ident(run_id)}">
  <title>{_xml(quiz.get("title", "Quiz"))}</title>
  <description>{_description(bank, quiz, points)}</description>
  <shuffle_questions>false</shuffle_questions>
  <shuffle_answers>false</shuffle_answers>
  <scoring_policy>keep_highest</scoring_policy>
  <quiz_type>assignment</quiz_type>
  <points_possible>{points:.1f}</points_possible>
  <allowed_attempts>1</allowed_attempts>
  <available>false</available>
  <one_question_at_a_time>false</one_question_at_a_time>
  <show_correct_answers>true</show_correct_answers>
  <assignment identifier="{item_id(run_id, "assignment")}">
    <title>{_xml(quiz.get("title", "Quiz"))}</title>
    <workflow_state>unpublished</workflow_state>
    <quiz_identifierref>{quiz_ident(run_id)}</quiz_identifierref>
    <points_possible>{points:.1f}</points_possible>
    <grading_type>points</grading_type>
    <submission_types>online_quiz</submission_types>
  </assignment>
</quiz>
'''


def _quiz_resources(bank, quiz: dict) -> str:
    """The two <resource> blocks for one quiz: the QTI file, and its meta as a dependency."""
    q = quiz_ident(bank.run_id)
    meta_res = iid(bank.run_id, "meta")
    return f'''    <resource identifier="{q}" type="imsqti_xmlv1p2">
      <file href="{q}/{q}.xml"/>
      <dependency identifierref="{meta_res}"/>
    </resource>
    <resource identifier="{meta_res}" type="associatedcontent/imscc_xmlv1p1/learning-application-resource" href="{q}/assessment_meta.xml">
      <file href="{q}/assessment_meta.xml"/>
    </resource>'''


def _manifest(manifest_id: str, title: str, resources: str) -> str:
    """A QTI Quiz Export manifest. Quiz resources are plain `imsqti_xmlv1p2` pointing at the
    inline-questions file — the shape that imports with questions (reference/Classic-Quiz-Sample).
    Any number of quizzes can be declared here, which is what makes a one-import bundle work."""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{manifest_id}" {MANIFEST_NS}>
  <metadata>
    <schema>IMS Content</schema>
    <schemaversion>1.1.3</schemaversion>
    <imsmd:lom>
      <imsmd:general>
        <imsmd:title>
          <imsmd:string>{_xml(title)}</imsmd:string>
        </imsmd:title>
      </imsmd:general>
    </imsmd:lom>
  </metadata>
  <organizations/>
  <resources>
{resources}
  </resources>
</manifest>
'''


def emit_manifest(bank, quiz: dict) -> str:
    return _manifest(qid(bank.run_id, "manifest"),
                     f'QTI Quiz Export for "{quiz.get("title", "Quiz")}"',
                     _quiz_resources(bank, quiz))


def emit_bundle_manifest(entries: list[tuple], title: str) -> str:
    """One manifest declaring every quiz in the bundle."""
    resources = "\n".join(_quiz_resources(b, q) for b, q in entries)
    manifest_id = qid(*[b.run_id for b, _ in entries], "bundle")
    return _manifest(manifest_id, title, resources)


# --------------------------------------------------------------- packaging

def package_files(bank, quiz: dict) -> dict[str, str]:
    """The arcname -> content map that makes up the .imscc.

    Questions are inline in the assessment (emit_assessment), so there are no separate
    objectbank files — those did not re-import as Canvas question banks.
    """
    return {"imsmanifest.xml": emit_manifest(bank, quiz), **_quiz_files(bank, quiz)}


def _quiz_files(bank, quiz: dict) -> dict[str, str]:
    """One quiz's two files, keyed by arcname. Shared by the single and bundle packages."""
    q = quiz_ident(bank.run_id)
    return {
        f"{q}/{q}.xml": emit_assessment(bank, quiz),
        f"{q}/assessment_meta.xml": emit_assessment_meta(bank, quiz),
    }


def bundle_files(entries: list[tuple], title: str) -> dict[str, str]:
    """Every quiz in one package: N quiz folders + a manifest declaring them all."""
    files = {"imsmanifest.xml": emit_bundle_manifest(entries, title)}
    for b, quiz in entries:
        for arc, data in _quiz_files(b, quiz).items():
            if arc in files:
                raise ValueError(f"two quizzes produced the same file: {arc}")
            files[arc] = data
    return files


def write_imscc(bank, quiz: dict, out_path) -> Path:
    """Write a Canvas QTI quiz package: a standard-deflate .zip, imsmanifest.xml at root.

    Extension is .zip (not .imscc) because this is a QTI Quiz Export — import it via Canvas's
    'QTI .zip file' option, not 'Canvas Course Export Package'.
    """
    files = package_files(bank, quiz)  # may raise NotImplementedError — do it before any I/O
    out_path = Path(out_path)
    if out_path.suffix != ".zip":
        out_path = out_path.with_suffix(".zip")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, data in files.items():
            z.writestr(arc, data)
    return out_path


# ----------------------------------------------- re-emit from saved bank.json

def _quiz_for(bank, quiz_json_path: Path) -> dict:
    """Prefer the saved quiz.json; else synthesise a pick-1-per-group quiz from the bank."""
    import json
    if quiz_json_path.exists():
        return json.loads(quiz_json_path.read_text(encoding="utf-8"))
    return {"title": bank.title,
            "groups": [{"group_id": gid, "pick_count": 1, "points": 1}
                       for gid in sorted(bank.groups)]}


def _incomplete_reason(bank) -> str | None:
    """Why a bank.json must not be emitted: an incomplete generation run would ship a broken quiz.

    The concrete break is an **empty group** — a concept the model opened but never filled — which
    otherwise sails through as a phantom question that draws nothing, so the quiz is silently short
    (week 9's `c5` was exactly this). `bank.validate_final` catches it at generation time and refuses
    to finalize; emit re-checks it because a partial, autosaved `bank.json` is still on disk."""
    if not bank.groups:
        return "no question groups"
    empty = [gid for gid, g in bank.groups.items() if not g.variants]
    if empty:
        return (f"group '{empty[0]}' has no variants — generation did not complete "
                f"(finalized={getattr(bank, 'finalized', False)}); regenerate this week")
    return None


def _quiz_bank_mismatch(bank, quiz: dict) -> str | None:
    """A stale `quiz.json` can reference groups a (re)generated or interrupted `bank.json` no longer
    has — emitting it would `KeyError` in `emit_assessment`. Catch it so one out-of-sync week is
    skipped with a clear reason, not fatal to the whole-course package. (Seen 2026-07-31: an
    interrupted week-7 quiz left a one-group bank beside a stale five-group quiz.json.)"""
    referenced = {g["group_id"] for g in quiz.get("groups", [])} | set(quiz.get("picks", {}))
    missing = sorted(referenced - set(bank.groups))
    if missing:
        return (f"quiz.json references group(s) {missing} not in bank.json — the quiz is out of sync "
                f"with the bank (an interrupted or partial generation); regenerate this week's quiz")
    return None


def _load_banks(path) -> tuple[list[tuple], list[tuple]]:
    """(entries, skipped) for every bank.json under path. entries are (bank, quiz, bank_json)."""
    from coursekit.generate.quiz.bank import Bank
    path = Path(path)
    jsons = [path] if path.is_file() else sorted(path.glob("**/bank.json"))
    entries, skipped = [], []
    for bj in jsons:
        b = Bank.model_validate_json(bj.read_text(encoding="utf-8"))
        reason = _incomplete_reason(b)
        if reason:
            skipped.append((bj, reason))
            continue
        quiz = _quiz_for(b, bj.parent / "quiz.json")
        reason = _quiz_bank_mismatch(b, quiz)
        if reason:
            skipped.append((bj, reason))
            continue
        try:
            _quiz_files(b, quiz)  # surfaces unsupported question types before we commit
        except NotImplementedError as e:
            skipped.append((bj, str(e)))
            continue
        entries.append((b, quiz, bj))
    return entries, skipped


def bundle(path, out_path=None, title=None) -> tuple:
    """Bundle every bank.json under `path` into ONE package — one import, many quizzes.

    Returns (out_path_or_None, included_bank_jsons, skipped).
    """
    path = Path(path)
    entries, skipped = _load_banks(path)
    if not entries:
        return None, [], skipped

    pairs = [(b, q) for b, q, _ in entries]
    title = title or f"Quizzes ({len(pairs)})"
    files = bundle_files(pairs, title)

    if out_path is None:
        base = path if path.is_dir() else path.parent
        out_path = base / "all-quizzes.zip"
    out_path = Path(out_path)
    if out_path.suffix != ".zip":
        out_path = out_path.with_suffix(".zip")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, data in files.items():
            z.writestr(arc, data)
    return out_path, [bj for _, _, bj in entries], skipped


def reemit(path) -> list[tuple]:
    """Walk a bank.json (or a tree of them) and write an .imscc beside each. Model-free.

    Returns (bank_json, imscc_or_None, reason). A bank with a not-yet-supported question type is
    skipped with a reason rather than aborting the whole walk.
    """
    from coursekit.generate.quiz.bank import Bank
    path = Path(path)
    jsons = [path] if path.is_file() else sorted(path.glob("**/bank.json"))
    results = []
    for bj in jsons:
        b = Bank.model_validate_json(bj.read_text(encoding="utf-8"))
        reason = _incomplete_reason(b)
        if reason:
            results.append((bj, None, reason))
            continue
        quiz = _quiz_for(b, bj.parent / "quiz.json")
        reason = _quiz_bank_mismatch(b, quiz)
        if reason:
            results.append((bj, None, reason))
            continue
        out = bj.parent / f"{bj.parent.name}.zip"
        try:
            results.append((bj, write_imscc(b, quiz, out), None))
        except NotImplementedError as e:
            results.append((bj, None, str(e)))
    return results
