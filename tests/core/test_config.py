"""The public/private boundary, asserted. Every location is named in core.config and nowhere else."""
import re
import subprocess
from pathlib import Path

import pytest

from parts_index.core import config

REPO = config.REPO_ROOT
# scripts/licence_guard.py is deliberately standalone (stdlib only, runs in the git hook before the
# package is installed), so it is allowed to spell out the private directory itself.
SOURCE_DIRS = ["src", "tests"]


def test_every_location_resolves_on_the_right_side():
    # Compare logical paths, never resolved ones: corpus/ and books/ are symlinks to the real corpora,
    # and what decides whether git can see a file is the path inside the checkout, not its target.
    root = config.data_root()
    for name, visibility, path, _ in config.describe():
        inside_private = path == root or root in path.parents
        if visibility == "public":
            assert not inside_private, f"{name} is public but lives inside the data root: {path}"
            assert REPO in path.parents or path == REPO, f"{name} escapes the checkout: {path}"
        else:
            assert inside_private, f"{name} is private but lives outside the data root: {path}"


def test_the_data_root_can_be_moved(monkeypatch, tmp_path):
    monkeypatch.setenv("PIDX_DATA_ROOT", str(tmp_path))
    assert config.data_root() == tmp_path
    assert config.corpus_db() == tmp_path / "corpus" / "db" / "schematics.sqlite"
    assert config.schematics_parts() == config.PUBLIC_DATA / "schematics" / "parts.csv"   # public is unmoved


def test_require_explains_itself(tmp_path):
    with pytest.raises(config.PrivateDataMissing, match="rebuilding the index"):
        config.require(tmp_path / "nothing", "rebuilding the index")
    assert config.require(tmp_path, "this exists") == tmp_path


def test_readonly_uri_is_readonly():
    assert config.corpus_db_uri().endswith("?mode=ro")
    assert "?" not in config.corpus_db_uri(readonly=False)


def test_no_other_module_hardcodes_a_location():
    """Only config.py may spell out a directory under the data root or a data/ subdirectory."""
    offenders = []
    suspicious = re.compile(r'["\'](?:private_uncommitted|corpus|spice|staging)/|/\s*"(?:corpus|spice|staging)"')
    for d in SOURCE_DIRS:
        for f in (REPO / d).rglob("*.py"):
            if f.name in ("config.py", "test_config.py") or "__pycache__" in f.parts:
                continue
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if suspicious.search(line) and "config." not in line:
                    offenders.append(f"{f.relative_to(REPO)}:{i}: {line.strip()[:90]}")
    assert not offenders, "these must ask core.config instead:\n" + "\n".join(offenders)


def test_nothing_public_is_git_ignored():
    """A public location that git ignores would silently never be committed."""
    public = [str(p.relative_to(REPO)) for _, v, p, _ in config.describe() if v == "public" and REPO in p.parents]
    r = subprocess.run(["git", "check-ignore", *public], cwd=REPO, capture_output=True, text=True)
    assert r.stdout == "", f"public locations are git-ignored:\n{r.stdout}"


def test_the_whole_data_root_is_git_ignored():
    """One directory rule covers every private location, which test_every_location_... proves are under it.

    Checking the root rather than each path is also the only thing git can answer: it refuses a pathspec
    that goes through a symlink, and corpus/ is one.
    """
    root = config.data_root()
    if REPO not in root.parents:
        return                                              # PIDX_DATA_ROOT points outside the checkout
    r = subprocess.run(["git", "check-ignore", str(root.relative_to(REPO))], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip(), f"the data root {root} is NOT git-ignored"
