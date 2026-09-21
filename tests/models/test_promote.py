"""What may cross from the curated tree into git, and what may not."""
from __future__ import annotations

import json

import pytest
import yaml

from parts_index.models import promote as P

PROV = {
    "source": "acme", "file": "sources/acme/raw/acme.lib",
    "file_sha256": "aa" * 32, "licence": "sources/acme/SOURCE.md",
    "manifest": "sources/acme/manifest.json", "fetched": "2026-09-14",
    "url": "https://acme.example/acme.lib", "note": "commit deadbee",
    "lines": {"Q1": [7, 19]},
}
PART = {
    "part": "Q1", "kind": "bjt", "priority": 1,
    "candidates": [
        {"file": "acme.lib", "source": "acme", "name": "Q1", "def": "model",
         "type": "NPN", "pins": [], "deps": [], "changes": [], "note": "", "provenance": PROV},
        # A rival named in `preferred_why` is always a candidate too: the sentence compares the models
        # this part offers, which is what lets every mention be rewritten as a source.
        {"file": "other.lib", "source": "other", "name": "Q1", "def": "model",
         "type": "NPN", "pins": [], "deps": [], "changes": [], "note": "",
         "provenance": dict(PROV, source="other", url="https://other.example/o.lib")},
    ],
    "preferred": "acme.lib",
    "preferred_why": "best datasheet agreement, tied with other.lib (tools/verify.py)",
    "verification": {"acme.lib": {"score": 1.0, "counts": {"pass": 6, "off": 0, "fail": 0,
                                                           "na": 3, "typ_rows": 1}, "error": None}},
    "datasheet": {"url": "https://acme.example/q1.pdf", "maker": "acme", "doc": "Q1 sheet",
                  "date": "1974-06", "pdf": "datasheets/bjt/Q1_acme.pdf"},
}


def test_nothing_that_names_the_private_tree_is_published():
    """The curation is full of local paths; the recipe must carry none of them."""
    text = yaml.safe_dump(P.recipe(PART))
    for private in ("sources/acme/raw", "SOURCE.md", "manifest.json", "datasheets/bjt/Q1_acme.pdf"):
        assert private not in text, private


def test_the_recipe_says_how_to_get_the_file():
    got = P.recipe(PART)["models"][0]["get"]
    assert got["url"] == "https://acme.example/acme.lib"
    assert got["sha256"] == "aa" * 32
    assert got["lines"] == {"Q1": [7, 19]}


def test_the_licence_is_not_copied_in():
    """It lives once in the registry; a copy here would go stale the day a source is reviewed."""
    doc = P.recipe(PART)
    assert "licence" not in doc and all("licence" not in m for m in doc["models"])


def test_the_preferred_model_is_named_as_a_source_not_a_file():
    doc = P.recipe(PART)
    assert doc["preferred"] == "acme"
    assert "tools/verify.py" not in doc["preferred_why"] and ".lib" not in doc["preferred_why"]


def test_the_two_cryptic_score_keys_are_spelled_out():
    v = P.recipe(PART)["models"][0]["verification"]
    assert v == {"score": 1.0, "pass": 6, "marginal": 0, "fail": 0,
                 "not_measurable": 3, "typical_rows": 1}


def test_a_model_that_ships_with_a_simulator_says_so_instead_of_an_empty_link():
    prov = {"source": "ltspice-native", "file": "$LTSPICE_LIB/cmp/standard.dio", "url": None,
            "file_sha256": "bb" * 32,
            "origin": "LTspice 17.2.4 installed library (Analog Devices); ~/somewhere/local/lib"}
    got = P.get_block(prov)
    assert got["installed_with"] == "LTspice 17.2.4 installed library (Analog Devices)"
    assert got["file"] == "cmp/standard.dio"
    assert "url" not in got and "somewhere" not in json.dumps(got)   # the machine's own path stays out


def test_an_unpacked_model_is_linked_to_the_archive_it_came_from(tmp_path, monkeypatch):
    """Curation recorded the path it read, not the link; the manifest still holds the link."""
    entry = {"url": "https://acme.example/pack.zip", "path": "raw/pack.zip", "sha256": "cc" * 32}
    monkeypatch.setattr(P, "source_files", lambda s: [entry])
    got = P.get_block({"source": "acme", "file": "sources/acme/extracted/pack/lib/q.lib",
                       "file_sha256": "dd" * 32})
    assert got["url"] == "https://acme.example/pack.zip"
    assert got["member"] == "lib/q.lib" and got["archive_sha256"] == "cc" * 32
    assert "archive_inferred" not in got          # the folder names the archive: this is a record


def test_a_guessed_archive_is_published_as_a_guess(tmp_path, monkeypatch):
    """One archive on file and a folder that names none of them: still useful, but it is an inference."""
    entry = {"url": "https://acme.example/bundle.zip", "path": "raw/bundle.zip", "sha256": "ee" * 32}
    monkeypatch.setattr(P, "source_files", lambda s: [entry])
    got = P.get_block({"source": "acme", "file": "sources/acme/extracted/LIBRARY/q.lib",
                       "file_sha256": "ff" * 32})
    assert got["url"] == "https://acme.example/bundle.zip" and got["archive_inferred"] is True


def test_a_model_with_no_recorded_origin_says_unknown_rather_than_an_empty_link(monkeypatch):
    monkeypatch.setattr(P, "source_files", lambda s: [])
    got = P.get_block({"source": "acme", "file": "sources/acme/extracted/x/q.lib"})
    assert got["how"] == "unknown" and "url" not in got


@pytest.mark.parametrize("changes,expected", [([], True), ([{"id": "rb_fix"}], False)])
def test_verbatim_says_whether_we_changed_the_text(changes, expected):
    part = json.loads(json.dumps(PART))
    part["candidates"][0]["changes"] = changes
    m = P.recipe(part)["models"][0]
    assert m["verbatim"] is expected
    assert ("changes" in m) is (not expected)


@pytest.mark.parametrize("prose,expected", [
    ("Treated like any other model here (Ada, 2026-09-20).",
     "Treated like any other model here (maintainer, 2026-09-20)."),
    ("Checked against the sheet (Ada Lovelace, 2026-09-20)",
     "Checked against the sheet (maintainer, 2026-09-20)"),
    ("commit deadbee", "commit deadbee"),                       # nothing to strip
    ("see RFC (2026-09-20)", "see RFC (2026-09-20)"),           # a bare date is not a signature
])
def test_a_signed_judgement_keeps_its_date_and_loses_the_name(prose, expected):
    """Notes are prose the maintainer wrote for themselves, and the public side carries no names."""
    assert P.unsigned(prose) == expected
