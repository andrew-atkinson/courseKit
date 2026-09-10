"""Canvas Assignment resource XML — the per-assignment CC parts (settings, instructions HTML, rubric).

Grounded from the real ARGS260 Canvas export (its assignments + `course_settings/rubrics.xml`, verified
against an upload-with-rubric assignment): an assignment is a `learning-application-resource` whose dir
holds the instructions HTML + an `assignment_settings.xml` (`<assignment xmlns=…cccv1p0>`); a structured
rubric lives in `course_settings/rubrics.xml` and is attached via `<rubric_identifierref>`. The emitted
fields are a valid subset of the export's (Canvas defaults the rest). The MANIFEST/module wiring is NOT here — `emit/sources/
assignments.py` turns these parts into cartridge items so the shared assembler (`cartridge.py`) places
an assignment in a week module exactly like a page or quiz. `emit_from_path` routes a standalone
`emit assignments` through that same assembler.
"""

from pathlib import Path

from coursekit.emit import cc          # reuse gid / _xml / _attr
from coursekit.generate.assignment.assignment import Assignment

CC_NS = 'xmlns="http://canvas.instructure.com/xsd/cccv1p0"'


def assignment_ident(a: Assignment) -> str:
    return cc.gid(a.assignment_id, "assignment")


def group_ident(group_title: str) -> str:
    return cc.gid(group_title, "assignment_group")


def _assignment_page(a: Assignment):
    """The assignment's instructions as a PAGE of typed blocks — so it renders through the page
    design system (theme type/spacing/headings, styled code, `_md_inline`) exactly like a course page.
    No Markdown parsing: the structure is explicit (paragraphs, a bullets block for steps)."""
    from coursekit.generate.page.page import Page, build_block
    pairs = []
    if a.overview.strip():
        pairs.append(("intro", "paragraph", {"text": a.overview.strip()}))
    pairs.append(("task-h", "heading", {"text": "Your task", "role": "concept"}))
    pairs.append(("task", "paragraph", {"text": a.task.strip()}))
    steps = [s.strip() for s in a.steps if s.strip()]
    if steps:
        pairs.append(("steps", "bullets", {"items": steps}))
    if a.deliverable.strip():
        pairs.append(("submit-h", "heading", {"text": "What to submit", "role": "practice"}))
        pairs.append(("submit", "paragraph", {"text": a.deliverable.strip()}))
    if a.rubric_criteria and not a.rubric:      # flat criteria in-text only when no structured rubric
        pairs.append(("assess-h", "heading", {"text": "How you'll be assessed", "role": "summary"}))
        pairs.append(("assess", "bullets", {"items": a.rubric_criteria}))
    blocks = {bid: build_block(k, block_id=bid, **f) for bid, k, f in pairs}
    return Page(page_id=a.assignment_id, title=a.title, page_type="assignment",
                week_ref=a.week_ref, slug=a.slug, blocks=blocks, finalized=True)


def assignment_html(a: Assignment, style=None) -> str:
    """The instructions as a standalone HTML doc, rendered through the page renderer with the course
    THEME (like a page). `style` is a resolved theme; None falls back to the default identity."""
    from coursekit.generate.page.renderer import render_body
    from coursekit.generate.page.style import load_style
    body = render_body(_assignment_page(a), style=style or load_style(None))
    return (f"<html>\n<head>\n"
            f'<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>\n'
            f"<title>Assignment: {cc._xml(a.title)}</title>\n</head>\n<body>\n"
            f"{body}\n</body>\n</html>\n")


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
            f"  <allowed_extensions></allowed_extensions>\n"   # empty = any file (matches the export)
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


def emit_from_path(path, out_path=None) -> Path | None:
    """Package every `assignment.json` under `path` into ONE `.imscc` (model-free), through the shared
    cartridge assembler with ONLY the assignment source — so a standalone `emit assignments` gets the
    SAME module/manifest/course_settings structure the whole-course cartridge does (that is what makes
    it importable). Returns the written path, or None when there are none."""
    from coursekit.emit import cartridge
    from coursekit.emit.sources.assignments import AssignmentSource

    p = Path(path)
    default_out = (p if p.is_dir() else p.parent) / "assignments.imscc"
    return cartridge.write_course_imscc(path, out_path=out_path or default_out,
                                        sources=[AssignmentSource()])
