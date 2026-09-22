"""Taking in a delivery gathered by hand: the files, and what was looked for and not found."""
import csv

import pytest

from parts_index.core import config
from parts_index.models import ingest as I

LOG = """source_id,pieza,fichero,url_descarga,url_pagina,fecha,estado,notas
tubes,6SF5,6SF5_koren.lib,https://v.example/6SF5_koren.lib,https://v.example/thread,2026-09-20,encontrado,de un hilo
tubes,6Y6GA,coleccion.lib,https://v.example/coleccion.lib,,2026-09-20,encontrado,la coleccion entera
tubes,6BW6,coleccion.lib,https://v.example/coleccion.lib,,2026-09-20,encontrado,la misma coleccion
tubes,35Z5,N/A - no publicado,N/A,,2026-09-20,no_publicado,nadie lo ha publicado nunca
tubes,EL84,,,https://v.example/search?q=EL84,2026-09-20,parcial,solo cosas no prioritarias
tubes,ECC83 snippet,visto en el hilo,https://v.example/post/9 ; https://v.example/post/10,,2026-09-20,encontrado_parcial,solo fragmento
"""


@pytest.fixture()
def delivery(tmp_path):
    root = tmp_path / "round"
    (root / "tubes").mkdir(parents=True)
    (root / "tubes" / "6SF5_koren.lib").write_text(".model X NPN(IS=1e-14)\n")
    (root / "tubes" / "coleccion.lib").write_text(".SUBCKT A 1 2\n.ENDS\n")
    (root / "tubes" / "README.txt").write_text("notes about the round")
    (root / "descargas.csv").write_text(LOG, encoding="utf-8")
    (root / "INFORME.md").write_text("# the report, naming a person and in another language")
    return root


@pytest.fixture()
def trees(tmp_path, monkeypatch):
    monkeypatch.setenv("PIDX_SPICE_MODELS", str(tmp_path / "models"))
    monkeypatch.setattr(config, "model_state", lambda s: tmp_path / "state" / f"{s}.csv")
    monkeypatch.setattr(config, "model_sources", lambda s=None: (tmp_path / "reg" / f"{s}.yaml") if s else tmp_path / "reg")
    for m in (I, __import__("parts_index.models.fetch", fromlist=["x"])):
        for n in ("model_state", "model_sources"):
            if hasattr(m, n):
                monkeypatch.setattr(m, n, getattr(config, n))
    (tmp_path / "reg").mkdir()
    return tmp_path


def rows(path):
    return list(csv.DictReader(open(path, encoding="utf-8")))


@pytest.mark.parametrize("value,want", [
    ("https://v.example/a.lib", "https://v.example/a.lib"),
    ("N/A", ""), ("", ""), ("no publicado", ""),
    ("https://a.example/1 ; https://b.example/2", "https://a.example/1"),
    ("https://a.example/1 + extra", "https://a.example/1"),
])
def test_only_something_you_can_open_counts_as_a_url(value, want):
    assert I.real_url(value) == want


@pytest.mark.parametrize("piece,want", [
    ("6SF5", "6SF5"), ("BC114, BC148, BC153", "BC114"),
    ("MP20 (posible pieza sovietica)", "MP20"), ("(coleccion/autor) andy_c", "(coleccion/autor) andy_c"),
])
def test_a_piece_is_named_not_described(piece, want):
    assert I.piece_name(piece) == want


def test_files_arrive_with_their_provenance(delivery, trees):
    counts = I.ingest(delivery)
    assert counts["files"] == 3 and counts["into:tubes"] == 3
    kept = trees / "models/sources/tubes/raw/6SF5_koren.lib"
    assert kept.read_text().startswith(".model")
    from parts_index.models.fetch import Manifest
    assert Manifest("tubes").by_url("https://v.example/6SF5_koren.lib")["path"] == "raw/6SF5_koren.lib"


def test_one_collection_can_answer_several_pieces(delivery, trees):
    """Two rows name the same file. Both were satisfied; neither should look unfulfilled."""
    counts = I.ingest(delivery)
    assert "outcome:downloaded" not in counts and "outcome:listed" in counts


def test_what_was_not_found_is_recorded_so_nobody_looks_again(delivery, trees):
    I.ingest(delivery)
    by_key = {r["key"]: r for r in rows(trees / "state/tubes.csv")}
    assert by_key["part:35Z5"]["status"] == "not_published"      # nothing anywhere: keyed by the piece
    assert by_key["https://v.example/search?q=EL84"]["status"] == "searched"
    assert by_key["https://v.example/post/9"]["status"] == "listed"   # a link, not a file


def test_the_public_ledger_carries_no_prose(delivery, trees):
    I.ingest(delivery)
    text = (trees / "state/tubes.csv").read_text()
    assert "de un hilo" not in text and "nadie lo ha publicado" not in text
    assert all(r["skip_reason"] in ("", "not_published", "searched", "listed")
               for r in rows(trees / "state/tubes.csv"))


def test_the_delivery_keeps_its_own_account_privately(delivery, trees):
    I.ingest(delivery)
    kept = trees / "models/sources/tubes/delivery"
    assert (kept / "descargas.csv").is_file() and (kept / "INFORME.md").is_file()


def test_a_new_source_gets_registered(delivery, trees):
    I.ingest(delivery)
    import yaml
    entry = yaml.safe_load((trees / "reg/tubes.yaml").read_text())
    assert entry["fetch"] == "manual" and entry["redistributable"] is False


def test_a_dry_run_changes_nothing(delivery, trees):
    counts = I.ingest(delivery, dry=True)
    assert counts["files"] == 3
    assert not (trees / "models/sources/tubes").exists() and not (trees / "state").exists()


def test_a_delivery_without_a_log_still_lands(delivery, trees):
    (delivery / "descargas.csv").unlink()
    counts = I.ingest(delivery)
    assert counts["files"] == 3 and counts["into:tubes"] == 3      # the folder names the source


def test_an_archive_is_unpacked_so_the_indexer_can_see_inside_it(tmp_path, trees):
    """A delivery of zips is a delivery of nothing until they are opened.

    The indexer walks files, not zip members, so a vendor collection that arrives compressed lands with
    every model inside it invisible -- which is how a source can show a full ledger and no definitions.
    """
    import zipfile
    root = tmp_path / "round2"
    (root / "vendor").mkdir(parents=True)
    with zipfile.ZipFile(root / "vendor" / "pack.zip", "w") as z:
        z.writestr("inner/PART1.lib", ".model PART1 D(IS=1e-14)\n")
        z.writestr("inner/PART2.lib", ".SUBCKT PART2 1 2\n.ENDS\n")
    (root / "log.csv").write_text(
        "source_id,pieza,fichero,url_descarga,url_pagina,fecha,estado,notas\n"
        "vendor,PART1,pack.zip,https://v.example/pack.zip,,2026-09-21,encontrado,la coleccion\n",
        encoding="utf-8")

    counts = I.ingest(root)

    assert counts["unpacked"] == 2
    out = trees / "models/sources/vendor/extracted/pack/inner"
    assert (out / "PART1.lib").read_text().startswith(".model")
    assert (out / "PART2.lib").read_text().startswith(".SUBCKT")


def test_a_part_whose_file_arrived_is_no_longer_waiting_to_be_looked_for(delivery, trees):
    """The file's row is not the whole story: the part has a row of its own.

    Leaving it at not_tried makes the ledger say both "we hold this model" and "nobody has looked",
    and the second is what decides whether the search is run again.
    """
    I.ingest(delivery)
    by_key = {r["key"]: r for r in rows(trees / "state/tubes.csv")}
    assert by_key["part:6SF5"]["status"] == "downloaded"
    assert by_key["part:6SF5"]["skip_reason"] == ""
    assert by_key["part:6Y6GA"]["status"] == "downloaded"      # answered by a shared collection
    assert by_key["part:6BW6"]["status"] == "downloaded"       # and so was this one
