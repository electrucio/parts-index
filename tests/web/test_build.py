"""The architectural contract: the site is built from data/ and from nothing else."""
import json

import pytest

from parts_index.core import config
from parts_index.web import build as web_build


def test_builds_without_the_private_data_root(tmp_path, monkeypatch):
    """Sabotage the private root. A clean clone has no corpus, and the build must not care."""
    def explode():
        raise AssertionError("web build touched the private data root")

    monkeypatch.setattr(config, "data_root", explode)
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
