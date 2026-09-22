"""Reading how much attention a project has, and the two traps in doing so."""
from __future__ import annotations

import csv
import json
from datetime import date, timedelta

import pytest

from parts_index.core import config
from parts_index.datasets import repos as R

NODE = {"nameWithOwner": "a/one", "stargazerCount": 12, "forkCount": 3,
        "watchers": {"totalCount": 5}, "pushedAt": "2026-01-02T00:00:00Z", "isArchived": False}


@pytest.fixture
def tables(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_DATA", tmp_path / "data")
    p = config.dataset_table("part_repos")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("part,sheets,url\n"
                 "TL072,2,https://github.com/a/one\n"
                 "TL072,1,https://github.com/b/two\n"
                 "TL072,1,https://github.com/c/three\n", encoding="utf-8")
    monkeypatch.setattr(R, "shutil", type("x", (), {"which": staticmethod(lambda _: "/usr/bin/gh")}))
    return tmp_path


def read():
    with open(config.dataset_table("repo_stats"), encoding="utf-8") as f:
        return {r["url"].replace(R.HOST, ""): r for r in csv.DictReader(f)}


def test_one_query_carries_a_whole_batch(tables):
    q = R.query(["a/one", "b/two"])
    assert 'r0: repository(owner:"a", name:"one")' in q
    assert 'r1: repository(owner:"b", name:"two")' in q
    assert "watchers { totalCount }" in q      # the real watchers, not the REST alias for stars


def test_a_repository_that_is_gone_is_recorded_rather_than_dropped(tables, monkeypatch):
    """A project that has disappeared is one more dead link, which is worth knowing."""
    monkeypatch.setattr(R, "ask", lambda batch: {r: (NODE if r == "a/one" else None) for r in batch})
    c = R.refresh()
    assert c["gone"] == 2 and c["live"] == 1
    assert read()["b/two"]["status"] == "gone"
    assert read()["b/two"]["stars"] == ""


def test_a_renamed_repository_keeps_the_name_our_links_use(tables, monkeypatch):
    """GitHub redirects a renamed repository and answers under the new name. Storing that instead would
    break the join with part_repos.csv, which is where the links come from. 236 of them have moved."""
    moved = dict(NODE, nameWithOwner="newowner/one")
    monkeypatch.setattr(R, "ask", lambda batch: {r: (moved if r == "a/one" else None) for r in batch})
    R.refresh()
    row = read()["a/one"]
    assert row["url"] == R.HOST + "a/one" and row["moved_to"] == R.HOST + "newowner/one"
    assert c_rows_are_one_per_asked_repo()


def c_rows_are_one_per_asked_repo() -> bool:
    return len(read()) == len(R.wanted())


def test_a_reading_is_not_repeated_while_it_is_fresh(tables, monkeypatch):
    calls = []
    def ask(batch):
        calls.append(len(batch))
        return {r: NODE for r in batch}
    monkeypatch.setattr(R, "ask", ask)
    R.refresh()
    R.refresh()
    assert calls == [3], "the second run should have asked for nothing"
    assert R.refresh(all_=True)["asked"] == 3


def test_a_reading_that_has_aged_is_taken_again(tables, monkeypatch):
    monkeypatch.setattr(R, "ask", lambda batch: {r: NODE for r in batch})
    R.refresh()
    old = date.today() - timedelta(days=90)
    path = config.dataset_table("repo_stats")
    path.write_text(path.read_text(encoding="utf-8").replace(date.today().isoformat(), old.isoformat()),
                    encoding="utf-8")
    assert R.refresh(days=30)["asked"] == 3


def test_the_error_says_what_to_do_when_gh_is_missing(tables, monkeypatch):
    monkeypatch.setattr(R, "shutil", type("x", (), {"which": staticmethod(lambda _: None)}))
    with pytest.raises(RuntimeError, match="gh auth login"):
        R.refresh()


def test_the_batch_reads_what_gh_prints_even_when_some_of_it_failed(tables, monkeypatch):
    """`gh` writes NOT_FOUND to stderr and still returns the data for everything else."""
    out = json.dumps({"data": {"r0": NODE, "r1": None},
                      "errors": [{"type": "NOT_FOUND", "path": ["r1"]}]})
    monkeypatch.setattr(R.subprocess, "run",
                        lambda *a, **k: type("p", (), {"stdout": out, "stderr": "Could not resolve"})())
    got = R.ask(["a/one", "b/two"])
    assert got["a/one"]["stargazerCount"] == 12 and got["b/two"] is None
