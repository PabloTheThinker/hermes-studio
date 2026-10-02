"""Test 103: HTTP body refusals (S3-SPEC D27(d)/(e)): one header check, one response, then a close."""

from __future__ import annotations

import json
import re
import socket

import pytest
from s3_app import App
from test_oplog import base

from hermes_studio import studio
from hermes_studio.jsonrpc import MAX_BODY

STATUS = re.compile(rb"HTTP/1\.[01] (\d{3})")
SMUGGLE = b"GET /api/doctor HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(base())
    yield a
    a.close()


def exchange(app: App, raw: bytes, *, timeout: float = 5) -> tuple[list[int], bytes, bool]:
    """Send raw bytes; return the status codes seen, the bytes, and whether the server closed."""
    s = socket.create_connection(("127.0.0.1", app.port), timeout=timeout)
    s.sendall(raw)
    got, closed = b"", False
    try:
        while True:
            chunk = s.recv(65536)
            if not chunk:
                closed = True
                break
            got += chunk
    except TimeoutError:
        pass
    except ConnectionResetError:
        closed = True
    s.close()
    return [int(m) for m in STATUS.findall(got)], got, closed


def head(app: App, path: str, headers: list[str], token: str | None = None) -> bytes:
    lines = [f"POST {path} HTTP/1.1", f"Host: 127.0.0.1:{app.port}", "Content-Type: application/json"]
    if token:
        lines.append(f"Authorization: Bearer {token}")
    return ("\r\n".join(lines + headers) + "\r\n\r\n").encode()


def body_of(got: bytes) -> dict:
    return json.loads(got.split(b"\r\n\r\n", 1)[1])


BAD = [["Content-Length: abc"], ["Content-Length: -1"], ["Content-Length: +5"], ["Content-Length: 1_000"],
       ["Content-Length: \u0663"], ["Content-Length: 100000000"], ["Content-Length: 5", "Content-Length: 5"],
       ["Content-Length: 5", "Content-Length: 7"], ["Content-Length: 0x5"]]
TE = [["Transfer-Encoding: chunked"], ["Transfer-Encoding: chunked", "Content-Length: 5"], ["Transfer-Encoding: identity"]]


def encode(headers: list[str]) -> list[str]:
    return [h.encode("utf-8").decode("latin-1") for h in headers]  # the raw UTF-8 bytes on the wire


@pytest.mark.parametrize("route", ["/api/restyle", "/api/projects/p1/timeline_apply"])
@pytest.mark.parametrize("headers, why", [(h, "invalid content length") for h in BAD]
                         + [(["Content-Length: 1048577"], "request body too large")]
                         + [(h, "unsupported transfer encoding") for h in TE])
def test_103_rest_refusals_one_response_then_close(app, route, headers, why):
    raw = head(app, route, encode(headers), app.agent) + SMUGGLE + SMUGGLE
    codes, got, closed = exchange(app, raw)
    assert codes == [400] and closed, got  # the embedded /api/doctor never runs
    assert body_of(got) == {"ok": False, "error": why}
    assert b"\r\nConnection: close\r\n" in got


@pytest.mark.parametrize("headers", BAD + [["Content-Length: 1048577"]] + TE)
def test_103_http_mcp_refusals(app, headers):
    raw = head(app, "/mcp", encode(headers), app.agent) + SMUGGLE + SMUGGLE
    codes, got, closed = exchange(app, raw)
    assert codes == [400] and closed, got
    assert body_of(got) == {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
    assert b"\r\nConnection: close\r\n" in got


def test_103_iii_exact_cap_is_accepted_and_the_connection_stays_up(app):
    msg = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    pad = MAX_BODY - len(json.dumps({**msg, "p": ""}).encode())
    body = json.dumps({**msg, "p": "x" * pad}).encode()
    assert len(body) == MAX_BODY == studio.MAX_BODY
    second = (f"GET /api/projects/p1/hash HTTP/1.1\r\nHost: 127.0.0.1:{app.port}\r\nAuthorization: Bearer {app.ui}\r\n"
              "Connection: close\r\n\r\n").encode()
    codes, got, closed = exchange(app, head(app, "/mcp", [f"Content-Length: {MAX_BODY}"], app.agent) + body + second)
    assert codes == [200, 200], got
    rbody = {"ok": False}
    rest = head(app, "/api/projects/p1/timeline_apply", [f"Content-Length: {MAX_BODY}"], app.agent)
    pad = MAX_BODY - len(json.dumps({**rbody, "p": ""}).encode())
    codes, got, _ = exchange(app, rest + json.dumps({**rbody, "p": "x" * pad}).encode() + second)
    assert len(codes) == 2 and codes[1] == 200 and codes[0] == 400, got  # the engine's answer, then the next request


def test_103_iv_no_content_length_reads_as_empty(app):
    second = f"GET /api/projects/p1/hash HTTP/1.1\r\nHost: 127.0.0.1:{app.port}\r\nAuthorization: Bearer {app.ui}\r\nConnection: close\r\n\r\n".encode()
    codes, got, _ = exchange(app, head(app, "/api/projects/p1/timeline_apply", [], app.agent) + second)
    assert len(codes) == 2 and codes[1] == 200
    first = got.split(b"HTTP/1.1 200")[0]
    assert json.loads(first.split(b"\r\n\r\n", 1)[1])["path"] == "/base_version"  # the body was {} and reached the engine


def test_103_header_check_is_shared():
    from hermes_studio.jsonrpc import content_length

    assert content_length(b" \t00000007\t ") == (7, "")
    for v in (b"000000007", b"-1", b"+5", b"1_000", b"abc", b"", b"  ", "\u0663".encode(), b"5\r", b"5\x0b", b"5\x0c"):
        assert content_length(v)[0] is None, v
