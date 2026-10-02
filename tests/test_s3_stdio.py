"""S3 stdio /mcp: D27 framing (tests 101, 102), D15, D17, D28 and the attached C5 path (test 94)."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time

import pytest
from s3_app import App
from test_oplog import S, base
from test_s3_mcp import c5_calls, strip_ids

from hermes_studio import studio
from hermes_studio.jsonrpc import DRAIN_CHUNK, DRAIN_MAX, MAX_BODY

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSE = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}


class Stdio:
    def __init__(self, home) -> None:
        env = {**os.environ, "HOME": str(home), "PYTHONPATH": ROOT}
        self.p = subprocess.Popen(
            [sys.executable, "-c", "from hermes_studio import mcp; raise SystemExit(mcp.serve())"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=ROOT,
        )
        self.q: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        f = self.p.stdout
        while True:
            line = f.readline()
            if not line:
                self.q.put(None)
                return
            if line.lower().startswith(b"content-length:"):
                n = int(line.split(b":")[1])
                while f.readline() not in (b"\r\n", b"\n", b""):
                    pass
                self.q.put(json.loads(f.read(n)))
            elif line.strip():
                self.q.put(json.loads(line))

    def send(self, raw: bytes) -> None:
        self.p.stdin.write(raw)
        self.p.stdin.flush()

    def frame(self, msg, *, length: str | None = None) -> bytes:
        body = msg if isinstance(msg, bytes) else json.dumps(msg).encode()
        return f"Content-Length: {length if length is not None else len(body)}\r\n\r\n".encode() + body

    def get(self, timeout: float = 20):
        return self.q.get(timeout=timeout)

    def none_within(self, t: float = 0.5) -> bool:
        try:
            self.q.get(timeout=t)
            return False
        except queue.Empty:
            return True

    def finish(self, timeout: float = 30) -> tuple[list, int, str]:
        try:
            self.p.stdin.close()
        except OSError:
            pass
        rc = self.p.wait(timeout=timeout)
        rest = []
        while True:
            m = self.get()
            if m is None:
                break
            rest.append(m)
        return rest, rc, self.p.stderr.read().decode()

    def kill(self) -> None:
        if self.p.poll() is None:
            self.p.kill()
        self.p.wait()


def ping(i: int) -> dict:
    return {"jsonrpc": "2.0", "id": i, "method": "ping"}


def pong(i: int) -> dict:
    return {"jsonrpc": "2.0", "id": i, "result": {}}


@pytest.fixture
def sess(tmp_path):
    made = []

    def make():
        s = Stdio(tmp_path)
        made.append(s)
        return s

    yield make
    for s in made:
        s.kill()


def test_101_one_source_for_the_numbers():
    assert MAX_BODY == studio.MAX_BODY == 1048576 and DRAIN_MAX == 16 * MAX_BODY and DRAIN_CHUNK == 64 * 1024


def test_101_newline_framing_bad_lines_never_crash(sess):
    s = sess()
    s.send(b"9" * 5000 + b"\n" + b"\xff\n" + json.dumps(ping(1)).encode() + b"\n")
    assert [s.get(), s.get(), s.get()] == [PARSE, PARSE, pong(1)]
    rest, rc, _ = s.finish()
    assert rest == [] and rc == 0


def test_101_1_bad_json_body_keeps_framing(sess):
    s = sess()
    s.send(s.frame(b"{nope") + s.frame(ping(1)))
    assert [s.get(), s.get()] == [PARSE, pong(1)]
    assert s.finish()[1] == 0


def test_101_2_exactly_max_body_is_accepted(sess):
    s = sess()
    msg = ping(2)
    raw = json.dumps(msg).encode()
    pad = MAX_BODY - len(raw) - len(', "pad": ""')
    body = json.dumps({**msg, "pad": "x" * pad}).encode()
    assert len(body) == MAX_BODY
    s.send(s.frame(body) + s.frame(ping(3)))
    assert [s.get(), s.get()] == [pong(2), pong(3)]
    assert s.finish()[1] == 0


@pytest.mark.parametrize("n", [MAX_BODY + 1, DRAIN_MAX])
def test_101_3_4_over_cap_answered_first_then_drained(sess, n):
    s = sess()
    s.send(f"Content-Length: {n}\r\n\r\n".encode() + b"x" * 1000)  # write end left open
    assert s.get() == PARSE  # before the client finishes the body
    embedded = s.frame(ping(10))
    left = n - 1000
    s.send(embedded + b"y" * (left - len(embedded)))  # a framed ping inside the body: drained, never scanned
    s.send(s.frame(ping(11)))
    assert s.get() == pong(11)
    rest, rc, _ = s.finish()
    assert rest == [] and rc == 0


@pytest.mark.parametrize(
    "value",
    [str(DRAIN_MAX + 1), "100000000", "000000007", "-1", "+5", "1_000", "abc", "  ", "\u0663", "5\x0b", "5\r", "0x10", ""],
)
def test_101_5_6_7_broken_stream_closes(sess, value):
    s = sess()
    s.send(
        b"Content-Length: " + value.encode() + b"\r\n\r\n" + b'{"a":1}' + s.frame(ping(5)) + json.dumps(ping(6)).encode() + b"\n"
    )
    assert s.get() == PARSE
    rest, rc, err = s.finish()
    assert rest == [] and rc != 0 and "broken Content-Length framing" in err


def test_101_eight_digits_read_by_value(sess):
    s = sess()
    s.send(b'Content-Length: 00000007\r\n\r\n{"a":1}')
    assert s.get() == {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    body = json.dumps(ping(4)).encode()
    s.send(f"Content-Length: \t{len(body):08d} \t\r\n\r\n".encode() + body)
    assert s.get() == pong(4)
    assert s.finish()[1] == 0


EMBED = (
    b"Content-Length: 40\r\n\r\n"
    + json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "doctor", "arguments": {}}}).encode()
    + b"\n"
    + json.dumps({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "doctor", "arguments": {}}}).encode()
    + b"\n"
)


@pytest.mark.parametrize(
    "headers",
    [
        b"Content-Length: -1\r\n",
        b"Content-Length: +5\r\n",
        b"Content-Length: 1_000\r\n",
        b"Content-Length: abc\r\n",
        b"Content-Length: 5\r\nContent-Length: 5\r\n",
        b"Content-Length: 5\r\nContent-Length: 7\r\n",
        b"Content-Length: 5\r\ncontent-length: 5\r\n",
        # the addendum's second list: empty, whitespace-only, a non-ASCII digit, stray \r / \v, over 8 digits
        b"Content-Length:\r\n",
        b"Content-Length: \t \r\n",
        "Content-Length: \u0663\r\n".encode(),
        b"Content-Length: 5\r\r\n",
        b"Content-Length: 5\x0b\r\n",
        b"Content-Length: 000000005\r\n",
        b"Content-Length: 16777217\r\n",
        b"Content-Length: 5\r\nX-Other: 1\r\nContent-Length: 5\r\n",
    ],
)
def test_102_a_malformed_or_duplicate_headers_close_and_nothing_embedded_runs(sess, headers):
    s = sess()
    s.send(headers + b"\r\n" + EMBED)
    assert s.get() == PARSE
    rest, rc, err = s.finish()
    assert rest == [] and rc != 0 and "broken" in err


@pytest.mark.parametrize("gap", [b"\r\n", b"\n", b"\r\n\r\n", b" \r\n"])
def test_102_a_blank_line_between_frames_is_a_malformed_header(sess, gap):
    """Ada 8:29 PM: in Content-Length mode nothing between frames is skipped, blank lines included."""
    s = sess()
    s.send(s.frame(ping(1)) + gap + s.frame(ping(5)) + json.dumps(ping(6)).encode() + b"\n")
    assert [s.get(), s.get()] == [pong(1), PARSE]
    rest, rc, err = s.finish()
    assert rest == [] and rc != 0 and "broken Content-Length framing" in err


def test_102_b_over_drain_bound_closes(sess):
    s = sess()
    s.send(
        f"Content-Length: {DRAIN_MAX + 1}\r\n\r\n".encode() + s.frame({"jsonrpc": "2.0", "id": 9, "method": "ping"}) + b"z" * 5000
    )
    assert s.get() == PARSE
    rest, rc, _ = s.finish()
    assert rest == [] and rc != 0


def test_102_b2_newline_line_over_cap_closes_unparsed(sess):
    """O1: a newline-framed read takes at most MAX_BODY + 1 bytes; a longer line is never parsed."""
    s = sess()
    msg = json.dumps(ping(3)).encode()
    s.send(msg + b" " * (MAX_BODY + 1 - len(msg)) + b"\n" + json.dumps(ping(4)).encode() + b"\n")
    assert s.get() == PARSE  # not pong(3): the over-long line was never parsed
    rest, rc, err = s.finish()
    assert rest == [] and rc != 0 and f"line over {MAX_BODY} bytes" in err


def test_102_b2_newline_line_at_cap_is_read(sess):
    s = sess()
    msg = json.dumps(ping(3)).encode()
    s.send(msg + b" " * (MAX_BODY - len(msg)) + b"\n" + json.dumps(ping(4)).encode() + b"\n")
    assert [s.get(), s.get()] == [pong(3), pong(4)]
    rest, rc, _ = s.finish()
    assert rest == [] and rc == 0


def test_102_b_drained_body_is_not_scanned(sess):
    s = sess()
    inner = s.frame(ping(10))
    body = inner + b" " * (MAX_BODY + 1 - len(inner))
    s.send(f"Content-Length: {MAX_BODY + 1}\r\n\r\n".encode() + body + s.frame(ping(11)))
    assert [s.get(), s.get()] == [PARSE, pong(11)]
    rest, rc, _ = s.finish()
    assert rest == [] and rc == 0


def test_102_c_too_short_length_leftovers_close(sess):
    s = sess()
    s.send(b'Content-Length: 5\r\n\r\n{"a":1}Content-Length: 40\r\n\r\n' + json.dumps(ping(7)).encode() + b"\n")
    assert [s.get(), s.get()] == [PARSE, PARSE]  # '{"a":' doesn't parse; '1}Content-Length' isn't a header
    rest, rc, _ = s.finish()
    assert rest == [] and rc != 0
    s = sess()
    s.send(b"Content-Length: 2\r\n\r\n{}" + json.dumps(ping(7)).encode() + b"\r\n")
    assert s.get() == {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}  # D15 first
    assert s.get() == PARSE
    rest, rc, _ = s.finish()
    assert rest == [] and rc != 0


def test_102_limit_leftovers_that_form_a_real_frame_run(sess):
    s = sess()
    s.send(b"Content-Length: 2\r\n\r\n{}" + s.frame(ping(8)))
    assert s.get()["error"]["code"] == -32600 and s.get() == pong(8)
    assert s.finish()[1] == 0


def test_d15_request_shapes(sess):
    s = sess()
    for raw in (b"[1]", b"5", b'{"jsonrpc":"2.0","id":1}', b'{"jsonrpc":"2.0","id":2,"method":5}'):
        s.send(raw + b"\n")
        assert s.get() == {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    s.send(b'{"jsonrpc":"2.0","id":3,"method":"ping","params":5}\n')
    assert s.get() == {"jsonrpc": "2.0", "id": 3, "error": {"code": -32602, "message": "params must be an object"}}
    s.send(b'{"jsonrpc":"2.0","method":"ping","params":[]}\n')  # a notification: no reply
    assert s.none_within(0.5)
    s.send(b'{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"get_hash","arguments":5}}\n')
    assert s.get()["error"]["code"] == -32602
    s.send(b'{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"get_hash"}}\n')
    r = s.get()["result"]
    assert r["isError"] and json.loads(r["content"][-1]["text"])["path"] == "/project_id"
    assert s.finish()[1] == 0


def test_d17_output_is_ascii(sess):
    s = sess()
    s.send(b'{"jsonrpc":"2.0","id":"\\ud800\xc3\xa9","method":"ping"}\n')
    assert s.get() == {"jsonrpc": "2.0", "id": "\ud800\u00e9", "result": {}}
    assert s.finish()[1] == 0


# --------------------------------------------------------------------------- D28: closed app, attached app, test 94


def call(s: Stdio, i: int, name: str, args: dict) -> tuple[bool, dict]:
    s.send(
        json.dumps({"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}).encode()
        + b"\n"
    )
    r = s.get()
    assert r["id"] == i, r
    r = r["result"]
    return (not r["isError"]), json.loads(r["content"][-1]["text"])


def test_d28_closed_app_reads_and_refuses_writes(tmp_path, monkeypatch, sess):
    monkeypatch.setenv("HOME", str(tmp_path))
    from hermes_studio import project as P

    P.create_project(base())
    s = sess()
    ok, h = call(s, 1, "get_hash", {"project_id": "p1"})
    assert ok and h["version"] == 0
    ok, st = call(s, 2, "project_status", {"project_id": "p1"})
    assert ok and st["engine"] is None
    ok, e = call(
        s,
        3,
        "timeline_apply",
        {
            "project_id": "p1",
            "base_version": 0,
            "summary": "s",
            "client_op_id": "k",
            "ops": [{"op": "add_marker", "at": 0, "label": "m"}],
        },
    )
    assert not ok and e["code"] == "engine_offline"
    ok, e = call(s, 4, "get_hash", {"project_id": "nope"})
    assert not ok and e["code"] == "not_found"
    s.send(b'{"jsonrpc":"2.0","id":5,"method":"resources/list"}\n')
    assert s.get()["result"]["resources"] == [{"uri": "timeline://p1", "name": "p1", "mimeType": "application/json"}]
    assert s.finish()[1] == 0


def test_94_c5_over_attached_stdio_matches_http(tmp_path, monkeypatch, sess):
    monkeypatch.setenv("HOME", str(tmp_path))
    app = App(base())
    try:
        s = sess()
        n = iter(range(100, 10**6))

        def send(tool, args):
            ok, r = call(s, next(n), tool, {"project_id": "p1", **args})
            assert ok, r
            return r

        out = c5_calls(app, send)
        r1, r2, u, rd = out
        w = lambda r: [(x["code"], x["path"]) for x in r["warnings"]]  # noqa: E731
        assert w(r1) == w(r2) == [("ignored_field", "/actor"), ("ignored_field", "/ops/0/step")] and r1["op_id"] == r2["op_id"]
        assert w(u) == w(rd) == [("ignored_field", "/step")]
        raw = (app.proj.dir / "oplog.jsonl").read_text()
        assert '"x"' not in raw and "human" not in raw
        for line in raw.splitlines():  # the attach token's agent; MCP sessions have no plan step (§4 transport table)
            e = json.loads(line)
            assert e["actor"] == {"kind": "agent", "id": "stdio"} and e.get("step") is None
            assert all("step" not in op for op in e["ops"])
        ok, h = call(s, 1, "get_hash", {"project_id": "p1"})
        assert ok and h == app.head()
        s.send(b'{"jsonrpc":"2.0","id":2,"method":"resources/subscribe","params":{"uri":"timeline://p1"}}\n')
        assert s.get() == {"jsonrpc": "2.0", "id": 2, "result": {}}
        time.sleep(0.5)
        app.mcp_apply({"op": "add_marker", "at": 5 * S, "label": "b"})
        note = s.get()
        assert note == {"jsonrpc": "2.0", "method": "notifications/resources/updated", "params": {"uri": "timeline://p1"}}
        s.finish()
    finally:
        app.close()
    monkeypatch.setenv("HOME", str(tmp_path / "http"))
    ref = App(base())
    try:

        def rest(tool, args):
            ok, r = ref.rest(tool, args, ref.acp)
            assert ok, r
            return r

        assert strip_ids(c5_calls(ref, rest)) == strip_ids(out)  # identical results across the paths
    finally:
        ref.close()
