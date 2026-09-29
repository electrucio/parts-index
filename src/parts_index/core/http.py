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
# The names a site uses to address what this is. robots.txt is how a site says who may read it, and a
# site that writes a rule for `anthropic-ai` or `Claude-User` has written it about this, whatever the
# User-Agent header happens to say. Checking only the `*` group reads half the file and the wrong half:
# wiki.analog.com allows `*` everything but /_export/ and disallows every one of these outright, and
# `allowed()` answered True until 2026-09-25.
AI_AGENTS = ("anthropic-ai", "ClaudeBot", "Claude-Web", "Claude-User", "Claude-SearchBot")
DELAY = 3.0                 # seconds between two requests to one host
BIG, BIG_DELAY = 5 << 20, 20.0
MAX_WAIT = 600.0            # the longest we will honour a Retry-After for, so one header cannot stall a run
MAX_BYTES = 120 << 20
RETRY_STATUS = (0, 429, 500, 502, 503, 504)
MAGIC = {b"%PDF": "pdf", b"GIF8": "gif", b"\xff\xd8\xff": "jpeg", b"\x89PNG": "png", b"II*\x00": "tiff", b"MM\x00*": "tiff",
         b"PK\x03\x04": "zip"}
# A BMP opens with only "BM" and then its sizes, too little to trust alone; the header that follows says
# how long it is, and there are only these few lengths. hifisonix drew the e-Amp of 2011 in BMPs.
BMP_HEADERS = (12, 40, 52, 56, 64, 108, 124)

_next_ok: dict[str, float] = {}             # host -> earliest time of the next request
_robots: dict[tuple[str, str], robotparser.RobotFileParser] = {}
_trusted: dict[str, str] = {}               # host -> CA bundle that also holds the intermediate it omits


def trust(host: str, bundle: str) -> None:
    """Verify `host` against `bundle`. For a server that sends its certificate without the intermediate
    that signed it: the bundle is the usual roots plus that intermediate, fetched from the address the
    certificate itself names — what a browser does. Verification is never turned off."""
    _trusted[host] = bundle


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
    retry_after: float = 0                   # seconds the server asked us to wait, from its own header
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
        """pdf, gif, jpeg, png, tiff, zip by magic bytes; bmp, html and CAD by sniffing; else ''."""
        for magic, kind in MAGIC.items():
            if self.body.startswith(magic):
                return kind
        if self.body[:2] == b"BM" and int.from_bytes(self.body[14:18], "little") in BMP_HEADERS:
            return "bmp"
        head = self.body[:600].lstrip()
        low = head.lower()
        if low.startswith((b"<!doctype html", b"<html")) or b"<html" in low:
            return "html"
        # A schematic in its own format. Sniffed rather than taken from the extension, because `.sch`
        # belongs to EAGLE and to KiCad before version 6 both. See schematics/cad.py.
        if head.startswith(b"(kicad_sch"):
            return "kicad_sch"
        if head.startswith(b"EESchema Schematic File"):
            return "kicad_legacy"
        if b"<eagle" in self.body[:2000]:
            return "eagle_brd" if b"<board" in self.body[:20000] else "eagle_sch"
        if re.match(rb"v\s+\d{8}\s+\d", head) and b"\nC " in self.body[:20000]:
            return "geda_sch"           # gEDA/gschem, and a `.sch` too
        # LTspice and SPICE netlists are text too, and may be UTF-16 or CP932; the CAD module says which.
        if head.startswith((b"Version 4", b"\xff\xfeV\x00", b"V\x00e\x00")) or head[:1] in b"*.RCLQDJMXVI" \
                or head[:2] in (b"\xff\xfe",):
            from parts_index.schematics import cad
            found = cad.kind_of(cad._text(self.body[:200000]))
            if found in ("ltspice_asc", "spice_net"):
                return found
        return ""

    def text(self, limit: int | None = None) -> str:
        return self.body[:limit].decode("utf-8", "replace")


def wait_turn(host: str) -> None:
    pause = _next_ok.get(host, 0) - time.time()
    if pause > 0:
        time.sleep(pause)


def allowed(url: str, ua: str | None = BROWSER_UA) -> bool:
    """Whether robots.txt lets this read that URL — asked of every name that describes this, not just `*`.

    A rule written for `Claude-User` is a rule about an AI agent fetching at a person's request, which is
    what this is, and it holds whatever the User-Agent header says. So the answer is no if any of the
    names says no.
    """
    u = urlparse(url)
    key = (u.scheme, u.netloc)
    if key not in _robots:
        rp = robotparser.RobotFileParser()
        r = _once(f"{u.scheme}://{u.netloc}/robots.txt", ua, 20, None, True, 1 << 20, "requests")
        looks_like_robots = r.status == 200 and "<html" not in r.text(300).lower()
        rp.parse(r.text().splitlines() if looks_like_robots else [])
        _robots[key] = rp
    return all(_robots[key].can_fetch(agent, url) for agent in ("*", *AI_AGENTS))


def get(url: str, *, ua: str | None = BROWSER_UA, transport: str = "requests", robots: bool = True, delay: float = DELAY,
        timeout: float = 120, max_bytes: int = MAX_BYTES, referer: str | None = None, follow: bool = True,
        retries: int = 4, headers: dict[str, str] | None = None) -> Response:
    """`headers` is for an API that asks for them — an Accept type, a bearer token. Everything else here
    has no business setting them, and a header that changes who we appear to be is not one of these."""
    host = urlparse(url).netloc
    if robots and not allowed(url, ua):
        return Response(0, url, why="disallowed by robots.txt", attempts=0)
    resp = Response(0, url, why="not tried")
    for attempt in range(1, retries + 1):
        wait_turn(host)
        resp = _once(url, ua, timeout, referer, follow, max_bytes, transport, headers)
        resp.attempts = attempt
        _next_ok[host] = time.time() + (BIG_DELAY if len(resp.body) > BIG else delay)
        if resp.status not in RETRY_STATUS or resp.why == "larger than max_bytes":
            return resp
        # 429 is the server saying in words what a 5xx only implies. When it names a wait, that is the
        # wait — arguing with it by retrying sooner is how a polite client gets itself blocked.
        _next_ok[host] = time.time() + (resp.retry_after or max(delay, 0.01) * 10 * attempt)
    resp.why = resp.why or f"gave up after {retries} attempts ({resp.status})"
    return resp


def _once(url, ua, timeout, referer, follow, max_bytes, transport, headers=None) -> Response:
    ua = user_agent(ua)
    return (_curl(url, ua, timeout, referer, follow, max_bytes) if transport == "curl"
            else _requests(url, ua, timeout, referer, follow, max_bytes, headers))


def _retry_after(value: str) -> float:
    """What the server asked for, in seconds. A date is allowed there too; we only read the number."""
    try:
        return max(0.0, min(float(value.strip()), MAX_WAIT))
    except ValueError:
        return 0.0


def _requests(url, ua, timeout, referer, follow, max_bytes, extra=None) -> Response:
    import requests
    headers = {k: v for k, v in (("User-Agent", ua), ("Referer", referer)) if v} | (extra or {})
    try:
        with requests.get(url, headers=headers, timeout=(20, timeout), stream=True, allow_redirects=follow,
                          verify=_trusted.get(urlparse(url).netloc, True)) as r:
            body = b""
            for chunk in r.iter_content(1 << 16):
                body += chunk
                if len(body) > max_bytes:
                    return Response(r.status_code, r.url, r.headers.get("content-type", ""), why="larger than max_bytes")
            return Response(r.status_code, r.url, r.headers.get("content-type", ""), body,
                            _file_name(r.headers.get("content-disposition", "")),
                            retry_after=_retry_after(r.headers.get("retry-after", "")))
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
