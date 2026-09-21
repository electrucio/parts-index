"""Downloading a model, judging what arrived, and getting back what the tree lost."""
import hashlib
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

import pytest

from parts_index.core import config
from parts_index.models import fetch as F

MODEL = b"* vendor\n.MODEL Q2N3904 NPN (IS=1E-14 BF=300)\n"
LOGIN = b"<!DOCTYPE html><html><head><title>Sign in</title></head><body>please log in</body></html>"


def zipped(**members) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in members.items():
            z.writestr(name.replace("__", "/"), body)
    return buf.getvalue()


ARCHIVE = zipped(**{"lib__q.lib": MODEL.decode(), "readme.txt": "notes"})


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body, status = {"/q.lib": (MODEL, 200), "/pack.zip": (ARCHIVE, 200),
                        "/login": (LOGIN, 200), "/empty": (b"", 200)}.get(self.path, (b"no", 404))
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    """A private tree and a public ledger directory of our own."""
    monkeypatch.setenv("PIDX_SPICE_MODELS", str(tmp_path / "models"))
    (tmp_path / "models" / "sources" / "acme").mkdir(parents=True)
    monkeypatch.setattr(config, "model_state", lambda s: tmp_path / "state" / f"{s}.csv")
    monkeypatch.setattr(F, "model_state", lambda s: tmp_path / "state" / f"{s}.csv")
    monkeypatch.setattr(F.http, "DELAY", 0)
    return tmp_path


@pytest.mark.parametrize("data,verdict", [
    (MODEL, "model"), (LOGIN, "html"), (b"", "empty"), (b"short", "empty"),
    (ARCHIVE, "zip"), (b"* nothing here at all, just prose about models\n", "text_no_model"),
    (b"$CDNENCSTART" + b"x" * 100, "encrypted"),
])
def test_it_says_what_arrived(data, verdict):
    assert F.inspect(data)[0] == verdict


def test_a_model_is_kept_and_recorded_twice(tree, server):
    got = F.fetch("acme", f"{server}/q.lib")
    assert got == {"status": "downloaded", "path": "raw/q.lib", "verdict": "model",
                   "definitions": 1, "unpacked": 0}
    body = (tree / "models/sources/acme/raw/q.lib").read_bytes()
    assert body == MODEL
    entry = F.Manifest("acme").by_url(f"{server}/q.lib")            # private: URL -> local file
    assert entry["sha256"] == hashlib.sha256(MODEL).hexdigest() and entry["path"] == "raw/q.lib"
    row = next(iter(__import__("csv").DictReader(open(tree / "state/acme.csv"))))   # public: URL only
    assert row["status"] == "downloaded" and row["sha256"] == entry["sha256"]
    assert "raw/q.lib" not in (tree / "state/acme.csv").read_text()


def test_an_archive_is_unpacked_where_the_catalogue_looks(tree, server):
    got = F.fetch("acme", f"{server}/pack.zip")
    assert got["verdict"] == "zip" and got["unpacked"] == 2
    assert (tree / "models/sources/acme/extracted/pack/lib/q.lib").read_bytes() == MODEL


def test_a_login_page_is_not_a_model(tree, server):
    got = F.fetch("acme", f"{server}/login")
    assert got == {"status": "not_published", "verdict": "html"}
    assert not (tree / "models/sources/acme/raw").exists()
    row = next(iter(__import__("csv").DictReader(open(tree / "state/acme.csv"))))
    assert row["skip_reason"] == "html"


def test_a_missing_url_is_recorded_as_an_error(tree, server):
    assert F.fetch("acme", f"{server}/nothing")["status"] == "error"


def test_unpacking_never_escapes_its_directory(tmp_path):
    evil = tmp_path / "evil.zip"
    evil.write_bytes(zipped(**{"..__..__escaped.lib": "x", "fine.lib": "y"}))
    assert F.unpack(evil, tmp_path / "out") == 1
    assert (tmp_path / "out/fine.lib").is_file() and not (tmp_path / "escaped.lib").exists()


def manifest(tree, source, files):
    p = tree / "models/sources" / source
    p.mkdir(parents=True, exist_ok=True)
    (p / "manifest.json").write_text(json.dumps({"source_id": source, "files": files}))


def test_an_extracted_file_is_recovered_through_its_archive(tree):
    manifest(tree, "acme", [{"url": "https://v.example/pack.zip", "path": "raw/pack.zip", "sha256": "aa"}])
    gone = [{"file": "sources/acme/extracted/pack/lib/q.lib", "source": "acme", "definitions": 3},
            {"file": "sources/acme/extracted/pack/lib/r.lib", "source": "acme", "definitions": 1}]
    targets, unmatched = F.recovery_targets(gone)
    assert not unmatched
    assert [t[1]["url"] for t in targets] == ["https://v.example/pack.zip"]     # one download, both files


def test_an_archive_that_was_never_kept_is_still_found(tree):
    """Some archives were too large to keep; only what came out of them is on disk."""
    manifest(tree, "big", [{"url": "http://v.example/lib.zip", "path": None, "sha256": "bb",
                            "note": "zip not kept (>20 MB rule)"}])
    gone = [{"file": "sources/big/extracted/lib/cmp/x.mos", "source": "big", "definitions": 9}]
    targets, unmatched = F.recovery_targets(gone)
    assert not unmatched and targets[0][1]["url"] == "http://v.example/lib.zip"


def test_a_file_with_no_url_recorded_cannot_be_recovered(tree):
    manifest(tree, "hand", [{"url": None, "path": "raw/typed_in.lib"}])
    gone = [{"file": "sources/hand/raw/typed_in.lib", "source": "hand", "definitions": 2}]
    targets, unmatched = F.recovery_targets(gone)
    assert not targets and unmatched == gone


def test_recovery_verifies_against_the_checksum_we_had(tree, server):
    manifest(tree, "acme", [{"url": f"{server}/q.lib", "path": "raw/q.lib",
                             "sha256": hashlib.sha256(MODEL).hexdigest()}])
    counts = F.recover([{"file": "sources/acme/raw/q.lib", "source": "acme", "definitions": 1}])
    assert counts["fetched"] == 1 and counts["verified"] == 1 and counts["changed"] == 0


def test_recovery_says_so_when_the_vendor_changed_the_file(tree, server, capsys):
    manifest(tree, "acme", [{"url": f"{server}/q.lib", "path": "raw/q.lib", "sha256": "notwhatitis"}])
    counts = F.recover([{"file": "sources/acme/raw/q.lib", "source": "acme", "definitions": 1}])
    assert counts["verified"] == 0 and counts["changed"] == 1
    assert "checksum differs" in capsys.readouterr().out


def test_a_flattened_manifest_path_still_names_its_file(tree):
    """An early recovery run recorded `raw/<name>` for files that belong deep in a tree.

    The entry kept the right URL, so the file name finds it; and what is written back is the path the
    catalogue gives, not the flattened one, or the next run would have to recover it all over again.
    """
    manifest(tree, "kicad", [{"url": "https://raw.example/repo/c0de/Models/Maxim%20Integrated/MAX4200.FAM",
                              "path": "raw/MAX4200.FAM", "sha256": "cc"}])
    deep = "sources/kicad/raw/repo/Models/Maxim Integrated/MAX4200.FAM"
    targets, unmatched = F.recovery_targets([{"file": deep, "source": "kicad", "definitions": 48}])
    assert not unmatched
    assert targets[0][1]["rel"] == "raw/repo/Models/Maxim Integrated/MAX4200.FAM"


def test_two_files_of_the_same_name_are_not_guessed_at(tree):
    """A name that matches two entries identifies neither, and guessing would fetch the wrong one."""
    manifest(tree, "twins", [{"url": "https://v.example/a/x.lib", "path": "raw/a/x.lib", "sha256": "dd"},
                             {"url": "https://v.example/b/x.lib", "path": "raw/b/x.lib", "sha256": "ee"}])
    gone = [{"file": "sources/twins/raw/c/x.lib", "source": "twins", "definitions": 1}]
    targets, unmatched = F.recovery_targets(gone)
    assert not targets and unmatched == gone
