"""The course cartridge assembler — the whole course as ONE Canvas `.imscc`.

Where `cc.py` packages pages and `qti.py` packages quizzes each alone, this assembles **all** of a
course's artifacts into a single Common Cartridge that imports as week **modules** holding pages,
quizzes, and (later) discussions, assignments, and more.

The seam is deliberately open. A Common Cartridge is a manifest + a `module_meta.xml` organising
items into modules, where every item is the *same* shape — a `content_type`, a title, and an
`identifierref` at a resource — differing only in which `content_type` string it carries and which
files/resources it contributes. So each content type is one **`CartridgeSource`** producing
**`CartridgeItem`s**; the assembler knows nothing about pages or quizzes specifically. Adding
discussions (`DiscussionTopic`), assignments (`Assignment` + `rubrics.xml`), etc. is one new source
file — the shapes are all present in the real course export in `reference/`.

All XML here is transcribed from that export: a quiz is a CC-profile `assessment` stub +
`non_cc_assessments/<id>.xml.qti` (the questions) + `assessment_meta.xml`, typed `Quizzes::Quiz`; a
page is `webcontent`, typed `WikiPage`. There is no model — like the other emitters, it reads the
committed IR and packages it.
"""

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from coursekit import courseconfig
from coursekit.emit import cc


@dataclass
class CartridgeItem:
    """One thing that lands in a module: a page, a quiz, later a discussion or assignment.

    `resource_xml` is one or more `<resource>` blocks for the manifest; `files` is its arcname→content
    contributions to the zip; `resource_id` is what the module item points at (`identifierref`)."""
    week_key: str | None
    content_type: str          # "WikiPage" | "Quizzes::Quiz" | "DiscussionTopic" | "Assignment" | …
    title: str
    resource_id: str           # the module item's identifierref → the primary resource
    item_id: str               # the module-item identifier (distinct from the resource)
    resource_xml: str          # one or more <resource>…</resource> blocks
    files: dict                # arcname → content
    rank: int = 0              # order within a module (pages before quizzes, etc.)
    source: Path | None = None  # the file this item came from — named in a collision error


@runtime_checkable
class CartridgeSource(Protocol):
    """One content type's contribution. Implementations live in `emit/sources/`."""
    def collect(self, course_path) -> list[CartridgeItem]:
        """Every item of this content type found under the course path."""
        ...


def _default_sources() -> list:
    """The registered content types. Add a source here (one line) to include a new content type in
    the course cartridge — the assembler needs no other change."""
    from coursekit.emit.sources.pages import PagesSource
    from coursekit.emit.sources.quizzes import QuizzesSource
    return [PagesSource(), QuizzesSource()]


# ------------------------------------------------------------- module grouping

def _week_sort(k: str | None):
    """Numeric weeks first in order; anything else after, alphabetically. None sorts last."""
    if k is None:
        return (2, "")
    return (0, int(k)) if k.isdigit() else (1, k)


def _module_title(cfg, week_key: str | None, course_title: str) -> str:
    """A module's title: the course context's week title if known, else 'Week N', else the course."""
    if week_key is None:
        return course_title
    entry = cfg.week(week_key) if cfg else {}
    return (entry or {}).get("title") or f"Week {week_key}"


def _modules(items: list[CartridgeItem], path, course_title: str):
    """Group items into ordered week-modules: [(module_id, title, [items])]."""
    cfg = courseconfig.load(courseconfig.find_root(Path(path)) or Path(path))
    groups: dict = {}
    for it in items:
        groups.setdefault(it.week_key, []).append(it)
    modules = []
    for k in sorted(groups, key=_week_sort):
        mid = cc.gid(course_title, str(k), "module")
        its = sorted(groups[k], key=lambda it: (it.rank, it.title))
        modules.append((mid, _module_title(cfg, k, course_title), its))
    return modules


# ------------------------------------------------------------- module_meta.xml

def _meta_item(it: CartridgeItem, pos: int) -> str:
    return (f'      <item identifier="{it.item_id}">\n'
            f'        <content_type>{it.content_type}</content_type>\n'
            f'        <workflow_state>active</workflow_state>\n'
            f'        <title>{cc._xml(it.title)}</title>\n'
            f'        <identifierref>{it.resource_id}</identifierref>\n'
            f'        <position>{pos}</position>\n'
            f'        <new_tab>false</new_tab>\n'
            f'        <indent>0</indent>\n'
            f'        <link_settings_json>null</link_settings_json>\n'
            f'      </item>')


def _module_meta(modules, course_title: str) -> str:
    """`course_settings/module_meta.xml`: a module per week, each holding its items typed by
    content_type (WikiPage / Quizzes::Quiz / …) — what tells Canvas what each item is."""
    mods = []
    for pos, (mid, title, items) in enumerate(modules, 1):
        item_xml = "\n".join(_meta_item(it, i) for i, it in enumerate(items, 1))
        mods.append(f'  <module identifier="{mid}">\n'
                    f'    <title>{cc._xml(title)}</title>\n'
                    f'    <workflow_state>active</workflow_state>\n'
                    f'    <position>{pos}</position>\n'
                    f'    <require_sequential_progress>false</require_sequential_progress>\n'
                    f'    <locked>false</locked>\n'
                    f'    <items>\n{item_xml}\n    </items>\n'
                    f'  </module>')
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<modules {cc.CANVAS_NS}>\n'
            + "\n".join(mods) + "\n</modules>\n")


# ------------------------------------------------------------- manifest

def _organizations(modules, course_title: str) -> str:
    """The IMS rooted-hierarchy mirroring module_meta — LearningModules → module → item leaves."""
    mod_xml = []
    for mid, title, items in modules:
        leaves = "\n".join(
            f'          <item identifier="{it.item_id}" identifierref="{it.resource_id}">\n'
            f'            <title>{cc._xml(it.title)}</title>\n'
            f'          </item>' for it in items)
        mod_xml.append(f'        <item identifier="{mid}">\n'
                       f'          <title>{cc._xml(title)}</title>\n{leaves}\n        </item>')
    return ('  <organizations>\n'
            '    <organization identifier="org_1" structure="rooted-hierarchy">\n'
            '      <item identifier="LearningModules">\n'
            + "\n".join(mod_xml)
            + '\n      </item>\n    </organization>\n  </organizations>')


def _manifest(items: list[CartridgeItem], modules, course_title: str) -> str:
    """The Common Cartridge manifest: course metadata, the module tree, the course_settings resource
    (the Canvas-importer trigger), and every item's resource block(s)."""
    manifest_id = cc.gid(*[it.resource_id for it in items], "course-manifest")
    resources = "\n".join(it.resource_xml for it in items)
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<manifest identifier="{manifest_id}" {cc.MANIFEST_NS}>\n'
            f'  <metadata>\n'
            f'    <schema>IMS Common Cartridge</schema>\n'
            f'    <schemaversion>1.1.0</schemaversion>\n'
            f'    <lomimscc:lom>\n      <lomimscc:general>\n        <lomimscc:title>\n'
            f'          <lomimscc:string>{cc._xml(course_title)}</lomimscc:string>\n'
            f'        </lomimscc:title>\n      </lomimscc:general>\n    </lomimscc:lom>\n'
            f'  </metadata>\n'
            f'{_organizations(modules, course_title)}\n'
            f'  <resources>\n'
            f'{cc._course_settings_resource(course_title)}\n'
            f'{resources}\n'
            f'  </resources>\n</manifest>\n')


# ------------------------------------------------------------- assembly

class CartridgeCollision(ValueError):
    """Two items map to the same file inside the cartridge — a duplicate or ambiguous source in the
    course tree, not a bug. Carries the arcname and both offending items so the CLI can name them."""

    def __init__(self, arc: str, first: CartridgeItem, second: CartridgeItem):
        self.arc, self.first, self.second = arc, first, second
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f"two items map to the same cartridge file: {self.arc}\n"
            f"  - {self.first.title}  <-  {self.first.source or '?'}\n"
            f"  - {self.second.title}  <-  {self.second.source or '?'}\n"
            f"A course can hold only one item per file; remove or rename one of the two. "
            f"(emit scans every page.json / bank.json under the course tree, so a leftover or "
            f"duplicate copy — e.g. a decomposed and a monolithic page for the same week — is the "
            f"usual cause.)"
        )


def package_files(items: list[CartridgeItem], course_title: str) -> dict:
    """The arcname→content map for the whole course cartridge. A file collision is an error, not a
    silent overwrite — it names both sources so the duplicate is findable."""
    files: dict = {}
    owners: dict[str, CartridgeItem] = {}
    for it in items:
        for arc, data in it.files.items():
            prev = owners.get(arc)
            if prev is not None:
                raise CartridgeCollision(arc, prev, it)
            files[arc] = data
            owners[arc] = it
    files["course_settings/canvas_export.txt"] = cc.CANVAS_EXPORT_MARKER
    return files


def write_course_imscc(path, out_path=None, title=None, sources=None) -> Path | None:
    """Package a course's pages AND quizzes (and any future content types) into ONE `.imscc` whose
    items land in week modules. Returns the written path, or None when nothing was found.

    Deterministic ids mean re-packaging the same course yields byte-stable output.
    """
    srcs = _default_sources() if sources is None else sources
    items: list[CartridgeItem] = []
    for s in srcs:
        items.extend(s.collect(path))
    if not items:
        return None

    course_title = title or cc._course_title(path)
    modules = _modules(items, path, course_title)

    files = package_files(items, course_title)  # raises on a file collision — before any I/O
    files["course_settings/module_meta.xml"] = _module_meta(modules, course_title)
    files["imsmanifest.xml"] = _manifest(items, modules, course_title)

    p = Path(path)
    if out_path is None:
        base = p if p.is_dir() else p.parent
        out_path = base / "course.imscc"
    out_path = Path(out_path)
    if out_path.suffix != ".imscc":
        out_path = out_path.with_suffix(".imscc")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, data in files.items():
            z.writestr(arc, data)
    return out_path
