"""Desk guards: host allow-list, same-origin writes, JSON-only POSTs, loopback bind, outbound URL schemes."""
import io
import json

import pytest

from hermesclip import studio
from hermesclip.net import BlockedURL, check_url


def test_host_allow_list():
    for ok in ("127.0.0.1:3870", "localhost:3870", "[::1]:3870", "box.tail123.ts.net", "box.tail123.ts.net:3870"):
        assert studio.host_allowed(ok), ok
    for bad in (None, "", "evil.com", "127.0.0.1.evil.com", "attacker.localhost.evil:3870"):
        assert not studio.host_allowed(bad), bad


def test_extra_hosts_env(monkeypatch):
    monkeypatch.setenv("HERMESCLIP_ALLOWED_HOSTS", "studio.lan")
    assert studio.host_allowed("studio.lan:3870")


def test_origin_must_match_host():
    assert studio.origin_ok(None, "127.0.0.1:3870")
    assert studio.origin_ok("http://127.0.0.1:3870", "127.0.0.1:3870")
    assert not studio.origin_ok("https://evil.com", "127.0.0.1:3870")
    assert not studio.origin_ok("null", "127.0.0.1:3870")


def test_refuses_public_bind(monkeypatch):
    monkeypatch.delenv("HERMESCLIP_ALLOW_REMOTE", raising=False)
    with pytest.raises(SystemExit):
        studio.serve("0.0.0.0", 0)


def test_outbound_urls_are_http_only():
    assert check_url("https://api.x.ai/v1/chat/completions")
    assert check_url("http://127.0.0.1:11434/api/chat")
    for bad in ("file:///etc/passwd", "ftp://x/y", "gopher://x", "", "https//nohost"):
        with pytest.raises(BlockedURL):
            check_url(bad)


class _Fake(studio.StudioHandler):
    """Drive the handler without a socket."""

    def __init__(self, method, path, headers, body=b""):
        self.command, self.path, self.request_version = method, path, "HTTP/1.1"
        self.headers = headers
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.close_connection = False
        self.requestline = f"{method} {path} HTTP/1.1"
        self.client_address = ("127.0.0.1", 0)

    def status(self):
        return int(self.wfile.getvalue().split(b" ", 2)[1])

    def raw(self):
        return self.wfile.getvalue()


def _h(**kw):
    from email.message import Message

    m = Message()
    for k, v in kw.items():
        m[k.replace("_", "-")] = v
    return m


def test_rebinding_host_is_refused():
    h = _Fake("GET", "/api/jobs", _h(Host="evil.com"))
    h.do_GET()
    assert h.status() == 421


def test_cross_site_post_is_refused():
    body = json.dumps({"src": "x"}).encode()
    h = _Fake("POST", "/api/jobs", _h(Host="127.0.0.1:3870", Origin="https://evil.com",
                                     Content_Type="application/json", Content_Length=str(len(body))), body)
    h.do_POST()
    assert h.status() == 403


def test_form_post_is_refused():
    body = b"src=x"
    h = _Fake("POST", "/api/jobs", _h(Host="127.0.0.1:3870", Content_Type="text/plain", Content_Length=str(len(body))), body)
    h.do_POST()
    assert h.status() == 415


def test_oversized_body_is_refused():
    h = _Fake("POST", "/api/jobs", _h(Host="127.0.0.1:3870", Content_Type="application/json",
                                     Content_Length=str(studio.MAX_BODY + 1)), b"{}")
    h.do_POST()
    assert h.status() == 400


def test_security_headers_on_every_answer():
    h = _Fake("GET", "/nope", _h(Host="127.0.0.1:3870"))
    h.do_GET()
    raw = h.raw()
    for k in (b"Content-Security-Policy", b"X-Frame-Options: DENY", b"X-Content-Type-Options: nosniff"):
        assert k in raw


def test_media_path_traversal_is_refused():
    assert studio._safe_media("x", "../../etc/passwd") is None
    assert studio._safe_media("../x", "clip.mp4") is None
    assert studio._safe_media("x", ".hidden.mp4") is None
