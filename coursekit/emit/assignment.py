"""Canvas Assignment emitter — the assignment IR → a Common Cartridge `.imscc`.

Grounded from a real Canvas export (reference/arph201 … `assignment_settings.xml`), not the spec: an
assignment is a `learning-application-resource` whose dir holds the instructions HTML + an
`assignment_settings.xml` (`<assignment xmlns=…cccv1p0>`), with a `course_settings/assignment_groups.xml`
and a module item wiring it into the manifest. Reuses cc.py's id/escaping/packaging helpers so the
package shape matches the page cartridge.

NOT here yet: the structured Canvas rubric object (ASMT-7) — this export carries no rubric, so its CC
format isn't grounded. Criteria live in the instructions for now (see assignment.render_instructions).
"""

import zipfile
from pathlib import Path

from coursekit.emit import cc          # reuse gid / _xml / _attr / packaging
from coursekit.generate.assignment.assignment import Assignment, render_instructions

CC_NS = 'xmlns="http://canvas.instructure.com/xsd/cccv1p0"'
IMS_NS = ('xmlns="http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1" '
          'xmlns:lom="http://ltsc.ieee.org/xsd/imsccv1p1/LOM/resource" '
          'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"')


def assignment_ident(a: Assignment) -> str:
    return cc.gid(a.assignment_id, "assignment")


def group_ident(group_title: str) -> str:
    return cc.gid(group_title, "assignment_group")


def _href(a: Assignment) -> str:
    return f"{assignment_ident(a)}/{a.slug}.html"


def assignment_html(a: Assignment) -> str:
    """The instructions body — a standalone HTML doc, matching the export's shape."""
    return (f"<html>\n<head>\n"
            f'<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>\n'
            f"<title>Assignment: {cc._xml(a.title)}</title>\n</head>\n<body>\n"
            f"{render_instructions(a)}\n</body>\n</html>\n")


def rubric_ident(a: Assignment) -> str:
    return cc.gid(a.assignment_id, "rubric")


def assignment_settings_xml(a: Assignment) -> str:
    """`assignment_settings.xml` — the Canvas settings (grounded field set; the many boolean flags take
    the export's defaults). points_possible + submission_types + the group ref are what vary; a
    structured rubric attaches via `rubric_identifierref` and sets the point total."""
    rubric_block = ""
    if a.rubric:
        rubric_block = (f"  <rubric_identifierref>{rubric_ident(a)}</rubric_identifierref>\n"
                        f"  <rubric_use_for_grading>true</rubric_use_for_grading>\n"
                        f"  <rubric_hide_points>false</rubric_hide_points>\n"
                        f"  <rubric_hide_score_total>false</rubric_hide_score_total>\n")
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<assignment identifier="{assignment_ident(a)}" {CC_NS} '
            f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            f"  <title>{cc._xml(a.title)}</title>\n"
            f"  <assignment_group_identifierref>{group_ident(a.group_title)}"
            f"</assignment_group_identifierref>\n"
            f"{rubric_block}"
            f"  <workflow_state>unpublished</workflow_state>\n"
            f"  <points_possible>{a.effective_points:.1f}</points_possible>\n"
            f"  <grading_type>points</grading_type>\n"
            f"  <submission_types>{a.submission_type}</submission_types>\n"
            f"  <position>1</position>\n"
            f"  <peer_reviews>false</peer_reviews>\n"
            f"  <omit_from_final_grade>false</omit_from_final_grade>\n"
            f"</assignment>\n")


def _rubric_xml(a: Assignment) -> str:
    """One `<rubric>` for course_settings/rubrics.xml — criteria × rating-levels × points, grounded
    from the ARGS260 export. Criterion/rating ids are deterministic so a re-emit is stable."""
    r = a.rubric
    crits = []
    for i, c in enumerate(r.criteria):
        cid = f"{rubric_ident(a)}_c{i}"
        ratings = "\n".join(
            f"          <rating>\n"
            f"            <description>{cc._xml(rt.description)}</description>\n"
            f"            <points>{rt.points:.1f}</points>\n"
            f"            <criterion_id>{cid}</criterion_id>\n"
            f"            <id>{cid}_r{j}</id>\n          </rating>"
            for j, rt in enumerate(c.ratings))
        crits.append(
            f"      <criterion>\n"
            f"        <criterion_id>{cid}</criterion_id>\n"
            f"        <points>{c.points:.1f}</points>\n"
            f"        <description>{cc._xml(c.description)}</description>\n"
            f"        <long_description>{cc._xml(c.long_description)}</long_description>\n"
            f"        <ratings>\n{ratings}\n        </ratings>\n      </criterion>")
    return (f'  <rubric identifier="{rubric_ident(a)}">\n'
            f"    <read_only>false</read_only>\n"
            f"    <title>{cc._xml(r.title)}</title>\n"
            f"    <reusable>false</reusable>\n    <public>false</public>\n"
            f"    <points_possible>{r.points_possible:.1f}</points_possible>\n"
            f"    <hide_score_total>false</hide_score_total>\n"
            f"    <free_form_criterion_comments>false</free_form_criterion_comments>\n"
            f"    <criteria>\n" + "\n".join(crits) + "\n    </criteria>\n  </rubric>")


def rubrics_xml(assignments: list[Assignment]) -> str:
    """`course_settings/rubrics.xml` — one `<rubric>` per assignment that carries one."""
    rubrics = "\n".join(_rubric_xml(a) for a in assignments if a.rubric)
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<rubrics {CC_NS} xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            f"{rubrics}\n</rubrics>\n")


def assignment_groups_xml(group_titles) -> str:
    groups = "\n".join(
        f'  <assignmentGroup identifier="{group_ident(t)}">\n'
        f"    <title>{cc._xml(t)}</title>\n    <position>{i + 1}</position>\n"
        f"    <group_weight>0.0</group_weight>\n  </assignmentGroup>"
        for i, t in enumerate(group_titles))
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<assignmentGroups {CC_NS} xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            f"{groups}\n</assignmentGroups>\n")


def emit_manifest(assignments: list[Assignment], course_title: str) -> str:
    items = "\n".join(
        f'          <item identifier="{cc.gid(a.assignment_id, "item")}" '
        f'identifierref="{assignment_ident(a)}">\n'
        f"            <title>{cc._xml(a.title)}</title>\n          </item>"
        for a in assignments)
    resources = "\n".join(
        f'    <resource identifier="{assignment_ident(a)}" '
        f'type="associatedcontent/imscc_xmlv1p1/learning-application-resource" href="{_href(a)}">\n'
        f'      <file href="{_href(a)}"/>\n'
        f'      <file href="{assignment_ident(a)}/assignment_settings.xml"/>\n    </resource>'
        for a in assignments)
    mod = cc.gid(course_title, "assignments-module")
    # course_settings bundles under ONE resource (canvas_export.txt marker + the settings files),
    # matching how the page cartridge and real Canvas exports wire it.
    settings_files = ('      <file href="course_settings/canvas_export.txt"/>\n'
                      '      <file href="course_settings/assignment_groups.xml"/>\n')
    if any(a.rubric for a in assignments):
        settings_files += '      <file href="course_settings/rubrics.xml"/>\n'
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<manifest identifier="{cc.gid(course_title, "manifest")}" '
            f"{IMS_NS}>\n  <organizations>\n    <organization identifier=\"org\" structure=\"rooted-hierarchy\">\n"
            f'      <item identifier="root">\n        <item identifier="{mod}">\n'
            f"          <title>Assignments</title>\n{items}\n        </item>\n      </item>\n"
            f"    </organization>\n  </organizations>\n  <resources>\n{resources}\n"
            f'    <resource identifier="{cc.course_ident(course_title)}" '
            f'type="associatedcontent/imscc_xmlv1p1/learning-application-resource" '
            f'href="course_settings/canvas_export.txt">\n{settings_files}    </resource>\n'
            f"  </resources>\n</manifest>\n")


def package_files(assignments: list[Assignment], course_title: str) -> dict[str, str]:
    """Every archive path → its text content. Deterministic, so a re-emit is byte-stable."""
    files = {"imsmanifest.xml": emit_manifest(assignments, course_title),
             "course_settings/canvas_export.txt": cc.CANVAS_EXPORT_MARKER,
             "course_settings/assignment_groups.xml":
                 assignment_groups_xml(sorted({a.group_title for a in assignments}))}
    if any(a.rubric for a in assignments):
        files["course_settings/rubrics.xml"] = rubrics_xml(assignments)
    for a in assignments:
        d = assignment_ident(a)
        files[f"{d}/{a.slug}.html"] = assignment_html(a)
        files[f"{d}/assignment_settings.xml"] = assignment_settings_xml(a)
    return files


def write_imscc(assignments: list[Assignment], course_title: str, out_path) -> Path:
    out_path = Path(out_path)
    if out_path.suffix != ".imscc":
        out_path = out_path.with_suffix(".imscc")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, data in package_files(assignments, course_title).items():
            z.writestr(arc, data)
    return out_path
