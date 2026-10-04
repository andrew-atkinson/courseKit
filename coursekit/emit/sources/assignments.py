"""Assignments as cartridge items — `assignment.json` → `Assignment` module items, plus the
course-level `rubrics.xml` / `assignment_groups.xml` a source contributes via `course_settings()`.

The per-resource XML (settings, html, rubric) lives in `emit/assignment.py`, grounded from the real
ARGS260 course export; this wires it into the shared cartridge assembler so an assignment lands in a
week module exactly like a page or quiz (and imports the same way).
"""

from pathlib import Path

from coursekit.courseconfig import week_key
from coursekit.emit import assignment as ae
from coursekit.emit import cc
from coursekit.emit.cartridge import CartridgeItem
from coursekit.generate.assignment.assignment import Assignment


def _load(course_path):
    """(Assignment, source_path) for every assignment.json under the course, in stable order."""
    out = []
    for f in sorted(Path(course_path).rglob("assignment.json")):
        out.append((Assignment.model_validate_json(f.read_text(encoding="utf-8")), f))
    return out


def _resource(a: Assignment) -> str:
    aid = ae.assignment_ident(a)
    return (f'    <resource identifier="{aid}" '
            f'type="associatedcontent/imscc_xmlv1p1/learning-application-resource" '
            f'href="{aid}/{a.slug}.html">\n'
            f'      <file href="{aid}/{a.slug}.html"/>\n'
            f'      <file href="{aid}/assignment_settings.xml"/>\n    </resource>')


class AssignmentSource:
    content_type = "Assignment"

    def __init__(self):
        self._loaded = []

    def collect(self, course_path) -> list[CartridgeItem]:
        from coursekit.courseconfig import find_root
        from coursekit.coursestructure import CourseStructure
        from coursekit.generate.page.style import load_style
        self._loaded = _load(course_path)
        root = find_root(Path(course_path))
        style = load_style(root)                            # the course theme, so assignments match pages
        scheme = CourseStructure.load(course_path).grading()   # declared grading groups (STRC-2)
        items = []
        for a, f in self._loaded:
            aid = ae.assignment_ident(a)
            group = scheme.group_for("assignment", slug=a.slug) or a.group_title   # declared → default
            items.append(CartridgeItem(
                week_key=week_key(a.week_ref) if a.week_ref else None,
                content_type="Assignment",
                title=a.title,
                resource_id=aid,
                item_id=cc.gid(a.assignment_id, "item"),
                resource_xml=_resource(a),
                files={f"{aid}/{a.slug}.html": ae.assignment_html(a, style=style),
                       f"{aid}/assignment_settings.xml": ae.assignment_settings_xml(a, group_title=group)},
                rank=2,   # assignments after pages(0) / quizzes(1) in a week's module
                source=f,
            ))
        return items

    def course_settings(self) -> dict:
        """Course-level files this source contributes: the rubrics when any assignment has one. The
        assignment GROUPS file is emitted by the assembler (`cartridge.py`) from the declared scheme, so
        it spans quizzes too and exists even with no assignments (STRC-2)."""
        assignments = [a for a, _ in self._loaded]
        if assignments and any(a.rubric for a in assignments):
            return {"course_settings/rubrics.xml": ae.rubrics_xml(assignments)}
        return {}
