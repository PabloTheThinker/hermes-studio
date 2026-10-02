"""The engine's HTTP surface (S3): HTTP /mcp, the project REST routes and the SSE feed.

Auth is ``Authorization: Bearer <token>`` (D13); a missing or unknown token is 401 before
anything else is read. Bodies are the same as /mcp's (D25 status codes, D26 read routes).
Every refusal of a request body closes the connection (D27(d)).
"""

from __future__ import annotations

import json
import queue
import re
import threading
from typing import Any
from urllib.parse import parse_qs

from hermes_studio import __version__
from hermes_studio import mcp_timeline as MT
from hermes_studio import project as P
from hermes_studio.api import HermesStudioError
from hermes_studio.jsonrpc import PARSE_ERROR, dumps, parse_message
from hermes_studio.studio import MAX_BODY, BodyRefused, body_length, no_body

ENGINE: P.Engine | None = None
UI_TOKEN: str | None = None  # minted at start; how the Edit page receives it is not in S3
KEEPALIVE_SEC = 15
STATUS = {
    "invalid_op": 400,
    "schema_mismatch": 400,
    "bad_input": 400,
    "not_found": 404,
    "conflict": 409,
    "undo_blocked": 409,
    "invalid_doc": 422,
    "permission_denied": 403,
    "engine_offline": 503,
    "needs_approval": 202,
    "failed": 500,
}
_QUERY_INT = re.compile(r"\A(0|[1-9][0-9]*)\Z")  # ASCII only (D26)
WRITE_ROUTES = ("timeline_apply", "history_undo", "history_redo")


def start(port: int) -> P.Engine:
    """Start the timeline engine for the app on ``port``: open (and lock) every project."""
    global ENGINE, UI_TOKEN
    engine = P.Engine(port=port)
    engine.open_all()  # a project held by another engine is a startup error (D6)
    UI_TOKEN = engine.tokens.mint("ui")
    ENGINE = engine
    return engine


def stop(engine: P.Engine) -> None:
    global ENGINE
    engine.close()  # deletes every .attach (D14) and releases the locks
    if ENGINE is engine:
        ENGINE = None


# --------------------------------------------------------------------------- helpers


def _send(h: Any, code: int, body: bytes, ctype: str = "application/json; charset=utf-8", *, close: bool = False) -> None:
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-store")
    if close:
        h.send_header("Connection", "close")
    h.end_headers()
    h.wfile.write(body)
    if close:
        h.close_connection = True


def _json(h: Any, code: int, payload: Any) -> None:
    _send(h, code, json.dumps(payload).encode("utf-8"))


def _error(h: Any, e: HermesStudioError) -> None:
    _json(h, STATUS.get(e.code, 500), e.as_dict())


def _token(h: Any) -> P.Token | None:
    auth = h.headers.get_all("Authorization") or []
    if len(auth) != 1 or not auth[0].startswith("Bearer ") or ENGINE is None:
        return None
    return ENGINE.tokens.resolve(auth[0][len("Bearer ") :].strip())


def _unauthorized(h: Any) -> None:
    h._refuse(401, "missing or unknown token")


def _denied(scope: str) -> P.ToolError:
    return P.ToolError("permission_denied", f"this token has no '{scope}' scope")


def _query_value(v: str) -> Any:
    if _QUERY_INT.fullmatch(v):
        try:
            return int(v)
        except ValueError:  # more digits than int() takes: the engine says bad_arg (D26)
            return v
    return v


def _history_args(query: str) -> dict:
    qs = parse_qs(query, keep_blank_values=True)
    out: dict[str, Any] = {}
    for k in ("since_version", "limit"):
        if k in qs:
            vals = [_query_value(v) for v in qs[k]]
            out[k] = vals[0] if len(vals) == 1 else vals
    return out


# --------------------------------------------------------------------------- GET


def get(h: Any, segs: list[str], query: str) -> None:
    """GET /mcp or /api/projects/<id>/...; ``segs`` is the path split on '/', each segment
    decoded once. D27(d): any body framing is refused before routing, nothing read."""
    is_mcp = segs == ["", "mcp"]
    try:
        no_body(h)
    except BodyRefused as exc:
        return _mcp_refuse(h) if is_mcp else h._refuse(400, str(exc))
    tok = _token(h)
    if tok is None:
        return _unauthorized(h)
    if is_mcp:
        return _mcp_stream(h, tok)
    pid, rest = segs[3], segs[4:]  # a decoded '/' stays inside its segment, so it never matches a route
    if "read" not in tok.scopes or tok.session is None:
        return _error(h, _denied("read"))
    try:
        proj = ENGINE.get(pid)
        if rest == ["events"]:
            return _events(h, proj)
        if rest == ["status"]:
            return _json(h, 200, proj.status())
        with proj.mutex:
            log = proj.oplog()
            if rest == ["hash"]:
                body = log.head()
            elif rest == ["history"]:
                body = log.history_list(**_history_args(query))
            elif rest == ["history", "diff"]:
                body = log.history_diff(**_history_args(query))
            else:
                return _json(h, 404, {"ok": False, "error": "unknown project route"})
        return _json(h, 200, body)
    except HermesStudioError as e:
        return _error(h, e)


def _sse_head(h: Any) -> None:
    h.send_response(200)
    h.send_header("Content-Type", "text/event-stream; charset=utf-8")
    h.send_header("Cache-Control", "no-store")
    h.send_header("Connection", "close")
    h.end_headers()
    h.close_connection = True


def _events(h: Any, proj: P.Project) -> None:
    """D11: SSE ids are log seqs; Last-Event-ID n replays seq > n, then goes live."""
    raw = h.headers.get_all("Last-Event-ID") or []
    last = None
    if raw:
        if len(raw) != 1 or not _QUERY_INT.fullmatch(raw[0].strip(" \t")) or len(raw[0].strip(" \t")) > 4000:
            return h._refuse(400, "Last-Event-ID must be a whole number")
        last = int(raw[0].strip(" \t"))
    sub, replay, reset = proj.subscribe(last)
    try:
        _sse_head(h)
        if reset is not None:
            h.wfile.write(_sse(None, "stream.reset", {"type": "stream.reset", "head_seq": reset}))
        for ev in replay:
            h.wfile.write(_sse(ev["seq"], ev["type"], ev))
        h.wfile.flush()
        while not sub.dropped.is_set():
            try:
                ev = sub.q.get(timeout=KEEPALIVE_SEC)
            except queue.Empty:
                h.wfile.write(b": keepalive\n\n")
                h.wfile.flush()
                continue
            h.wfile.write(_sse(ev["seq"], ev["type"], ev))
            h.wfile.flush()
    except OSError:
        pass
    finally:
        proj.unsubscribe(sub)


def _sse(seq: int | None, event: str, data: dict) -> bytes:
    head = f"id: {seq}\n" if seq is not None else ""
    return (head + f"event: {event}\ndata: " + json.dumps(data, ensure_ascii=True) + "\n\n").encode("ascii")


def _mcp_stream(h: Any, tok: P.Token) -> None:
    """GET /mcp: server-to-client notifications (D12): resources/updated for every new entry."""
    if "read" not in tok.scopes:
        return _error(h, _denied("read"))
    q: queue.Queue = queue.Queue(maxsize=P.EVENT_QUEUE_MAX)
    dropped = threading.Event()

    def listen(ev: dict) -> None:
        try:
            q.put_nowait(ev["project_id"])
        except queue.Full:
            dropped.set()

    ENGINE.listen(listen)  # every project, including ones opened after the stream connected
    try:
        _sse_head(h)
        h.wfile.flush()
        while not dropped.is_set():
            try:
                pid = q.get(timeout=KEEPALIVE_SEC)
            except queue.Empty:
                h.wfile.write(b": keepalive\n\n")
                h.wfile.flush()
                continue
            note = {"jsonrpc": "2.0", "method": "notifications/resources/updated", "params": {"uri": f"timeline://{pid}"}}
            h.wfile.write(b"event: message\ndata: " + dumps(note) + b"\n\n")
            h.wfile.flush()
    except OSError:
        pass
    finally:
        ENGINE.unlisten(listen)


# --------------------------------------------------------------------------- REST writes


def rest_post(h: Any, segs: list[str]) -> None:
    """POST /api/projects/<id>/<timeline_apply|history_undo|history_redo>: the JSON body goes to
    the engine as received; the actor is the token's (never the body's)."""
    tok = _token(h)
    if tok is None:
        return _unauthorized(h)
    parts = segs[3:]  # [id, route], each already decoded
    if len(parts) != 2 or parts[1] not in WRITE_ROUTES:
        return _refuse_unread(h, 404, "unknown project route")
    n = body_length(h)  # raises BodyRefused (handled by do_POST)
    if n > MAX_BODY:
        raise BodyRefused("request body too large")
    raw = h.rfile.read(n) if n else b"{}"  # no body reads as {}, like the other REST routes
    ok, body = parse_message(raw)
    if not ok:
        raise ValueError("invalid JSON body")
    if tok.session is None or "write" not in tok.scopes:
        return _error(h, _denied("write"))
    try:
        proj = ENGINE.get(parts[0])
        return _json(h, 200, proj.write(tok.session, parts[1], body))
    except HermesStudioError as e:
        return _error(h, e)


def _refuse_unread(h: Any, code: int, why: str) -> None:
    h._refuse(code, why)


# --------------------------------------------------------------------------- HTTP /mcp


def _mcp_refuse(h: Any) -> None:
    _send(h, 400, dumps(PARSE_ERROR), "application/json", close=True)


def mcp_post(h: Any) -> None:
    """POST /mcp: one JSON-RPC message per request. Body refusals and unparseable bodies get
    400 with -32700 (id null) and a closed connection (D27(d)/(e))."""
    try:
        n = body_length(h)
    except BodyRefused:
        return _mcp_refuse(h)
    if n > MAX_BODY:
        return _mcp_refuse(h)
    tok = _token(h)
    if tok is None:
        return _unauthorized(h)
    raw = h.rfile.read(n) if n else b""
    ok, msg = parse_message(raw)
    if not ok:
        return _mcp_refuse(h)
    from hermes_studio.mcp import check_request

    bad, params = check_request(msg)
    if bad is not None:
        if not bad:  # a notification with bad params: no reply
            return _send(h, 202, b"", "application/json")
        return _send(h, 400 if bad["error"]["code"] == -32600 else 200, dumps(bad), "application/json")
    mid, method = msg.get("id"), msg["method"]
    if "id" not in msg:  # a notification: accepted, no reply
        return _send(h, 202, b"", "application/json")
    reply = _dispatch(tok, mid, method, params)
    return _send(h, 200, dumps(reply), "application/json")


def _dispatch(tok: P.Token, mid: Any, method: str, params: dict) -> dict:
    def ok(result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def err(code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}

    if method == "initialize":
        from hermes_studio.mcp import PROTOCOLS

        asked = str(params.get("protocolVersion") or "")
        return ok(
            {
                "protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {"listChanged": False}, "resources": {"subscribe": True, "listChanged": False}},
                "serverInfo": {"name": "hermes-studio-engine", "title": "Hermes Studio engine", "version": __version__},
            }
        )
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": MT.TOOLS})
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or name not in MT.BY_NAME:
            return err(-32602, f"Unknown tool: {name}")
        if "arguments" in params and not isinstance(params["arguments"], dict):
            return err(-32602, "arguments must be an object")
        args = params.get("arguments", {})
        if tok.session is None:
            return ok(MT.as_result(None, _denied("read")))
        return ok(MT.call(name, args, MT.EngineBackend(ENGINE, tok.session, tok.scopes)))
    if method == "resources/list":
        return ok(
            {
                "resources": [
                    {"uri": f"timeline://{p}", "name": p, "mimeType": "application/json"} for p in sorted(ENGINE.projects)
                ]
            }
        )
    if method == "resources/read":
        uri = params.get("uri")
        if not (isinstance(uri, str) and uri.startswith("timeline://")) or tok.session is None:
            return err(-32602, "unknown resource uri")
        res = MT.call(
            "get_timeline", {"project_id": uri[len("timeline://") :]}, MT.EngineBackend(ENGINE, tok.session, tok.scopes)
        )
        text = res["content"][-1]["text"]
        if res["isError"]:
            return {
                "jsonrpc": "2.0",
                "id": mid,
                "error": {"code": -32002, "message": "Resource not found", "data": json.loads(text)},
            }
        return ok({"contents": [{"uri": uri, "mimeType": "application/json", "text": text}]})
    if method in ("resources/subscribe", "resources/unsubscribe"):
        return ok({})  # updates go out on the GET /mcp stream
    if method == "prompts/list":
        return ok({"prompts": []})
    return err(-32601, f"Method not found: {method}")
