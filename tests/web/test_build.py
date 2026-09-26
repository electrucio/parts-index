"""The architectural contract: the site is built from data/ and from nothing else."""
import json

import pytest

from parts_index.core import config
from parts_index.web import build as web_build


def test_builds_without_the_private_data_root(tmp_path, monkeypatch):
    """Sabotage the private root. A clean clone has no corpus, and the build must not care."""
    def explode():
        raise AssertionError("web build touched a private tree")

    monkeypatch.setattr(config, "material_root", explode)
    monkeypatch.setattr(config, "spice_models_root", explode)
    monkeypatch.setattr("parts_index.web.build.web_data", lambda: tmp_path)

    manifest = web_build.build()

    assert manifest["schema"] == web_build.SCHEMA
    assert manifest["have"]["sources"] is True
    assert manifest["totals"]["sources"] > 0
    assert (tmp_path / "sources.json").is_file() and (tmp_path / "manifest.json").is_file()


def test_sources_carry_their_coverage(tmp_path):
    web_build.build(tmp_path)
    payload = json.loads((tmp_path / "sources.json").read_text(encoding="utf-8"))
    assert payload["schematics"] and payload["models"]
    row = next(r for r in payload["schematics"] if r["items"])
    assert set(row) == {"source", "kind", "status", "items", "download", "ocr", "index",
                        "linkcheck", "skipped", "last", "next"}
    assert row["index"] <= row["items"]


def test_writes_are_atomic(tmp_path):
    web_build.build(tmp_path)
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("name", ["sources.json", "manifest.json"])
def test_output_is_valid_json(tmp_path, name):
    web_build.build(tmp_path)
    json.loads((tmp_path / name).read_text(encoding="utf-8"))


def test_a_part_with_a_slash_in_its_name_gets_a_directory_not_a_crash(tmp_path):
    """267 published parts carry one — a manufacturer's ordering suffix — and the site asks for
    part/<encodeURIComponent(part)>.json, which a static server decodes into a path with a directory."""
    from parts_index.web.build import write_json
    n = write_json(tmp_path / "part", "ADC121C027CIMK/NOPB.json", {"part": "ADC121C027CIMK/NOPB"})
    assert (tmp_path / "part" / "ADC121C027CIMK" / "NOPB.json").is_file() and n > 0
