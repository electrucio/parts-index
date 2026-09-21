"""Every command runs. A command that only breaks when a person types it has no test."""
import pytest

from parts_index import cli


@pytest.mark.parametrize("argv", [
    ["status"],
    ["paths"],
    ["paths", "--public"],
    ["paths", "--private"],
    ["paths", "--missing"],
])
def test_it_runs_and_prints_something(argv, capsys):
    assert cli.main(argv) == 0
    assert capsys.readouterr().out.strip()


def test_web_build_writes_where_it_is_told(tmp_path, capsys):
    assert cli.main(["web", "build", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "manifest.json").is_file()
    assert "schematic sources" in capsys.readouterr().out


def test_paths_separates_the_two_private_trees(capsys):
    cli.main(["paths", "--private"])
    out = capsys.readouterr().out
    assert "private_web_spice_models" in out and "private_material" in out


def test_an_unknown_command_is_refused():
    with pytest.raises(SystemExit):
        cli.main(["nonsense"])
