import xml.etree.ElementTree as ET
import zipfile
import pytest
from coursekit.generate.quiz import bank as bankmod
from coursekit.emit import qti
from coursekit.generate.quiz.bank import Bank


def liter(root, name):
    return [e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == name]


def _mc_bank(run_id="run", n_groups=3):
    """A finalizable all-MC bank + its quiz dict."""
    bankmod.init(run_id, None, title="Week 3: Loops", source="week-3.md")
    for c in range(1, n_groups + 1):
        gid = f"c{c}"
        bankmod.create_group(gid, f"Concept {c}", "multiple_choice")
        for i, lbl in enumerate("ABCD"):
            bankmod.put_variant(bankmod.MCVariant(
                group_id=gid, label=lbl, variant_summary=f"{gid} angle {lbl}",
                question_text=f"Question {gid}{lbl}: what is `x < {i}`?", text_format="markdown",
                options=["one", "two", "three", "four"], correct_index=i))
    b = bankmod.get()
    quiz = bankmod.pick_quiz(seed=1)
    return b, quiz


@pytest.fixture(autouse=True)
def clean():
    bankmod.reset()


# ---------------------------------------------------- well-formedness

def test_every_package_file_is_well_formed():
    b, quiz = _mc_bank()
    for arc, data in qti.package_files(b, quiz).items():
        ET.fromstring(data)  # raises on malformed


def test_package_has_the_qti_quiz_export_tree():
    b, quiz = _mc_bank(n_groups=3)
    q = qti.quiz_ident(b.run_id)
    arcs = set(qti.package_files(b, quiz))
    # QTI Quiz Export layout: inline questions in <q>/<q>.xml, meta beside it. No CC stub,
    # no non_cc_assessments — those were what imported empty / landed in Files.
    assert arcs == {
        "imsmanifest.xml",
        f"{q}/{q}.xml",
        f"{q}/assessment_meta.xml",
    }
    assert not any(a.startswith("non_cc_assessments/") for a in arcs)


# ---------------------------------------------------- namespace exactness

def test_namespaces_and_resource_type_match_the_sample():
    b, quiz = _mc_bank()
    files = qti.package_files(b, quiz)
    q = qti.quiz_ident(b.run_id)

    # inline questions file, plain QTI namespace
    assert 'xmlns="http://www.imsglobal.org/xsd/ims_qtiasiv1p2"' in files[f"{q}/{q}.xml"]
    # meta uses the correct XMLSchema-instance xmlns:xsi (not the malformed course-export one)
    assert 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"' in files[f"{q}/assessment_meta.xml"]
    assert 'xmlns="http://canvas.instructure.com/xsd/cccv1p0"' in files[f"{q}/assessment_meta.xml"]
    # manifest: the plain imsqti_xmlv1p2 resource type + empty organizations
    manifest = files["imsmanifest.xml"]
    assert 'type="imsqti_xmlv1p2"' in manifest
    assert "imsqti_xmlv1p2/imscc_xmlv1p1/assessment" not in manifest  # not the course-export type
    assert "<organizations/>" in manifest
    assert f'<file href="{q}/{q}.xml"/>' in manifest


# ---------------------------------------------------- reference integrity

def test_assessment_has_a_question_group_per_concept_with_items_inline():
    b, quiz = _mc_bank(n_groups=4)
    assessment = ET.fromstring(qti.emit_assessment(b, quiz))
    root = [s for s in liter(assessment, "section") if s.get("ident") == "root_section"][0]
    groups = [c for c in root if c.tag.rsplit("}", 1)[-1] == "section"]
    assert len(groups) == 4                      # one question group per concept
    for g in groups:
        items = [c for c in g if c.tag.rsplit("}", 1)[-1] == "item"]
        assert len(items) == 4                   # its four variants, inline
        assert liter(g, "selection_number")      # and a group selection
    # No sourcebank_ref anywhere: nothing points at a separate bank file.
    assert not liter(assessment, "sourcebank_ref")


def test_manifest_hrefs_all_exist_in_the_package():
    b, quiz = _mc_bank()
    files = qti.package_files(b, quiz)
    manifest = ET.fromstring(files["imsmanifest.xml"])
    hrefs = {f.get("href") for f in liter(manifest, "file")}
    assert hrefs <= set(files), f"dangling hrefs: {hrefs - set(files)}"


def test_manifest_dependencies_match_a_resource():
    b, quiz = _mc_bank()
    manifest = ET.fromstring(qti.emit_manifest(b, quiz))
    resource_ids = {r.get("identifier") for r in liter(manifest, "resource")}
    deps = {d.get("identifierref") for d in liter(manifest, "dependency")}
    assert deps and deps <= resource_ids


def test_selection_number_within_group_size():
    b, quiz = _mc_bank()
    assessment = ET.fromstring(qti.emit_assessment(b, quiz))
    root = [s for s in liter(assessment, "section") if s.get("ident") == "root_section"][0]
    for g in [c for c in root if c.tag.rsplit("}", 1)[-1] == "section"]:
        n = int(liter(g, "selection_number")[0].text)
        items = len([c for c in g if c.tag.rsplit("}", 1)[-1] == "item"])
        assert 1 <= n <= items  # can't draw more than the group holds


def test_points_possible_equals_group_count():
    b, quiz = _mc_bank(n_groups=5)
    meta = ET.fromstring(qti.emit_assessment_meta(b, quiz))
    top_points = [e for e in liter(meta, "points_possible")][0]
    assert top_points.text == "5.0"


# ---------------------------------------------------- zip integrity

def test_imscc_is_a_valid_zip_with_manifest_at_root(tmp_path):
    b, quiz = _mc_bank()
    out = qti.write_imscc(b, quiz, tmp_path / "week-3")
    assert out.suffix == ".zip"
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        names = z.namelist()
        assert "imsmanifest.xml" in names
        assert all(z.getinfo(n).compress_type == zipfile.ZIP_DEFLATED for n in names)


def test_written_package_round_trips_through_the_zip(tmp_path):
    b, quiz = _mc_bank()
    out = qti.write_imscc(b, quiz, tmp_path / "week-3")
    with zipfile.ZipFile(out) as z:
        for name in z.namelist():
            ET.fromstring(z.read(name))  # every entry parses


# ---------------------------------------------------- determinism

def test_same_bank_yields_identical_package():
    b1, q1 = _mc_bank(run_id="fixed")
    files1 = qti.package_files(b1, q1)
    bankmod.reset()
    b2, q2 = _mc_bank(run_id="fixed")
    files2 = qti.package_files(b2, q2)
    assert files1 == files2  # deterministic ids -> byte-identical, so re-import updates


# ---------------------------------------------------- re-emit from bank.json

def test_reemit_writes_imscc_beside_an_mc_bank(tmp_path):
    b, quiz = _mc_bank()
    wk = tmp_path / "week-3"
    wk.mkdir()
    (wk / "bank.json").write_text(b.model_dump_json(), encoding="utf-8")
    import json
    (wk / "quiz.json").write_text(json.dumps(quiz), encoding="utf-8")

    results = qti.reemit(tmp_path)
    assert len(results) == 1
    bank_json, imscc, reason = results[0]
    assert reason is None
    assert imscc == wk / "week-3.zip"
    assert imscc.exists()


def test_reemit_synthesises_quiz_when_quiz_json_missing(tmp_path):
    b, _ = _mc_bank()
    wk = tmp_path / "week-3"
    wk.mkdir()
    (wk / "bank.json").write_text(b.model_dump_json(), encoding="utf-8")
    # no quiz.json
    _, imscc, reason = qti.reemit(tmp_path)[0]
    assert reason is None and imscc.exists()


def test_reemit_skips_a_bank_with_an_empty_group(tmp_path):
    # a concept the model opened but never filled would ship a silently-short quiz (week 9's c5);
    # emit must skip it with a reason, not package a partial bank
    _mc_bank(n_groups=2)
    bankmod.create_group("c3", "Unfinished concept", "multiple_choice")   # opened, no variants
    wk = tmp_path / "week-9"
    wk.mkdir()
    (wk / "bank.json").write_text(bankmod.get().model_dump_json(), encoding="utf-8")

    bank_json, imscc, reason = qti.reemit(tmp_path)[0]
    assert imscc is None
    assert "c3" in reason and "no variants" in reason
    assert not (wk / "week-9.zip").exists()   # nothing written for the broken bank


def test_bundle_skips_the_incomplete_bank_but_keeps_the_rest(tmp_path):
    good, _ = _mc_bank(run_id="good")
    (tmp_path / "week-3").mkdir()
    (tmp_path / "week-3" / "bank.json").write_text(good.model_dump_json(), encoding="utf-8")
    _mc_bank(run_id="bad", n_groups=2)
    bankmod.create_group("c3", "Unfinished", "multiple_choice")
    (tmp_path / "week-9").mkdir()
    (tmp_path / "week-9" / "bank.json").write_text(bankmod.get().model_dump_json(), encoding="utf-8")

    out, included, skipped = qti.bundle(tmp_path)
    assert out is not None and len(included) == 1        # the good week bundled
    assert any("c3" in reason for _, reason in skipped)  # the broken one reported


def test_reemit_skips_unsupported_types_without_aborting(tmp_path, monkeypatch):
    # Every modelled type emits now, so simulate an unsupported one to exercise the skip path.
    def _unsupported(v, run_id):
        raise NotImplementedError("QTI emit for 'numerical' is not supported here")
    monkeypatch.setitem(qti._ITEM_EMITTERS, "numerical", _unsupported)

    bankmod.reset()
    mc, mcq = _mc_bank(run_id="mc")
    (tmp_path / "week-3").mkdir()
    (tmp_path / "week-3" / "bank.json").write_text(mc.model_dump_json(), encoding="utf-8")

    bankmod.reset()
    bankmod.init("mx", None, title="Numerical week")
    bankmod.create_group("c1", "Counts", "numerical")
    for lbl, a in zip("ABCD", [3, 4, 5, 6]):
        bankmod.put_variant(bankmod.NumVariant(
            group_id="c1", label=lbl, variant_summary=f"Count {lbl}",
            question_text="How many sides does the shape have?", answer=a))
    (tmp_path / "week-4").mkdir()
    (tmp_path / "week-4" / "bank.json").write_text(bankmod.get().model_dump_json(), encoding="utf-8")

    results = {bj.parent.name: (imscc, reason) for bj, imscc, reason in qti.reemit(tmp_path)}
    assert results["week-3"][0] is not None          # MC emitted
    assert results["week-4"][0] is None               # numerical skipped
    assert "numerical" in results["week-4"][1]
    assert not (tmp_path / "week-4" / "week-4.zip").exists()  # no partial file


# ---------------------------------------------------- multi-quiz bundle

def _write_week(tmp_path, name, run_id, n_groups=2):
    bankmod.reset()
    b, quiz = _mc_bank(run_id=run_id, n_groups=n_groups)
    wk = tmp_path / name
    wk.mkdir()
    (wk / "bank.json").write_text(b.model_dump_json(), encoding="utf-8")
    import json
    (wk / "quiz.json").write_text(json.dumps(quiz), encoding="utf-8")
    return wk


def test_bundle_puts_every_quiz_in_one_package(tmp_path):
    _write_week(tmp_path, "week-3", "r3")
    _write_week(tmp_path, "week-4", "r4")
    _write_week(tmp_path, "week-5", "r5")

    out, included, skipped = qti.bundle(tmp_path)
    assert skipped == []
    assert len(included) == 3
    assert out == tmp_path / "all-quizzes.zip"

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert names.count("imsmanifest.xml") == 1          # exactly one manifest
        manifest = ET.fromstring(z.read("imsmanifest.xml"))
        quiz_res = [r for r in liter(manifest, "resource")
                    if r.get("type") == "imsqti_xmlv1p2"]
        assert len(quiz_res) == 3                            # three quizzes declared
        # every declared href is present in the zip
        hrefs = {f.get("href") for f in liter(manifest, "file")}
        assert hrefs <= set(names)
        # and every entry parses
        for n in names:
            ET.fromstring(z.read(n))


def test_bundle_quizzes_keep_separate_folders_and_ids(tmp_path):
    _write_week(tmp_path, "week-3", "r3")
    _write_week(tmp_path, "week-4", "r4")
    out, _, _ = qti.bundle(tmp_path)
    with zipfile.ZipFile(out) as z:
        folders = {n.split("/")[0] for n in z.namelist() if "/" in n}
    assert len(folders) == 2  # one folder per quiz, no collision


def test_bundle_skips_unsupported_without_losing_the_rest(tmp_path, monkeypatch):
    def _unsupported(v, run_id):
        raise NotImplementedError("QTI emit for 'numerical' is not supported here")
    monkeypatch.setitem(qti._ITEM_EMITTERS, "numerical", _unsupported)
    _write_week(tmp_path, "week-3", "r3")
    bankmod.reset()
    bankmod.init("rnum", None, title="Numerical week")
    bankmod.create_group("c1", "Counts", "numerical")
    for lbl, a in zip("ABCD", [3, 4, 5, 6]):
        bankmod.put_variant(bankmod.NumVariant(
            group_id="c1", label=lbl, variant_summary=f"Count {lbl}",
            question_text="How many sides does the shape have?", answer=a))
    wk = tmp_path / "week-4"
    wk.mkdir()
    (wk / "bank.json").write_text(bankmod.get().model_dump_json(), encoding="utf-8")

    out, included, skipped = qti.bundle(tmp_path)
    assert len(included) == 1 and len(skipped) == 1
    assert "numerical" in skipped[0][1]
    assert out.exists()


def test_bundle_returns_none_when_nothing_usable(tmp_path):
    out, included, skipped = qti.bundle(tmp_path)
    assert out is None and included == []
