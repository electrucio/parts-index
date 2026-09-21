"""The guard's own tests. It is the last thing between the private tree and a public push."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "licence_guard.py"


def run() -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GUARD), "--all"], capture_output=True, text=True, cwd=ROOT)


@pytest.fixture
def dropped():
    """A file placed in the working tree and removed afterwards, tracked or not."""
    made: list[Path] = []
    def put(rel: str, text: str) -> Path:
        p = ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        made.append(p)
        return p
    yield put
    for p in made:
        p.unlink(missing_ok=True)


def test_the_repository_as_it_stands_is_clean():
    assert run().returncode == 0, run().stderr


def test_a_patch_against_a_model_is_caught_although_its_suffix_is_not_a_model_one(dropped):
    """A diff carries the vendor's surrounding lines, so the text is looked for, not just the name."""
    dropped("data/models/_probe.patch",
            "--- a\n+++ b\n@@ -1 +1 @@\n-.model Q1 NPN(BF=100)\n+.model Q1 NPN(BF=120)\n")
    out = run()
    assert out.returncode == 1 and "_probe.patch" in out.stderr


def test_a_file_that_is_not_yet_tracked_is_checked(dropped):
    """`--all` once read `git ls-files`, so a newly generated tree was invisible until it was committed."""
    # Assembled from pieces, like the guard's own patterns, so this file does not trip its own bait.
    bait = "/" + "home" + "/someone/secret"
    dropped("data/models/_probe.yaml", f"note: {bait}\n")
    out = run()
    assert out.returncode == 1 and "_probe.yaml" in out.stderr


def test_invented_model_text_in_a_test_is_allowed(dropped):
    dropped("tests/_probe_fixture.py", 'NPN = """\n.MODEL Q1 NPN (BF=300)\n"""\n')
    assert run().returncode == 0
