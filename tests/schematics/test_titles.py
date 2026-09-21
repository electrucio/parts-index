"""A `<title>` is written for a browser tab, not for a list of results."""
from __future__ import annotations

import pytest

from parts_index.schematics import titles


@pytest.mark.parametrize("raw,url,expect", [
    # the site's own name, at either end
    ("ESP | 60W Amplifier - Elliott Sound Products", "https://e.org/p3.htm", "60W Amplifier"),
    ("tubecad.com: Aikido Preamp", "https://tubecad.com/a.html", "Aikido Preamp"),
    # a CMS default says nothing, so the URL has to
    ("index.html", "https://e.org/schematics/fender-bassman-5f6a.pdf", "Fender bassman 5f6a"),
    ("Index of /_pdf/2SK/", "https://e.org/_pdf/2SK/", "2SK"),
    ("", "https://e.org/amps/Marshall_JTM45.gif", "Marshall JTM45"),
    # the whole abstract in the tab: cut at the end of the first sentence. The dash here is at
    # character 9, too early to be the break between a name and its description, so it is not used.
    ("Project 3 - A 60 watt amplifier with low distortion. This article describes the design of a "
     "power amplifier suitable for home construction.", "https://e.org/p3.htm",
     "Project 3 - A 60 watt amplifier with low distortion"),
    # …and here the dash is late enough to be that break, so it is
    ("The Aikido line stage preamplifier - a complete constructional article with PCB layouts",
     "https://e.org/aikido.html", "The Aikido line stage preamplifier"),
    # a normal title is left alone
    ("Building the 5E3 Deluxe", "https://e.org/5e3.html", "Building the 5E3 Deluxe"),
])
def test_clean(raw, url, expect):
    assert titles.clean(raw, url) == expect


def test_it_walks_up_the_url_past_segments_that_say_nothing():
    assert titles.from_url("https://e.org/amps/marshall/index.php") == "Marshall"


def test_a_title_is_never_longer_than_a_line():
    long = "A " + "very " * 60 + "long title"
    assert len(titles.clean(long, "https://e.org/x")) <= titles.MAX
