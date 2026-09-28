"""Joining definition files back to the downloads they came from."""
from __future__ import annotations

import json
from collections import Counter

from parts_index.models import index as ix
from parts_index.models import reconcile as R


def test_folder_guesses_follow_how_archives_were_unpacked():
    x = {"url": "u", "path": "raw/pspice-all/PSpice_20260827.zip"}
    rules = R.candidates(x, Counter({"pspice-all": 1}), n_archives=5)
    assert rules[0] == ["extracted/pspice-all/PSpice_20260827", "extracted/PSpice_20260827"]
    assert rules[1] == ["extracted/pspice-all"]
    assert "extracted/win" in R.candidates({"path": "raw/tubemodel_3.20_win.zip"}, Counter(), 3)[1]
    assert R.candidates({"path": "raw/only.zip"}, Counter({"": 1}), 1)[-1] == ["extracted"]


def manifest(tmp_path, monkeypatch, files, sub=None):
    src = tmp_path / "acme"
    (src / (sub or "")).mkdir(parents=True, exist_ok=True)
    (src / (sub or "") / "manifest.json").write_text(json.dumps({"files": files}), encoding="utf-8")
    monkeypatch.setattr(ix, "spice_source_manifest", lambda s: tmp_path / s / "manifest.json")
    monkeypatch.setattr(R, "spice_source", lambda s: tmp_path / s)
    return src


def test_an_archive_is_matched_to_the_one_folder_holding_its_definitions(tmp_path, monkeypatch):
    manifest(tmp_path, monkeypatch, [{"url": "https://a/win.zip", "path": "raw/tubemodel_3.20_win.zip"},
                                     {"url": "https://a/lin.zip", "path": "raw/tubemodel_3.20_linux.zip"}])
    unc = {"extracted/win/12AX7.inc", "extracted/linux/12AX7.inc"}
    got = {x["url"]: into for _, x, into in R.propose("acme", unc)}
    assert got == {"https://a/win.zip": "extracted/win", "https://a/lin.zip": "extracted/linux"}


def test_a_guess_naming_two_folders_is_not_taken(tmp_path, monkeypatch):
    manifest(tmp_path, monkeypatch, [{"url": "https://a/x.zip", "path": "raw/Deluxe_Bassman.zip"},
                                     {"url": "https://a/y.zip", "path": "raw/other.zip"}])
    assert R.propose("acme", {"extracted/Deluxe/a.lib", "extracted/Bassman/b.lib"}) == []


def test_a_sub_manifest_is_read_and_its_missing_rows_are_found(tmp_path, monkeypatch):
    manifest(tmp_path, monkeypatch, [{"url": "https://v/1.zip", "path": "raw/1/sij4108dp.zip", "sha256": "ab"}],
             sub="semis")
    (tmp_path / "acme" / "manifest.json").write_text(json.dumps({"files": []}), encoding="utf-8")

    class Led:
        rows: dict = {}
    assert [x["url"] for x in R.missing_rows("acme", Led())] == ["https://v/1.zip"]
    props = R.propose("acme", {"semis/extracted/sij4108dp/a.lib"})
    assert [(f, into) for f, _, into in props] == [("semis", "extracted/sij4108dp")]
    R.record("acme", props)
    saved = json.loads((tmp_path / "acme" / "semis" / "manifest.json").read_text(encoding="utf-8"))
    assert saved["files"][0]["unpacked_to"] == "extracted/sij4108dp" and saved["files"][0]["sha256"] == "ab"


def test_a_downloaded_file_filed_as_not_published_is_refiled_and_the_part_keeps_its_fact():
    import tempfile
    from pathlib import Path

    from parts_index.core.ledger import MODEL_FIELDS, MODEL_STAGES, MODEL_VERSIONED, Ledger
    led = Ledger(Path(tempfile.mkdtemp()) / "adi.csv", stages=MODEL_STAGES, fields=MODEL_FIELDS, versioned=MODEL_VERSIONED)
    url = "https://www.analog.com/ad8051_5.cir"
    led.skip(url, "not_published", part="AD8052", status="not_published", sha256="ab")
    led.skip("part:AD8052", "", url="https://www.analog.com/ad8052", part="AD8052", status="not_tried")
    R.refile(led, [(url, {"sha256": "ab", "bytes": 2501, "path": "raw/ad8051_5.cir"})])
    assert (led.rows[url]["status"], led.rows[url]["part"]) == ("downloaded", "")
    assert led.rows["part:AD8052"]["status"] == "not_published"
