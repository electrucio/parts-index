"""How one part's matches become its distinct models, and where each copy is said to come from."""
from __future__ import annotations

import json

from parts_index.models import found as F

LIB = """* a vendor library
.model Q2N3904 NPN(IS=1E-14 BF=300)
.subckt AMP1 1 2 3
Q1 1 2 3 QINNER
.ends
.model QINNER NPN(IS=2E-14
+ BF=100)
"""


def test_a_subcircuit_brings_what_it_references_first():
    defs = F.blocks(LIB)
    assert [nm for _, nm, _ in F.closure(defs, "amp1")] == ["QINNER", "AMP1"]
    assert F.spans(LIB)["qinner"] == (6, 7)


def h(text: str, name: str) -> str:
    return F.code_hash(F.closure(F.blocks(text), name))


def test_copies_that_differ_only_in_comments_case_and_spacing_are_one_model():
    a = "* from the vendor\n.model Q1 NPN(IS=1E-14  BF=300) ; typical\n"
    b = ".MODEL q1 npn(is=1e-14 bf=300)\n"
    assert h(a, "Q1") == h(b, "q1")
    assert h(a, "Q1") != h(".model Q1 NPN(IS=1E-14 BF=301)\n", "Q1")


def test_a_copy_that_only_renamed_the_model_is_the_same_model():
    assert h(".model Q2N3904 NPN(IS=1E-14 BF=300)\n", "Q2N3904") == h(".model 2N3904 NPN(IS=1E-14 BF=300)\n", "2N3904")
    sub = ".subckt {n} C B E\nQ1 C B E {m}\n.ends\n.model {m} NPN(BF=50)\n"
    assert h(sub.format(n="TIP31", m="QT"), "TIP31") == h(sub.format(n="XTIP31", m="QINNER"), "XTIP31")


def test_a_model_rewritten_with_its_parameters_sorted_and_defaults_dropped_is_the_same_model():
    """Bordodynov's MJ15001M is Motorola's 1997 Qmj15001, sorted, on one line, without CJS=0 PTF=0 KF=0 AF=1."""
    motorola = ".MODEL Qmj15001 npn\n+IS=1.23312e-13 BF=115.914 VAF=10\n+CJS=0 PTF=0 KF=0 AF=1\n"
    bordodynov = ".MODEL MJ15001M NPN (BF=115.914 IS=1.23312E-13 VAF=10)\n"
    assert h(motorola, "Qmj15001") == h(bordodynov, "MJ15001M")
    assert h(".model D1 D(IS=1.2n)\n", "D1") == h(".model D1 D(IS=1.2E-9)\n", "D1")
    assert h(motorola, "Qmj15001") != h(bordodynov.replace("VAF=10", "VAF=11"), "MJ15001M")
    assert h(".model Q1 PNP(BF=100)\n", "Q1") != h(".model Q1 NPN(BF=100)\n", "Q1")


def tree(tmp_path, files: dict[str, str], manifest: dict[str, dict] | None = None):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    for source, man in (manifest or {}).items():
        (tmp_path / "sources" / source / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    return tmp_path


def cand(source, file, name="Q2N3904", match="exact"):
    return {"source": source, "file": file, "name": name, "kind": "model", "type": "NPN", "pins": [],
            "match": match, "encrypted": False, "mfg": None}


def test_the_same_code_in_several_sources_is_credited_to_the_most_original(tmp_path):
    same = ".model Q2N3904 NPN(IS=1E-14 BF=300)\n"
    root = tree(tmp_path, {"sources/kicad-spice-library/raw/a.lib": same,
                           "sources/onsemi/raw/2N3904.LIB": "* onsemi\n" + same,
                           "sources/bordodynov/raw/b.lib": ".model Q2N3904 NPN(IS=1E-14 BF=200)\n"})
    entry = {"candidates": [cand("kicad-spice-library", "sources/kicad-spice-library/raw/a.lib"),
                            cand("onsemi", "sources/onsemi/raw/2N3904.LIB"),
                            cand("bordodynov", "sources/bordodynov/raw/b.lib")]}
    groups, n = F.groups_for(entry, F.Files(root))
    assert n == 2
    assert [(g["best"]["source"], len(g["members"])) for g in groups] == [("onsemi", 2), ("bordodynov", 1)]


def test_a_grade_match_is_dropped_when_the_part_has_a_model_of_its_own(tmp_path):
    root = tree(tmp_path, {"sources/acme/raw/a.lib": ".model BC549C NPN(BF=500)\n.model BC549 NPN(BF=300)\n"})
    entry = {"candidates": [cand("acme", "sources/acme/raw/a.lib", "BC549C"),
                            cand("acme", "sources/acme/raw/a.lib", "BC549", "grade")]}
    groups, _ = F.groups_for(entry, F.Files(root))
    assert [g["best"]["name"] for g in groups] == ["BC549C"]


def test_another_simulators_syntax_is_never_a_candidate(tmp_path):
    root = tree(tmp_path, {"sources/ayumi/extracted/simetrix/t.lib": ".subckt 12AX7 P G K\n.ends\n"})
    entry = {"candidates": [dict(cand("ayumi", "sources/ayumi/extracted/simetrix/t.lib", "12AX7"), kind="subckt")]}
    assert F.groups_for(entry, F.Files(root)) == ([], 0)


def test_a_model_read_out_of_an_archive_is_had_from_the_archive(tmp_path):
    root = tree(tmp_path, {"sources/bordodynov/extracted/lib/cmp/standard.bjt": ".model MJ15001M NPN(BF=115)\n"},
                {"bordodynov": {"fetched": "2026-09-14", "files": [
                    {"path": None, "url": "http://bordodynov.ltwiki.org/lib.zip", "sha256": "ab" * 32}]}})
    prov = F.provenance(root, "sources/bordodynov/extracted/lib/cmp/standard.bjt", "bordodynov", "cd" * 32)
    assert prov["url"] == "http://bordodynov.ltwiki.org/lib.zip"
    assert prov["member"] == "cmp/standard.bjt"
    assert prov["archive"]["sha256"] == "ab" * 32


def test_a_file_listed_in_the_manifest_is_had_from_its_own_url(tmp_path):
    rel = "sources/spice-model-cd/raw/Motorola/Spice/PowerBJT/MJ15001.LIB"
    url = "https://ltwiki.org/files/LTspiceIV/Vendor%20List/Motorola/Spice/PowerBJT/MJ15001.LIB"
    root = tree(tmp_path, {rel: ".model Qmj15001 npn\n"},
                {"spice-model-cd": {"fetched": "2026-09-21",
                                    "files": [{"path": "raw/Motorola/Spice/PowerBJT/MJ15001.LIB", "url": url}]}})
    assert F.provenance(root, rel, "spice-model-cd", "ef" * 32)["url"] == url


def test_a_model_record_names_its_lines_its_dependencies_and_its_copies(tmp_path):
    root = tree(tmp_path, {"sources/acme/raw/a.lib": LIB, "sources/ltwiki/raw/b.lib": LIB})
    entry = {"kind": "ic-audio", "group": "", "priority": 2,
             "candidates": [dict(cand("ltwiki", "sources/ltwiki/raw/b.lib", "AMP1"), kind="subckt"),
                            dict(cand("acme", "sources/acme/raw/a.lib", "AMP1"), kind="subckt")]}
    got = F.find({"AMP1": entry}, root)["AMP1"]
    assert got["distinct"] == 1
    (m,) = got["models"]
    assert (m["source"], m["def"], m["type"], m["deps"]) == ("ltwiki", "subckt", "SUBCKT", ["QINNER"])
    assert m["provenance"]["lines"] == {"QINNER": [6, 7], "AMP1": [3, 5]}
    assert m["copies"] == [{"source": "acme", "file": "sources/acme/raw/a.lib", "name": "AMP1"}]
