"""Desk guards: host allow-list, same-origin writes, JSON-only POSTs, loopback bind, outbound URL schemes."""
import io
import json

import pytest

from hermes_studio import studio
from hermes_studio.net import BlockedURL, check_url


def test_host_allow_list():
    for ok in ("127.0.0.1:3870", "localhost:3870", "[::1]:3870", "box.tail123.ts.net", "box.tail123.ts.net:3870"):
        assert studio.host_allowed(ok), ok
    for bad in (None, "", "evil.com", "127.0.0.1.evil.com", "attacker.localhost.evil:3870"):
        assert not studio.host_allowed(bad), bad


def test_extra_hosts_env(monkeypatch):
    monkeypatch.setenv("HERMES_STUDIO_ALLOWED_HOSTS", "studio.lan")
    assert studio.host_allowed("studio.lan:3870")


def test_origin_must_match_host():
    assert studio.origin_ok(None, "127.0.0.1:3870")
    assert studio.origin_ok("http://127.0.0.1:3870", "127.0.0.1:3870")
    assert not studio.origin_ok("https://evil.com", "127.0.0.1:3870")
    assert not studio.origin_ok("null", "127.0.0.1:3870")


def test_refuses_public_bind(monkeypatch):
    monkeypatch.delenv("HERMES_STUDIO_ALLOW_REMOTE", raising=False)
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


def test_job_ids_and_clip_names_are_slugs():
    from hermes_studio.pipeline import safe_clip_file, safe_job_id

    assert safe_job_id("3da7b951a6b8") and safe_job_id("abc_12-x")
    for bad in ("", "../x", "a/b", ".hidden", "*", "a[1]", "x" * 80):
        assert not safe_job_id(bad), bad
    assert safe_clip_file("clip-01.mp4") and safe_clip_file("Why Mars (part 2).mp4")
    for bad in ("", "../clip.mp4", "a/b.mp4", ".x.mp4", "clip..mp4"):
        assert not safe_clip_file(bad), bad


def test_local_sources_must_be_media(tmp_path, monkeypatch):
    from hermes_studio.download import local_source

    monkeypatch.setenv("HERMES_STUDIO_MEDIA_ROOTS", str(tmp_path))

    vid = tmp_path / "talk.mp4"
    vid.write_bytes(b"x")
    assert local_source(str(vid)) == vid.resolve()
    key = tmp_path / "id_rsa"
    key.write_text("secret")
    for bad in (str(key), "/etc/passwd", str(tmp_path / "missing.mp4")):
        with pytest.raises((ValueError, FileNotFoundError)):
            local_source(bad)


def test_desk_rejects_non_media_sources(tmp_path):
    assert studio.check_src("https://www.youtube.com/watch?v=x") is None
    assert studio.check_src("/etc/passwd")
    assert studio.check_src("file:///etc/passwd")
    assert studio.check_src("ftp://x/y.mp4")


def test_platform_hosts_are_exact():
    from hermes_studio.download import kind_of

    assert kind_of("https://www.youtube.com/watch?v=x") == "youtube"
    assert kind_of("https://m.twitch.tv/x") == "twitch"
    assert kind_of("https://evil-youtube.com/x") == "url"
    assert kind_of("https://youtube.com.evil.net/x") == "url"


def test_local_sources_must_live_under_a_media_root(tmp_path, monkeypatch):
    import os

    from hermes_studio.download import local_source

    monkeypatch.delenv("HERMES_STUDIO_MEDIA_ROOTS", raising=False)
    outside = tmp_path / "clip.mp4"
    outside.write_bytes(b"x")
    if str(tmp_path).startswith(os.path.expanduser("~")):
        return  # tmp inside home on this machine; covered by the symlink case below
    with pytest.raises(ValueError):
        local_source(str(outside))


def test_symlink_out_of_roots_is_refused(tmp_path, monkeypatch):
    from hermes_studio.download import local_source

    root = tmp_path / "media"
    root.mkdir()
    secret = tmp_path / "secret.mp4"
    secret.write_bytes(b"x")
    (root / "link.mp4").symlink_to(secret)
    monkeypatch.setenv("HERMES_STUDIO_MEDIA_ROOTS", str(root))
    monkeypatch.setattr("hermes_studio.download.Path.home", staticmethod(lambda: root))
    import hermes_studio.pipeline as pl
    monkeypatch.setattr(pl, "library_root", lambda: root)
    with pytest.raises(ValueError):
        local_source(str(root / "link.mp4"))
