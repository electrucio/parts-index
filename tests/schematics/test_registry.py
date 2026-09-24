"""The registry as it is actually shipped: read it, and hold it to what the stages expect of it.

Every other test here builds a registry of its own. This one reads `data/schematics/sources.yaml`, so a
pattern that does not compile is caught now rather than by a crawl that dies on its first page, hours
after it was launched and in a log nobody is watching.
"""
from __future__ import annotations

import re

import pytest
import yaml

from parts_index.core import config

REGISTRY = yaml.safe_load(config.schematics_registry().read_text(encoding="utf-8"))
SOURCES = REGISTRY["sources"] if "sources" in REGISTRY else REGISTRY
CRAWLED = sorted(name for name, entry in SOURCES.items() if entry.get("crawl"))
STATUSES = {"active", "proposed", "blocked", "excluded"}


@pytest.mark.parametrize("name", CRAWLED)
def test_every_crawl_pattern_compiles(name):
    """`(?i)` has to come first in a pattern, and radiomanual's did not."""
    for key in ("allow", "deny", "cdn"):
        pattern = SOURCES[name]["crawl"].get(key)
        if pattern is not None:
            re.compile(pattern)          # raises re.error, which is the whole test


@pytest.mark.parametrize("name", CRAWLED)
def test_every_crawl_says_where_to_start_and_where_it_may_go(name):
    crawl = SOURCES[name]["crawl"]
    assert crawl.get("start"), f"{name} has a crawl block with nowhere to start"
    assert crawl.get("allow"), f"{name} would wander the whole host"


def test_every_source_has_a_status_the_stages_know():
    wrong = {n: e.get("status") for n, e in SOURCES.items() if e.get("status") not in STATUSES}
    assert not wrong
