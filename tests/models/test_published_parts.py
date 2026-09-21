"""Checks against the real `data/models/parts/`, which CI runs from a clean clone.

These need no private corpus: the published recipes are in git, and the point is that they stay honest
on their own. Referential integrity is the one that earns its keep — it is what found `ltspice-native`,
a source named by 74 parts and registered nowhere.
"""
from __future__ import annotations

import re

import pytest
import yaml

from parts_index.core.config import model_part, model_sources

PARTS = sorted(model_part("*", "*").parent.parent.glob("*/*.yaml"))
REGISTERED = {p.stem for p in model_sources().glob("*.yaml")}
PRIVATE = re.compile(r"(?:^|[\s'\"])(?:sources|private_\w+|datasheets)/|\$[A-Z_]+/|/(?:home|Users)/")


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.skipif(not PARTS, reason="no promoted parts yet")
def test_every_source_named_by_a_model_is_registered():
    unknown = {m["source"] for p in PARTS for m in load(p)["models"]} - REGISTERED
    assert not unknown, f"named by a part but absent from data/models/sources/: {sorted(unknown)}"


@pytest.mark.skipif(not PARTS, reason="no promoted parts yet")
def test_no_recipe_names_a_path_from_the_private_tree():
    bad = [p.name for p in PARTS if PRIVATE.search(p.read_text(encoding="utf-8"))]
    assert not bad, bad[:10]


@pytest.mark.skipif(not PARTS, reason="no promoted parts yet")
def test_no_recipe_carries_model_text():
    """The recipe says where the definition is, never what it says."""
    bad = [p.name for p in PARTS
           if re.search(r"^\s*\.(model|subckt)\s", p.read_text(encoding="utf-8"), re.M | re.I)]
    assert not bad, bad[:10]


@pytest.mark.skipif(not PARTS, reason="no promoted parts yet")
def test_every_model_says_how_to_obtain_it_or_admits_it_cannot():
    """A link we followed, a simulator that installs it, or `how: unknown` — never an empty link."""
    bad = []
    for p in PARTS:
        for m in load(p)["models"]:
            g = m["get"]
            if not (g.get("url") or g.get("installed_with") or g.get("how") == "unknown"):
                bad.append(f"{p.name}:{m['source']}")
            if g.get("url") == "":
                bad.append(f"{p.name}:{m['source']} empty url")
    assert not bad, bad[:10]


@pytest.mark.skipif(not PARTS, reason="no promoted parts yet")
def test_the_preferred_model_is_one_of_the_models_offered():
    bad = []
    for p in PARTS:
        doc = load(p)
        if doc.get("preferred") and doc["preferred"] not in {m["source"] for m in doc["models"]}:
            bad.append(f"{p.name}: prefers {doc['preferred']}")
    assert not bad, bad[:10]
