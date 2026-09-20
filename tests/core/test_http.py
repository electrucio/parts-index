"""The polite client against a local server: robots, pacing, retries, size cap, file names. Both transports."""
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from parts_index.core import http

PDF = b"%PDF-1.4 fake schematic"


class Handler(BaseHTTPRequestHandler):
    flaky_hits = 0

    def log_message(self, *a):
        pass

    def do_GET(self):
        body, status, headers = b"not found", 404, {}
        if self.path == "/robots.txt":
            body, status = b"User-agent: *\nDisallow: /private/\n", 200
        elif self.path in ("/doc.pdf", "/private/doc.pdf"):
            body, status = PDF, 200
        elif self.path == "/named":
            body, status, headers = PDF, 200, {"Content-Disposition": 'attachment; filename="TL072_model.zip"'}
        elif self.path == "/big":
            body, status = b"x" * 5000, 200
        elif self.path == "/flaky":
            type(self).flaky_hits += 1
            body, status = (b"busy", 503) if type(self).flaky_hits < 3 else (PDF, 200)
        elif self.path == "/page":
            body, status = b"<!DOCTYPE html><html><body>BC109</body></html>", 200
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def base():
    Handler.flaky_hits = 0
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


TRANSPORTS = ["requests", pytest.param("curl", marks=pytest.mark.skipif(not shutil.which("curl"), reason="no curl"))]


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_download_type_and_hash(base, transport):
    r = http.get(f"{base}/doc.pdf", transport=transport, delay=0)
    assert r.ok and r.kind == "pdf" and r.body == PDF and len(r.sha256) == 64
    assert http.get(f"{base}/page", transport=transport, delay=0).kind == "html"
    missing = http.get(f"{base}/nothing", transport=transport, delay=0)
    assert missing.status == 404 and not missing.ok and missing.attempts == 1          # a 404 is not retried


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_file_name_offered_by_the_server(base, transport):
    assert http.get(f"{base}/named", transport=transport, delay=0).disposition == "TL072_model.zip"


def test_robots_txt_is_honoured(base):
    r = http.get(f"{base}/private/doc.pdf", delay=0)
    assert r.status == 0 and r.why == "disallowed by robots.txt" and r.attempts == 0
    assert http.get(f"{base}/private/doc.pdf", delay=0, robots=False).ok


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_size_cap(base, transport):
    r = http.get(f"{base}/big", transport=transport, delay=0, max_bytes=1000)
    assert not r.ok and r.why == "larger than max_bytes" and r.body == b""


def test_retries_with_back_off_then_succeeds(base):
    r = http.get(f"{base}/flaky", delay=0)
    assert r.ok and r.attempts == 3


def test_gives_up(base):
    Handler.flaky_hits = -100
    r = http.get(f"{base}/flaky", delay=0, retries=2)
    assert not r.ok and r.status == 503 and "gave up" in r.why


def test_one_request_per_host_every_delay(base):
    http.get(f"{base}/doc.pdf", delay=0.4)
    t = time.time()
    http.get(f"{base}/doc.pdf", delay=0.4)
    assert time.time() - t >= 0.35


def test_contact_goes_in_the_user_agent_from_the_environment(monkeypatch):
    monkeypatch.delenv("PIDX_CONTACT", raising=False)
    assert "@" not in http.user_agent()
    monkeypatch.setenv("PIDX_CONTACT", "https://example.org/about")
    assert http.user_agent().endswith("(parts-index; https://example.org/about)") and http.user_agent(None) is None
