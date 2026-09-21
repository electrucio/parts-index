"""Checks against the real exported index, which CI runs from a clean clone."""
from __future__ import annotations

import csv
import json
from collections import Counter

import pytest
import yaml

from parts_index.core.config import (
    schematics_documents,
    schematics_export_manifest,
    schematics_parts,
    schematics_registry,
    schematics_uses,
)

SOURCES = sorted(p.stem for p in schematics_documents("x").parent.glob("*.csv")) \
    if schematics_documents("x").parent.is_dir() else []
pytestmark = pytest.mark.skipif(not SOURCES, reason="the index has not been exported yet")


def read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_every_use_points_at_a_document_that_is_published():
    """A use naming a document nobody published would be a result that leads nowhere."""
    bad = []
    for s in SOURCES:
        ids = {r["id"] for r in read(schematics_documents(s))}
        bad += [f"{s}:{r['doc']}" for r in read(schematics_uses(s)) if r["doc"] not in ids]
    assert not bad, bad[:10]


def test_every_source_that_has_an_index_is_in_the_registry():
    registry = yaml.safe_load(schematics_registry().read_text(encoding="utf-8")) or {}
    assert not set(SOURCES) - set(registry)


def test_no_document_id_is_used_twice():
    for s in SOURCES:
        ids = [r["id"] for r in read(schematics_documents(s))]
        assert len(ids) == len(set(ids)), s


def test_parts_re_derives_exactly_from_the_uses():
    docs, pages, uses, srcs = Counter(), Counter(), Counter(), {}
    for s in SOURCES:
        seen_d, seen_p = set(), set()
        for r in read(schematics_uses(s)):
            uses[r["part"]] += 1
            seen_d.add((r["part"], r["doc"]))
            seen_p.add((r["part"], r["doc"], r["page"]))
            srcs.setdefault(r["part"], set()).add(s)
        for p, _ in seen_d:
            docs[p] += 1
        for p, _, _ in seen_p:
            pages[p] += 1
    bad = []
    for r in read(schematics_parts()):
        p = r["part"]
        if (int(r["documents"]), int(r["pages"]), int(r["uses"]), r["sources"]) != (
                docs[p], pages[p], uses[p], " ".join(sorted(srcs[p]))):
            bad.append(p)
    assert not bad, bad[:10]


def test_the_manifest_agrees_with_what_is_on_disk():
    m = json.loads(schematics_export_manifest().read_text(encoding="utf-8"))
    assert set(m["sources"]) == set(SOURCES)
    for s in SOURCES:
        assert m["sources"][s]["uses"] == len(read(schematics_uses(s))), s
    assert m["totals"]["uses"] == sum(v["uses"] for v in m["sources"].values())


def test_every_published_link_is_a_link_and_not_a_local_path():
    from parts_index.core.config import schematics_pages
    bad = []
    for s in SOURCES:
        for r in read(schematics_pages(s)):
            if not r["url"].startswith(("http://", "https://")):
                bad.append(f"{s}:{r['doc']}:{r['page']}")
    assert not bad, bad[:10]
