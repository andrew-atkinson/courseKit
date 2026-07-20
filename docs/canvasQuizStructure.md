# Canvas quiz import: the format that works

Reference for `qti.py`. Every structure here is read from real Canvas exports and **confirmed by
importing the result into a live Canvas course** — quizzes arrive with their questions, and the
question groups randomize.

> **The one thing to know.** Canvas has two quiz package formats, and only one of them imports
> questions. Emit the **QTI Quiz Export** format (below), import it via **"QTI .zip file"**.
> Do *not* emit the full-course Common Cartridge flavour — see [The trap](#the-trap).

## Package layout (verified)

A `.zip`, standard deflate, `imsmanifest.xml` at the root:

```
imsmanifest.xml
<quiz-id>/
  <quiz-id>.xml          # the assessment: ALL questions, inline
  assessment_meta.xml    # Canvas quiz settings
```

One quiz folder per quiz. A **bundle** is the same thing with N quiz folders and one manifest
declaring all of them — a single import creates every quiz. Both forms are confirmed working.

Identifiers are `g` + 32 hex (quizzes, sections), `i` + 32 hex (the meta resource). Derive them
deterministically (e.g. `md5(run_id:…)`) so re-emitting is idempotent — Canvas then updates on
re-import rather than duplicating.

## The manifest

```xml
<manifest identifier="<g-hex>" xmlns="http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1" xmlns:lom="http://ltsc.ieee.org/xsd/imsccv1p1/LOM/resource" xmlns:imsmd="http://www.imsglobal.org/xsd/imsmd_v1p2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1 http://www.imsglobal.org/xsd/imscp_v1p1.xsd http://ltsc.ieee.org/xsd/imsccv1p1/LOM/resource http://www.imsglobal.org/profile/cc/ccv1p1/LOM/ccv1p1_lomresource_v1p0.xsd http://www.imsglobal.org/xsd/imsmd_v1p2 http://www.imsglobal.org/xsd/imsmd_v1p2p2.xsd">
  <metadata>
    <schema>IMS Content</schema>
    <schemaversion>1.1.3</schemaversion>
    <imsmd:lom><imsmd:general><imsmd:title>
      <imsmd:string>QTI Quiz Export for "..."</imsmd:string>
    </imsmd:title></imsmd:general></imsmd:lom>
  </metadata>
  <organizations/>
  <resources>
    <!-- repeat this pair per quiz for a bundle -->
    <resource identifier="<quiz-id>" type="imsqti_xmlv1p2">
      <file href="<quiz-id>/<quiz-id>.xml"/>
      <dependency identifierref="<meta-id>"/>
    </resource>
    <resource identifier="<meta-id>" type="associatedcontent/imscc_xmlv1p1/learning-application-resource" href="<quiz-id>/assessment_meta.xml">
      <file href="<quiz-id>/assessment_meta.xml"/>
    </resource>
  </resources>
</manifest>
```

Load-bearing details:
- Resource type is plain **`imsqti_xmlv1p2`**. Not `imsqti_xmlv1p2/imscc_xmlv1p1/assessment`.
- **`<organizations/>` is empty** and self-closing.
- Metadata is **IMS Content 1.1.3** with the `imsmd` namespace (not `lomimscc`).

## The assessment — questions inline, grouped

`<quiz-id>/<quiz-id>.xml`. `root_section` holds one `<section>` per concept; each is a **question
group** containing its variants inline plus a `<selection_ordering>` that picks N of them. Canvas
honours the pick: students get a random variant per group.

```xml
<?xml version="1.0"?>
<questestinterop xmlns="http://www.imsglobal.org/xsd/ims_qtiasiv1p2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.imsglobal.org/xsd/ims_qtiasiv1p2 http://www.imsglobal.org/xsd/ims_qtiasiv1p2p1.xsd">
  <assessment ident="<quiz-id>" title="Week 3: Repetition">
    <qtimetadata>
      <qtimetadatafield><fieldlabel>cc_maxattempts</fieldlabel><fieldentry>1</fieldentry></qtimetadatafield>
    </qtimetadata>
    <section ident="root_section">
      <section ident="<g-hex>" title="Anatomy of a for loop">
        <selection_ordering>
          <selection>
            <selection_number>1</selection_number>
            <selection_extension><points_per_item>1.0</points_per_item></selection_extension>
          </selection>
        </selection_ordering>
        <item .../>   <!-- the concept's variants, inline -->
        <item .../>
      </section>
      <!-- one section per concept -->
    </section>
  </assessment>
</questestinterop>
```

**No `<sourcebank_ref>`.** Drawing from a separate item bank does not survive import (see below).

## Text: two levels of escaping

`<mattext texttype="text/html">` holds **HTML that is then XML-escaped**. So `x < 10` becomes HTML
`x &lt; 10`, then XML `x &amp;lt; 10`. The tell in Canvas's own output is `&amp;nbsp;` — an HTML
`&nbsp;` escaped once more. Wrap the body in a `<div>`; markdown code spans become `<code>`.

## Item structures by question type

All verified from a real Classic quiz export. In bank/group items `points_possible` is empty
(`<fieldentry/>`); the group's `points_per_item` assigns the score.

- **multiple_choice_question** — `<response_lid rcardinality="Single"><render_choice>` of
  `<response_label ident>`; `<resprocessing>` with
  `<decvar varname="SCORE" maxvalue="100" minvalue="0" vartype="Decimal"/>` and one
  `<respcondition continue="No">` whose `<varequal respident="response1">` names the correct label,
  then `<setvar action="Set" varname="SCORE">100</setvar>`.
- **true_false_question** — the same shape with two labels, "True" and "False".
  *(Inferred rather than sampled, but confirmed working on import.)*
- **short_answer_question** — `<response_str><render_fib><response_label ident="answer1"/>`.
  One respcondition whose conditionvar holds a `<varequal>` **per accepted answer** (OR), score 100.
- **multiple_answers_question** — `<response_lid rcardinality="Multiple">`. Scoring is
  **all-or-nothing**: `<conditionvar><and>` with a bare `<varequal>` for each correct option and a
  `<not><varequal></not>` for each wrong one.
- **matching_question** — one `<response_lid ident="response_<leftId>">` per left item (its text in
  `<material><mattext>`), each offering the **shared** right-option set. One respcondition per left,
  `setvar action="Add"` of `round(100/n, 2)`. `original_answer_ids` lists the left ids.
- **numerical_question** — `<response_str><render_fib fibtype="Decimal">` (the `fibtype` is the
  marker). One respcondition matching exact-or-within-margin:
  `<or><varequal>answer</varequal><and><vargt>lo</vargt><varlte>hi</varlte></and></or>`.
  **Canvas uses `vargt` (strictly greater) for the lower bound when there is a margin, but
  `vargte` when the margin is zero** — otherwise an exact answer falls outside its own bounds.
  Numbers are decimals (`4.0`, `2.7175`); round before formatting so float arithmetic doesn't
  leak `2.7174999999999998`. A pure *range* question (rather than answer±margin) instead uses a
  bare `<vargte>lo</vargte><varlte>hi</varlte>` with no `<or>` — we don't model that form.
- `essay_question` / `text_only_question` exist but aren't in our model.

## assessment_meta.xml

```xml
<quiz identifier="<quiz-id>" xmlns="http://canvas.instructure.com/xsd/cccv1p0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://canvas.instructure.com/xsd/cccv1p0 https://canvas.instructure.com/xsd/cccv1p0.xsd">
```

Note `xmlns:xsi` is the **XMLSchema-instance** URL with a separate `xsi:schemaLocation`. Canvas's
own *course* export writes this malformed (it puts the schemaLocation into `xmlns:xsi`) — don't copy
that. Load-bearing fields: `<title>`, `<description>` (escaped HTML), `<quiz_type>assignment</quiz_type>`,
`<points_possible>`, `<allowed_attempts>`, `<scoring_policy>`, plus a nested `<assignment>` block.
Omitting `assignment_group_identifierref` is fine — the quiz lands in the default group.

## The trap

Canvas **course exports** (`.imscc`, imported as "Canvas Course Export Package") represent quizzes
completely differently, and reproducing that shape **imports an empty quiz**:

```
<quiz-id>/assessment_qti.xml     # a CC stub with an EMPTY <section ident="root_section"/>
<quiz-id>/assessment_meta.xml
non_cc_assessments/<quiz-id>.xml.qti   # the real QTI (Canvas-proprietary)
non_cc_assessments/<bank-id>.xml.qti   # objectbanks the quiz draws from
```

Canvas reads the **empty stub** as the quiz and offers the real files as course **Files**. We
reproduced this exactly — matching the namespaces, the `learning-application-resource` wiring, all of
it — and got an empty quiz twice, once with item banks and once with inline questions. Even for a
quiz whose questions are inline, a course export leaves `assessment_qti.xml` empty.

Two consequences:
- **Separate `<objectbank>` files do not re-import as question banks.** They land in Files. Any
  randomization built on `<sourcebank_ref>` therefore resolves to nothing.
- Randomization must instead come from **inline question groups**, as documented above.

Import type matters as much as format: a QTI Quiz Export is a **`.zip`** imported via
**"QTI .zip file"**. Importing it as a "Canvas Course Export Package" is the wrong door.
