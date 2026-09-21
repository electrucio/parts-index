"""The public/private boundary, asserted. Every location is named in core.config and nowhere else."""
import re
import subprocess

import pytest

from parts_index.core import config

REPO = config.REPO_ROOT
# scripts/licence_guard.py is deliberately standalone (stdlib only, runs in the git hook before the
# package is installed), so it is allowed to spell out the private directory itself.
SOURCE_DIRS = ["src", "tests"]


def test_every_location_resolves_on_the_right_side():
    # Compare logical paths, never resolved ones: corpus/ and books/ are symlinks to the real corpora,
    # and what decides whether git can see a file is the path inside the checkout, not its target.
    roots = (config.material_root(), config.spice_models_root())
    for name, visibility, path, _ in config.describe():
        inside_private = any(path == r or r in path.parents for r in roots)
        if visibility in ("public", "built"):
            assert not inside_private, f"{name} is {visibility} but lives inside the data root: {path}"
            assert REPO in path.parents or path == REPO, f"{name} escapes the checkout: {path}"
        else:
            assert inside_private, f"{name} is private but lives outside the data root: {path}"


def test_each_private_tree_can_be_moved_on_its_own(monkeypatch, tmp_path):
    monkeypatch.setenv("PIDX_MATERIAL", str(tmp_path / "m"))
    monkeypatch.setenv("PIDX_SPICE_MODELS", str(tmp_path / "s"))
    assert config.index_db() == tmp_path / "m" / "index.sqlite"
    assert config.spice_part_json("bjt", "2N3904") == tmp_path / "s" / "models" / "bjt" / "2N3904" / "part.json"
    assert config.schematics_parts() == config.PUBLIC_DATA / "schematics" / "parts.csv"   # public is unmoved


def test_require_explains_itself(tmp_path):
    with pytest.raises(config.PrivateDataMissing, match="rebuilding the index"):
        config.require(tmp_path / "nothing", "rebuilding the index")
    assert config.require(tmp_path, "this exists") == tmp_path


def test_readonly_uri_is_readonly():
    assert config.index_db_uri().endswith("?mode=ro")
    assert "?" not in config.index_db_uri(readonly=False)


def test_no_other_module_hardcodes_a_location():
    """Only config.py may name a private tree or build a path on the public-data anchor."""
    offenders = []
    # Naming a private tree, or building a path on top of the public-data anchor, both belong here only.
    suspicious = re.compile(r'private_material|private_web_spice_models|PUBLIC_DATA\s*/')
    for d in SOURCE_DIRS:
        for f in (REPO / d).rglob("*.py"):
            # config.py defines them; these two assert on what the tools print, which is not the same
            # thing as building a path.
            if f.name in ("config.py", "test_config.py", "test_commands.py") or "__pycache__" in f.parts:
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


def test_built_locations_are_git_ignored():
    """Generated output lives in the checkout but must never be committed."""
    built = [str(p.relative_to(REPO)) for _, v, p, _ in config.describe() if v == "built"]
    r = subprocess.run(["git", "check-ignore", *built], cwd=REPO, capture_output=True, text=True)
    assert set(r.stdout.split()) == set(built), f"built locations git does not ignore: {r.stdout}"


def test_both_private_trees_are_git_ignored():
    """One directory rule each covers every private location, which the test above proves are under them."""
    for root in (config.material_root(), config.spice_models_root()):
        if REPO not in root.parents:
            continue                                        # kept outside the checkout
        r = subprocess.run(["git", "check-ignore", str(root.relative_to(REPO))],
                           cwd=REPO, capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout.strip(), f"the private tree {root} is NOT git-ignored"
