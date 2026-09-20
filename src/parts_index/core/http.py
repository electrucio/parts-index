"""The one polite HTTP client. Every crawler, downloader and model fetcher goes through `get()`.

What "polite" means here, for every request regardless of who asks:
  * robots.txt is honoured (`robots=False` only for a vendor file a person is pointed to by the vendor's own page);
  * one request per host every `delay` seconds, longer after a large file, much longer after 429/5xx;
  * a size cap, a timeout, and at most `retries` attempts;
  * never a CAPTCHA, login, paywall or click-through licence: a page that asks for one is recorded as blocked.

Two transports with the same result type: "requests" (default) and "curl". Some vendor sites answer curl and refuse
everything else, so model fetch adapters choose it explicitly; nothing else differs.

A contact address for the User-Agent comes from $PIDX_CONTACT (never from the code).
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlparse

BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
DELAY = 3.0                 # seconds between two requests to one host
BIG, BIG_DELAY = 5 << 20, 20.0
MAX_BYTES = 120 << 20
RETRY_STATUS = (0, 429, 500, 502, 503, 504)
MAGIC = {b"%PDF": "pdf", b"GIF8": "gif", b"\xff\xd8\xff": "jpeg", b"\x89PNG": "png", b"II*\x00": "tiff", b"MM\x00*": "tiff",
         b"PK\x03\x04": "zip"}

_next_ok: dict[str, float] = {}             # host -> earliest time of the next request
_robots: dict[tuple[str, str], robotparser.RobotFileParser] = {}


def user_agent(base: str | None = BROWSER_UA) -> str | None:
    contact = os.environ.get("PIDX_CONTACT")
    if base is None:
        return None                          # curl's own default
    return f"{base} (parts-index; {contact})" if contact else base


@dataclass
class Response:
    status: int
    url: str                                 # after redirects
    ctype: str = ""
    body: bytes = b""
    disposition: str = ""                    # file name offered by the server
    why: str = ""                            # reason when there is no usable body
    attempts: int = 1
    _sha: str = field(default="", repr=False)

    @property
    def ok(self) -> bool:
        return self.status == 200 and not self.why

    @property
    def sha256(self) -> str:
        if not self._sha:
            self._sha = hashlib.sha256(self.body).hexdigest()
        return self._sha

    @property
    def kind(self) -> str:
        """pdf, gif, jpeg, png, tiff, zip by magic bytes; html by sniffing; else ''."""
        for magic, kind in MAGIC.items():
            if self.body.startswith(magic):
                return kind
        head = self.body[:600].lstrip().lower()
        return "html" if head.startswith((b"<!doctype html", b"<html")) or b"<html" in head else ""

    def text(self, limit: int | None = None) -> str:
        return self.body[:limit].decode("utf-8", "replace")


def wait_turn(host: str) -> None:
    pause = _next_ok.get(host, 0) - time.time()
    if pause > 0:
        time.sleep(pause)


def allowed(url: str, ua: str | None = BROWSER_UA) -> bool:
    u = urlparse(url)
    key = (u.scheme, u.netloc)
    if key not in _robots:
        rp = robotparser.RobotFileParser()
        r = _once(f"{u.scheme}://{u.netloc}/robots.txt", ua, 20, None, True, 1 << 20, "requests")
        looks_like_robots = r.status == 200 and "<html" not in r.text(300).lower()
        rp.parse(r.text().splitlines() if looks_like_robots else [])
        _robots[key] = rp
    return _robots[key].can_fetch("*", url)


def get(url: str, *, ua: str | None = BROWSER_UA, transport: str = "requests", robots: bool = True, delay: float = DELAY,
        timeout: float = 120, max_bytes: int = MAX_BYTES, referer: str | None = None, follow: bool = True,
        retries: int = 4) -> Response:
    host = urlparse(url).netloc
    if robots and not allowed(url, ua):
        return Response(0, url, why="disallowed by robots.txt", attempts=0)
    resp = Response(0, url, why="not tried")
    for attempt in range(1, retries + 1):
        wait_turn(host)
        resp = _once(url, ua, timeout, referer, follow, max_bytes, transport)
        resp.attempts = attempt
        _next_ok[host] = time.time() + (BIG_DELAY if len(resp.body) > BIG else delay)
        if resp.status not in RETRY_STATUS or resp.why == "larger than max_bytes":
            return resp
        _next_ok[host] = time.time() + max(delay, 0.01) * 10 * attempt       # back off: 30 s, 60 s, 90 s at the default delay
    resp.why = resp.why or f"gave up after {retries} attempts ({resp.status})"
    return resp


def _once(url, ua, timeout, referer, follow, max_bytes, transport) -> Response:
    ua = user_agent(ua)
    return _curl(url, ua, timeout, referer, follow, max_bytes) if transport == "curl" else _requests(url, ua, timeout, referer, follow, max_bytes)


def _requests(url, ua, timeout, referer, follow, max_bytes) -> Response:
    import requests
    headers = {k: v for k, v in (("User-Agent", ua), ("Referer", referer)) if v}
    try:
        with requests.get(url, headers=headers, timeout=(20, timeout), stream=True, allow_redirects=follow) as r:
            body = b""
            for chunk in r.iter_content(1 << 16):
                body += chunk
                if len(body) > max_bytes:
                    return Response(r.status_code, r.url, r.headers.get("content-type", ""), why="larger than max_bytes")
            return Response(r.status_code, r.url, r.headers.get("content-type", ""), body,
                            _file_name(r.headers.get("content-disposition", "")))
    except requests.RequestException as e:
        return Response(0, url, why=type(e).__name__)


def _curl(url, ua, timeout, referer, follow, max_bytes) -> Response:
    if not shutil.which("curl"):
        return Response(0, url, why="curl is not installed")
    with tempfile.TemporaryDirectory(prefix="pidx_http_") as tmp:
        body, hdr = Path(tmp) / "body", Path(tmp) / "headers"
        cmd = ["curl", "-sSL" if follow else "-sS", "--compressed", "-m", str(int(timeout)), "-o", str(body), "-D", str(hdr),
               "--max-filesize", str(max_bytes), "-w", "%{http_code}\t%{url_effective}\t%{content_type}"]
        cmd += ["-A", ua] if ua else []
        cmd += ["-e", referer] if referer else []
        p = subprocess.run(cmd + [url], capture_output=True, text=True)
        code, eff, ctype = (p.stdout.split("\t") + ["", "", ""])[:3]
        if p.returncode == 63:
            return Response(int(code or 0), eff or url, ctype, why="larger than max_bytes")
        headers = hdr.read_text(errors="replace") if hdr.exists() else ""
        data = body.read_bytes() if body.exists() else b""
        why = "" if p.returncode == 0 else f"curl exit {p.returncode}"
        return Response(int(code or 0) if p.returncode == 0 else 0, eff or url, ctype, data, _file_name(headers), why)


def _file_name(headers: str) -> str:
    for line in headers.splitlines() or [headers]:
        low = line.lower()
        if "content-disposition" in low or "filename" in low or ("content-type:" in low and "name=" in low):
            m = re.search(r'name\*?="?([^";]+)', line)
            if m:
                return m.group(1).strip()
    return ""
