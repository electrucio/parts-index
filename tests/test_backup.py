"""Packing the private trees, and getting them back.

The round trip is the test that matters: an archive nobody has restored is a hope, not a backup.
"""
from __future__ import annotations

import gzip
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from parts_index import backup as B
from parts_index.core import config

RESTORE = Path(__file__).resolve().parents[1] / "scripts" / "restore_private.py"


def put(path, data: bytes | str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    return path


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A miniature private root, and a checkout to restore it into.

    Built through `core.config` rather than by spelling the directory names out, which is the same rule
    the rest of the project follows and incidentally proves the backup asks config for every location.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    put(repo / "pyproject.toml", "[project]\nname='x'\n")
    monkeypatch.setattr(config, "REPO_ROOT", repo)
    monkeypatch.setattr(B, "REPO_ROOT", repo)
    monkeypatch.setenv("PIDX_MATERIAL", str(repo / config.material_root().name))
    monkeypatch.setenv("PIDX_SPICE_MODELS", str(repo / config.spice_models_root().name))

    put(config.ocr_root() / "esp" / "a.jsonl.gz", gzip.compress(b'{"page":1}\n'))
    put(config.ocr_map(), "source,doc_key\nesp,http://x\n")
    put(config.source_list("esp"), '{"url":"http://x"}\n')
    put(config.download_manifest("esp"), "url,sha256\n")
    put(config.page_sizes(), gzip.compress(b"doc,page\n"))
    put(config.guard_extra_patterns(), "nothing\n")
    put(config.spice_part_json("bjt", "Q1"), '{"part":"Q1"}')
    put(config.spice_source_manifest("acme"), '{"files":[]}')
    put(config.spice_source_doc("acme"), "# acme\n")
    return repo


def packed(level: str) -> set[str]:
    return {B.rel(p) for root, _ in B.contents(level) for p in B.files_under(root)}


def test_everything_irreplaceable_is_packed(tree):
    names = packed("essential")
    for must in (config.ocr_root() / "esp" / "a.jsonl.gz",
                 config.ocr_map(),                      # the tree describes itself
                 config.spice_part_json("bjt", "Q1"),
                 config.spice_source_manifest("acme"),
                 config.source_list("esp"),
                 config.page_sizes()):
        assert B.rel(must) in names, must


def test_the_downloaded_vendor_files_are_left_out_by_default(tree):
    """They have a URL and a checksum in a public ledger; that is what recovery reads."""
    downloaded = put(config.spice_source("acme") / "raw" / "q.lib", ".model Q1 NPN()\n")
    assert B.rel(downloaded) not in packed("essential")
    assert B.rel(downloaded) in packed("full")


def test_an_already_compressed_file_is_stored_rather_than_deflated(tree, tmp_path):
    B.build(tmp_path / "out", "essential")
    archive = next((tmp_path / "out").glob("*.zip"))
    with zipfile.ZipFile(archive) as zf:
        gz = zf.getinfo(B.rel(config.ocr_root() / "esp" / "a.jsonl.gz"))
        txt = zf.getinfo(B.rel(config.guard_extra_patterns()))
    assert gz.compress_type == zipfile.ZIP_STORED
    assert txt.compress_type == zipfile.ZIP_DEFLATED


def test_the_archive_carries_what_is_needed_to_restore_it(tree, tmp_path):
    B.build(tmp_path / "out", "essential")
    archive = next((tmp_path / "out").glob("*.zip"))
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
    assert {"MANIFEST.csv", "RESTORE.md", "restore.py"} <= names
    assert (tmp_path / "out" / "restore.py").is_file()   # also beside it, not only inside


def run_restore(archive: Path, into: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RESTORE), str(archive), "--into", str(into), *args],
                          capture_output=True, text=True)


def test_a_packed_tree_comes_back_byte_for_byte(tree, tmp_path):
    B.build(tmp_path / "out", "essential")
    archive = next((tmp_path / "out").glob("*.zip"))
    roots = (config.material_root().name, config.spice_models_root().name)
    before = {p.relative_to(tree): p.read_bytes()
              for p in tree.rglob("*") if p.is_file() and p.relative_to(tree).parts[0] in roots}

    into = tmp_path / "restored"
    into.mkdir()
    (into / "pyproject.toml").write_text("[project]\nname='x'\n")
    out = run_restore(archive, into)
    assert out.returncode == 0, out.stderr
    after = {p.relative_to(into): p.read_bytes()
             for p in into.rglob("*") if p.is_file() and p.relative_to(into).parts[0] in roots}
    assert after == before


def test_restoring_twice_changes_nothing_the_second_time(tree, tmp_path):
    B.build(tmp_path / "out", "essential")
    archive = next((tmp_path / "out").glob("*.zip"))
    into = tmp_path / "restored"
    into.mkdir()
    (into / "pyproject.toml").write_text("[project]\nname='x'\n")
    run_restore(archive, into)
    again = run_restore(archive, into)
    assert again.returncode == 0 and "0 files restored" in again.stdout


def test_a_file_that_is_there_and_different_is_never_silently_replaced(tree, tmp_path):
    """It is either newer work or a damaged download, and neither should be overwritten by surprise."""
    B.build(tmp_path / "out", "essential")
    archive = next((tmp_path / "out").glob("*.zip"))
    into = tmp_path / "restored"
    into.mkdir()
    put(into / "pyproject.toml", "[project]\nname='x'\n")
    mine = put(into / B.rel(config.ocr_map()), "something newer\n")

    out = run_restore(archive, into)
    assert mine.read_text() == "something newer\n"
    assert "already there and different" in out.stderr

    forced = run_restore(archive, into, "--force")
    assert forced.returncode == 0 and mine.read_text() != "something newer\n"


def test_restore_refuses_a_directory_that_is_not_a_checkout(tree, tmp_path):
    B.build(tmp_path / "out", "essential")
    archive = next((tmp_path / "out").glob("*.zip"))
    elsewhere = tmp_path / "somewhere"
    elsewhere.mkdir()
    out = run_restore(archive, elsewhere)
    assert out.returncode == 1 and "does not look like a parts-index checkout" in out.stderr
    assert not list(elsewhere.rglob("*.gz"))


def test_a_member_naming_a_path_outside_the_target_is_refused(tmp_path):
    into = tmp_path / "into"
    into.mkdir()
    (into / "pyproject.toml").write_text("[project]\nname='x'\n")
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../escaped.txt", "x")
        zf.writestr(f"{config.material_root().name}/fine.txt", "y")
    out = run_restore(evil, into)
    assert not (tmp_path / "escaped.txt").exists()
    assert (into / config.material_root().name / "fine.txt").is_file()
    assert out.returncode == 1 and "refused" in out.stderr
