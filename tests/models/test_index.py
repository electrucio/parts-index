"""Finding definitions in whatever a vendor calls its file."""
import json

import pytest

from parts_index.models import index as ix

NPN = """* ON Semiconductor
.MODEL Q2N3904 NPN (IS=1E-14 BF=300 VAF=100 MFG=ON)
.model D1N4148 D (Is=2.52n Rs=.568 N=1.752)
"""
SUB = """.SUBCKT TL072 1 2 3 4 5 PARAMS: gain=100k
.model dx D(Is=1e-14)
.ENDS
"""


def write(tmp_path, name, text, source="acme"):
    p = tmp_path / "sources" / source / "raw" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_finds_models_and_keeps_the_interesting_parameters(tmp_path):
    p = write(tmp_path, "q.lib", NPN)
    recs = ix.scan_file(p, "sources/acme/raw/q.lib", "acme")
    assert [r["name"] for r in recs] == ["Q2N3904", "D1N4148"]
    q = recs[0]
    assert q["kind"] == "model" and q["type"] == "NPN" and q["mfg"] == "ON"
    assert q["params"]["bf"] == "300" and "mfg" not in q["params"]
    assert q["comment"] == "ON Semiconductor"


def test_a_subckt_records_its_pins_and_what_it_contains(tmp_path):
    p = write(tmp_path, "op.sub", SUB)
    recs = ix.scan_file(p, "sources/acme/raw/op.sub", "acme")
    assert recs[0]["pins"] == ["1", "2", "3", "4", "5"] and recs[0]["params"]["gain"] == "100k"
    assert recs[1]["parent"] == "TL072"          # the diode inside belongs to the subcircuit


@pytest.mark.parametrize("name", ["v.dio", "v.mos", "v.bjt", "v.jft", "v.prm", "v.301", "vendorfile"])
def test_any_extension_a_vendor_invents(tmp_path, name):
    """The scanner filters by what certainly is not a model. An allow-list once cost 59,407 definitions."""
    p = write(tmp_path, name, NPN)
    assert len(ix.scan_file(p, f"sources/acme/raw/{name}", "acme")) == 2
    assert p in set(ix.iter_files(tmp_path / "sources" / "acme"))


@pytest.mark.parametrize("name", ["datasheet.pdf", "shot.png", "bundle.zip", "sym.asy", "page.html"])
def test_and_skips_what_never_holds_one(tmp_path, name):
    p = write(tmp_path, name, NPN)
    assert p not in set(ix.iter_files(tmp_path / "sources" / "acme"))


def test_continuation_lines_are_joined(tmp_path):
    p = write(tmp_path, "c.lib", ".model M NPN (IS=1E-14\n+ BF=250\n+ VAF=75)\n")
    rec = ix.scan_file(p, "sources/acme/raw/c.lib", "acme")[0]
    assert rec["params"]["bf"] == "250" and rec["params"]["vaf"] == "75"


def test_binary_and_oversized_files_are_left_alone(tmp_path):
    p = tmp_path / "sources" / "acme" / "raw" / "x.lib"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"PK\x03\x04" + b"\x00" * 500)
    assert ix.scan_file(p, "sources/acme/raw/x.lib", "acme") == []


def test_an_encrypted_file_still_says_the_part_has_a_model(tmp_path):
    p = write(tmp_path, "2SK209_LTspice.lib", "* LTspice encrypted file\n\x01\x02binary-ish\n")
    rec = ix.scan_file(p, "sources/acme/raw/2SK209_LTspice.lib", "acme")[0]
    assert rec["name"] == "2SK209" and rec["encrypted"] and rec["enc_kind"] == "ltspice"


def test_utf16_is_read(tmp_path):
    p = tmp_path / "sources" / "acme" / "raw" / "u.lib"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(NPN.encode("utf-16-le"))
    assert len(ix.scan_file(p, "sources/acme/raw/u.lib", "acme")) == 2


def test_scanning_a_tree_names_each_source(tmp_path):
    write(tmp_path, "a.lib", NPN, source="acme")
    write(tmp_path, "b.301", SUB, source="other")
    recs, n_files = ix.scan(tmp_path / "sources")
    assert n_files == 2 and {r["source"] for r in recs} == {"acme", "other"}
    assert {r["file"] for r in recs} == {"sources/acme/raw/a.lib", "sources/other/raw/b.301"}


def test_an_unpacked_archive_counts_towards_the_archive(tmp_path):
    assert ix.manifest_key("sources/ti/extracted/sloj070/TL082.lib") == ("ti", "stem:sloj070")
    assert ix.manifest_key("sources/ti/raw/sloj070.zip") == ("ti", "raw/sloj070.zip")


def test_missing_lists_what_a_previous_catalogue_had(tmp_path):
    write(tmp_path, "kept.lib", NPN)
    ref = tmp_path / "old.jsonl"
    ref.write_text("\n".join(json.dumps({"file": f, "source": "acme"}) for f in
                             ["sources/acme/raw/kept.lib", "sources/acme/raw/gone.dio",
                              "sources/acme/raw/gone.dio", "sources/acme/extracted/x/gone.mos"]) + "\n")
    gone = ix.missing(ref, tmp_path / "sources")
    assert [(g["file"], g["definitions"]) for g in gone] == [
        ("sources/acme/extracted/x/gone.mos", 1), ("sources/acme/raw/gone.dio", 2)]
