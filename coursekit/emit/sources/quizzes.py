"""Quizzes as cartridge items — `bank.json` → `Quizzes::Quiz` module items.

Inside a full-course Common Cartridge a quiz is NOT the standalone "QTI .zip" shape `qti.write_imscc`
emits. It is the **CC-profile** shape, transcribed from the real course export in `reference/`:

    <id>/assessment_qti.xml            a stub: cc_profile cc.exam.v0p1, empty <section root_section/>
    <id>/assessment_meta.xml           the quiz settings   (qti.emit_assessment_meta)
    non_cc_assessments/<id>.xml.qti    the actual questions (qti.emit_assessment)

wired in the manifest as an `imsqti_xmlv1p2/imscc_xmlv1p1/assessment` resource whose meta+questions
hang off a `learning-application-resource` dependency. The *questions* come from the same
`qti.emit_assessment` the .zip path uses — only the packaging differs.
"""

from coursekit.courseconfig import week_key
from coursekit.emit import cc, qti
from coursekit.emit.cartridge import CartridgeItem


def _assessment_stub(qid: str, title: str) -> str:
    """The CC-profile `assessment_qti.xml` — metadata + an empty root section. Canvas reads the real
    questions from the `non_cc_assessments` file the meta resource points at."""
    return (f'<?xml version="1.0"?>\n'
            f'<questestinterop xmlns="http://www.imsglobal.org/xsd/ims_qtiasiv1p2" '
            f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            f'xsi:schemaLocation="http://www.imsglobal.org/xsd/ims_qtiasiv1p2 '
            f'http://www.imsglobal.org/profile/cc/ccv1p1/ccv1p1_qtiasiv1p2p1_v1p0.xsd">\n'
            f'  <assessment ident="{qid}" title="{cc._attr(title)}">\n'
            f'    <qtimetadata>\n'
            f'      <qtimetadatafield>\n'
            f'        <fieldlabel>cc_profile</fieldlabel>\n'
            f'        <fieldentry>cc.exam.v0p1</fieldentry>\n'
            f'      </qtimetadatafield>\n'
            f'      <qtimetadatafield>\n'
            f'        <fieldlabel>qmd_assessmenttype</fieldlabel>\n'
            f'        <fieldentry>Examination</fieldentry>\n'
            f'      </qtimetadatafield>\n'
            f'      <qtimetadatafield>\n'
            f'        <fieldlabel>cc_maxattempts</fieldlabel>\n'
            f'        <fieldentry>1</fieldentry>\n'
            f'      </qtimetadatafield>\n'
            f'    </qtimetadata>\n'
            f'    <section ident="root_section"/>\n'
            f'  </assessment>\n'
            f'</questestinterop>\n')


def _quiz_resources(qid: str, meta_id: str) -> str:
    """The two manifest resources: the assessment stub, and the meta+questions dependency."""
    return (f'    <resource identifier="{qid}" type="imsqti_xmlv1p2/imscc_xmlv1p1/assessment">\n'
            f'      <file href="{qid}/assessment_qti.xml"/>\n'
            f'      <dependency identifierref="{meta_id}"/>\n'
            f'    </resource>\n'
            f'    <resource identifier="{meta_id}" '
            f'type="associatedcontent/imscc_xmlv1p1/learning-application-resource" '
            f'href="{qid}/assessment_meta.xml">\n'
            f'      <file href="{qid}/assessment_meta.xml"/>\n'
            f'      <file href="non_cc_assessments/{qid}.xml.qti"/>\n'
            f'    </resource>')


class QuizzesSource:
    content_type = "Quizzes::Quiz"

    def collect(self, course_path) -> list[CartridgeItem]:
        entries, skipped = qti._load_banks(course_path)   # (bank, quiz, bank_json); guards run here
        for bj, reason in skipped:                          # a broken week is warned + omitted, not fatal
            print(f"  ⚠ skipped quiz {bj.parent.name}: {reason}")
        items = []
        for bank, quiz, bj in entries:
            qid = qti.quiz_ident(bank.run_id)
            meta_id = qti.iid(bank.run_id, "meta")
            title = quiz.get("title") or bank.title or "Quiz"
            items.append(CartridgeItem(
                week_key=week_key(bj.parent.name),
                content_type="Quizzes::Quiz",
                title=title,
                resource_id=qid,
                item_id=cc.gid(bank.run_id, "item"),
                resource_xml=_quiz_resources(qid, meta_id),
                files={
                    f"{qid}/assessment_qti.xml": _assessment_stub(qid, title),
                    f"{qid}/assessment_meta.xml": qti.emit_assessment_meta(bank, quiz),
                    f"non_cc_assessments/{qid}.xml.qti": qti.emit_assessment(bank, quiz),
                },
                rank=1,   # quizzes after pages in a week's module
            ))
        return items
