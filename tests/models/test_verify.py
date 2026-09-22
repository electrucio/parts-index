"""The model tree against what says it should be there: the manifests and the ledger, not itself."""
from __future__ import annotations

import hashlib

import pytest

from parts_index.core import config
from parts_index.core.ledger import MODEL_FIELDS, MODEL_STAGES, MODEL_VERSIONED, Ledger
from parts_index.models import fetch as F
from parts_index.models import verify as V

MODEL = b"* vendor\n.MODEL Q2N3904 NPN (IS=1E-14 BF=300)\n"


@pytest.fixture
def tree(tmp_path, monkeypatch):
    monkeypatch.setenv("PIDX_SPICE_MODELS", str(tmp_path / "models"))
    (tmp_path / "models" / "sources" / "acme" / "raw").mkdir(parents=True)
    monkeypatch.setattr(config, "model_state", lambda s: tmp_path / "state" / f"{s}.csv")
    monkeypatch.setattr(F, "model_state", lambda s: tmp_path / "state" / f"{s}.csv")
    monkeypatch.setattr(V, "model_state", lambda s: tmp_path / "state" / f"{s}.csv")
    return tmp_path


def give(name: str, body: bytes = MODEL, *, on_disk: bool = True, recorded: bytes | None = None) -> str:
    """One file of source acme: written to the tree, named in the manifest, stamped in the ledger."""
    url = f"https://acme.example/{name}"
    rel = f"raw/{name}"
    path = config.spice_source("acme") / rel
    if on_disk:
        path.write_bytes(body)
    manifest = F.Manifest("acme")
    manifest.add(url, rel, recorded if recorded is not None else body)
    manifest.save()
    led = Ledger(config.model_state("acme"), stages=MODEL_STAGES, fields=MODEL_FIELDS, versioned=MODEL_VERSIONED)
    led.stamp(url, "fetch", status="downloaded", bytes=len(body),
              sha256=hashlib.sha256(recorded if recorded is not None else body).hexdigest())
    led.save()
    return url


def test_a_tree_that_holds_everything_says_so(tree):
    give("q.lib")
    counts = V.look("acme")["counts"]
    assert counts["held"] == 1 and not any(counts[s] for s in counts if s != "held")


def test_a_file_the_tree_no_longer_holds_is_lost(tree):
    """The check a rebuilt catalogue cannot make, because it is rebuilt from the tree it is checking."""
    give("gone.lib", on_disk=False)
    report = V.look("acme")
    assert report["counts"]["lost"] == 1
    assert report["broken"][0]["path"] == "raw/gone.lib"


def test_a_file_that_no_longer_matches_what_arrived_is_changed(tree):
    give("edited.lib", b"* edited by hand\n", recorded=MODEL)
    assert V.look("acme")["counts"]["changed"] == 1


def test_a_download_no_manifest_entry_names_is_reported(tree):
    give("q.lib")
    led = Ledger(config.model_state("acme"), stages=MODEL_STAGES, fields=MODEL_FIELDS, versioned=MODEL_VERSIONED)
    led.stamp("https://acme.example/orphan.lib", "fetch", status="downloaded", sha256="deadbeef")
    led.stamp("part:2N3904", "fetch", status="not_published")      # a part lookup is not a file
    led.save()

    counts = V.look("acme")["counts"]
    assert counts["unrecorded"] == 1 and counts["held"] == 1


def test_repair_puts_the_file_back_where_it_was(tree, monkeypatch):
    url = give("gone.lib", on_disk=False)
    monkeypatch.setattr(F, "how_to_ask", lambda source: {})
    monkeypatch.setattr(F.http, "get", lambda u, **kw: F.http.Response(200, u, "text/plain", MODEL))

    out = V.repair(V.look("acme"), log=lambda *a: None)
    assert out == {"recovered": 1, "differs": 0, "gone": 0}
    assert (config.spice_source("acme") / "raw/gone.lib").read_bytes() == MODEL
    assert V.look("acme")["counts"]["held"] == 1
    assert url.endswith("gone.lib")


def test_repair_says_when_the_vendor_serves_something_else_today(tree, monkeypatch):
    give("gone.lib", on_disk=False)
    monkeypatch.setattr(F, "how_to_ask", lambda source: {})
    monkeypatch.setattr(F.http, "get", lambda u, **kw: F.http.Response(200, u, "text/plain", b"* a newer model\n"))

    assert V.repair(V.look("acme"), log=lambda *a: None)["differs"] == 1


def test_something_deleted_on_purpose_is_not_a_loss(tree):
    """A prune is a decision. The manifest records it, and verify stops asking about that file."""
    give("notes.lib", on_disk=False)
    manifest = F.Manifest("acme")
    manifest.by_url("https://acme.example/notes.lib")["kept"] = False
    manifest.save()

    counts = V.look("acme")["counts"]
    assert counts["not_kept"] == 1 and counts["lost"] == 0


def test_what_could_never_have_been_a_model_is_counted_apart(tree):
    """Images and plots arrive with the models inside an archive; losing one costs nothing."""
    give("plot.png", b"\x89PNG\r\n\x1a\n", on_disk=False)
    give("q.lib", on_disk=False)

    counts = V.look("acme")["counts"]
    assert counts["material"] == 1 and counts["lost"] == 1
