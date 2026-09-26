"""The retention rule: a file whose text was read may go, and one nothing has read may not.

By hand there is no difference between the two, which is the whole reason this exists. A scan deleted
before OCR saw it leaves a ledger still saying "downloaded", so no stage asks for it again and the
document is missing from the index with nobody the wiser.
"""
from __future__ import annotations

import pytest

from parts_index.core import config
from parts_index.core.ledger import Ledger
from parts_index.schematics import release as R
from parts_index.schematics import verify as V
from parts_index.schematics.download import safe_name

REGISTRY = """
audiocircuit: {kind: factory, title: AudioCircuit, home_url: 'https://ac.example/', status: active,
               list: {role: schematic}}
openhw_topics: {kind: site, title: Open hardware, home_url: 'https://gh.example/', status: active,
                list: {role: schematic}}
"""


@pytest.fixture
def site(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "schematics").mkdir(parents=True)
    (data / "schematics" / "sources.yaml").write_text(REGISTRY, encoding="utf-8")
    monkeypatch.setattr(config, "PUBLIC_DATA", data)
    monkeypatch.setenv("PIDX_MATERIAL", str(tmp_path / "material"))
    return data


def held(source: str, key: str, kind: str, size: int = 2000, **stamps):
    """One row the ledger says was downloaded, with its file on disk. `stamps` say who has read it."""
    led = Ledger(config.schematics_state(source))
    led.stamp(key, "download", role="schematic", type=kind, http=200, bytes=size, sha256="x" * 64)
    led.row(key).update(stamps)
    led.dirty = True
    led.save()
    path = config.downloads(source) / kind / safe_name(key, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def test_only_what_something_has_read_may_go(site):
    read = held("audiocircuit", "https://ac.example/a.pdf", "pdf", ocr_at="2026-09-02")
    unread = held("audiocircuit", "https://ac.example/b.pdf", "pdf")

    R.drop(R.look("audiocircuit"))

    assert not read.exists(), "OCR has taken its text; the file is temporary here"
    assert unread.exists(), "nothing has read this one, and deleting it would be a silent hole"


def test_a_born_digital_pdf_counts_as_read_when_the_index_has_it(site):
    """It never goes through OCR, so `ocr_at` stays empty and the index's stamp is the only evidence."""
    born = held("audiocircuit", "https://ac.example/c.pdf", "pdf",
                text_method="text", index_at="2026-09-03")
    assert R.look("audiocircuit")["paths"] == [str(born)]


def test_cad_is_kept_by_default_and_released_only_when_asked(site):
    """A .kicad_sch is a few kilobytes and its reader is the one still changing — gEDA, EAGLE boards and
    the package guard all arrived in one day — so it is the kind most likely to be read again."""
    cad = held("openhw_topics", "https://gh.example/d.kicad_sch", "kicad_sch", size=500,
               ocr_at="2026-09-02")
    assert R.look("openhw_topics")["paths"] == []
    assert R.look("openhw_topics", all_kinds=True)["paths"] == [str(cad)]


def test_how_much_room_it_would_free_is_read_off_the_ledger(site):
    held("audiocircuit", "https://ac.example/a.pdf", "pdf", size=7000, ocr_at="2026-09-02")
    held("audiocircuit", "https://ac.example/b.pdf", "pdf", size=9000)
    assert R.look("audiocircuit")["bytes"] == 7000


def test_the_ledger_is_not_touched_so_nothing_is_asked_for_twice(site):
    held("audiocircuit", "https://ac.example/a.pdf", "pdf", ocr_at="2026-09-02")
    before = config.schematics_state("audiocircuit").read_text(encoding="utf-8")

    R.drop(R.look("audiocircuit"))

    assert config.schematics_state("audiocircuit").read_text(encoding="utf-8") == before


def test_afterwards_verify_calls_them_released_and_not_lost(site):
    """The one thing that must hold: `verify --repair` fetches back what is `lost`, and these are not."""
    held("audiocircuit", "https://ac.example/a.pdf", "pdf", ocr_at="2026-09-02")
    held("audiocircuit", "https://ac.example/b.pdf", "pdf")

    R.drop(R.look("audiocircuit"))

    led = Ledger(config.schematics_state("audiocircuit"))
    states = {k.rsplit("/", 1)[-1]: V.state_of("audiocircuit", r)[0] for k, r in led.rows.items()}
    assert states == {"a.pdf": "released", "b.pdf": "held"}
    assert V.look("audiocircuit")["broken"] == []
