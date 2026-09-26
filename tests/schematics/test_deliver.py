"""Taking in a pile somebody gathered by hand: what is kept, what is refused, and what it is keyed on."""
from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from parts_index.core import config
from parts_index.core.ledger import Ledger
from parts_index.schematics import deliver as D

REGISTRY = """
handover: {kind: delivery, title: By hand, home_url: 'https://forum.example/', status: active,
           delivery: {role: schematic,
                      link: [{match: '^threads/([^/]+)/', url: 'https://forum.example/threads/{1}/'}]}}
elsewhere: {kind: site, title: Elsewhere, home_url: 'https://e.org/', status: active}
"""
PDF = b"%PDF-1.4\n" + b"x" * 3000
GIF = b"GIF89a" + b"x" * 3000
ERROR_PAGE = b"<html><head><title>Error 404 Not Found</title></head><body>gone</body></html>"
GERBER = b"G04 a gerber file*\n%FSLAX46Y46*%\n"


def zipped(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in members.items():
            z.writestr(name, body)
    return buf.getvalue()


@pytest.fixture
def delivery(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "schematics").mkdir(parents=True)
    (data / "schematics" / "sources.yaml").write_text(REGISTRY, encoding="utf-8")
    monkeypatch.setattr(config, "PUBLIC_DATA", data)
    monkeypatch.setenv("PIDX_MATERIAL", str(tmp_path / "material"))
    inner = zipped({"board/top.gbr": GERBER})
    archive = zipped({
        "The Pile/threads/aleph-j/aleph.pdf": PDF,
        "The Pile/threads/aleph-j/layout.gif": GIF,
        "The Pile/recovered/missing.pdf": ERROR_PAGE,
        "The Pile/threads/gerbers/boards.zip": inner,
    })
    path = config.downloads("handover")
    path.mkdir(parents=True)
    (path / "pile.zip").write_bytes(archive)
    return path / "pile.zip"


def led() -> Ledger:
    return Ledger(config.schematics_state("handover"))


def test_each_file_is_keyed_on_where_it_sat_in_the_pile(delivery):
    D.deliver("handover", delivery, log=lambda *a: None)
    rows = led().rows

    assert "delivery:threads/aleph-j/aleph.pdf" in rows          # the packer's own top folder is dropped
    assert rows["delivery:threads/aleph-j/aleph.pdf"]["sha256"] == hashlib.sha256(PDF).hexdigest()
    stored = config.downloads("handover") / "pdf" / D.safe_name("delivery:threads/aleph-j/aleph.pdf", "pdf")
    assert stored.read_bytes() == PDF


def test_the_folder_it_sat_in_gives_it_a_public_link(delivery):
    D.deliver("handover", delivery, log=lambda *a: None)
    assert led().get("delivery:threads/aleph-j/aleph.pdf")["url"] == "https://forum.example/threads/aleph-j/"
    assert led().get("delivery:recovered/missing.pdf")["url"] == ""      # no rule matches: no link to offer


def test_a_saved_error_page_is_not_a_document(delivery):
    D.deliver("handover", delivery, log=lambda *a: None)
    assert led().get("delivery:recovered/missing.pdf")["skip_reason"] == "not the declared file type"


def test_an_archive_inside_the_archive_is_opened(delivery):
    D.deliver("handover", delivery, log=lambda *a: None)
    rows = led().rows
    assert rows["delivery:threads/gerbers/boards.zip!board/top.gbr"]["skip_reason"] == "not a document"
    assert rows["delivery:threads/gerbers/boards.zip"]["type"] == "zip"


def test_a_file_nothing_reads_is_still_kept(delivery):
    """A delivery cannot be fetched again and the archive goes, so the bytes stay whatever they are."""
    D.deliver("handover", delivery, log=lambda *a: None)

    board = config.downloads("handover") / "other" / D.safe_name("delivery:threads/gerbers/boards.zip!board/top.gbr", "other")
    assert board.read_bytes() == GERBER                      # refused by the reading stages, kept on disk
    inner = config.downloads("handover") / "zip" / D.safe_name("delivery:threads/gerbers/boards.zip", "zip")
    assert inner.exists()                                    # and so is the archive it came in
    page = config.downloads("handover") / "html" / D.safe_name("delivery:recovered/missing.pdf", "html")
    assert page.read_bytes() == ERROR_PAGE


def test_a_file_another_source_already_holds_is_recorded_as_the_duplicate_it_is(delivery):
    other = Ledger(config.schematics_state("elsewhere"))
    other.stamp("https://e.org/aleph.pdf", "download", type="pdf", sha256=hashlib.sha256(PDF).hexdigest())
    other.save()

    D.deliver("handover", delivery, log=lambda *a: None)
    row = led().get("delivery:threads/aleph-j/aleph.pdf")
    assert row["skip_reason"] == "same file as elsewhere: https://e.org/aleph.pdf"
    stored = config.downloads("handover") / "pdf" / D.safe_name("delivery:threads/aleph-j/aleph.pdf", "pdf")
    assert not stored.exists()          # the other source has it, and that one can be fetched again


def test_what_arrived_is_itself_a_row_and_can_be_removed_afterwards(delivery):
    D.deliver("handover", delivery, remove=True, log=lambda *a: None)
    row = led().get("delivery:pile.zip")
    assert row["role"] == "archive" and row["sha256"] and "unpacked" in row["skip_reason"]
    assert not delivery.exists()


def test_a_source_without_a_delivery_block_is_refused(delivery):
    with pytest.raises(SystemExit, match="delivery"):
        D.deliver("elsewhere", delivery, log=lambda *a: None)


def test_taking_the_same_pile_in_twice_says_the_same_thing(delivery):
    """What a file is does not depend on what else the pile holds, so two runs must agree."""
    first = D.deliver("handover", delivery, log=lambda *a: None)
    reasons = {k: r["skip_reason"] for k, r in led().rows.items()}

    second = D.deliver("handover", delivery, log=lambda *a: None)
    assert {k: r["skip_reason"] for k, r in led().rows.items()} == reasons
    assert first == second


def test_a_delivery_taken_in_again_after_a_reader_arrived_is_classified_afresh(delivery):
    """What was 'not a document' yesterday is a document once something reads it; the old reason goes."""
    netlist = b"* source CE3\nQ_Q1 N1 N2 N3 QC1815\nR_R1 N1 N4 1k\n"
    again = delivery.parent / "again.zip"
    again.write_bytes(zipped({"pack/threads/ce3/ce3.net": netlist}))
    D.deliver("handover", again, log=lambda *a: None)
    ledger = led()
    key = "delivery:threads/ce3/ce3.net"
    ledger.row(key)["skip_reason"] = "not a document"            # what an older reader left behind
    ledger.save()
    D.deliver("handover", again, log=lambda *a: None)
    row = led().get(key)
    assert (row["type"], row["skip_reason"]) == ("spice_net", "")
