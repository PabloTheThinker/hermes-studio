"""Shared S3 fixture: a real engine behind a real StudioHandler on a free loopback port."""

from __future__ import annotations

import http.client
import itertools
import json
import threading
from http.server import ThreadingHTTPServer

from hermes_studio import http_engine, studio
from hermes_studio import oplog as O
from hermes_studio import project as P

_keys = itertools.count(1)


def key(e: dict) -> tuple:
    """What tests 88-100 compare between /mcp and HTTP."""
    return (e.get("code"), e.get("rule"), e.get("path"), e.get("op_index"), "id" in e, e.get("id"))


class App:
    def __init__(self, base_doc: dict, mode: str = "auto") -> None:
        d = P.create_project(base_doc)
        # S8: Propose is the engine default; the S3-S7 contract tests predate the gate and expect
        # agent writes to apply, so the harness opens projects in Auto unless a test asks otherwise.
        (d / "mode.json").write_text(json.dumps({"mode": mode}))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), studio.StudioHandler)
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        self.eng = http_engine.start(self.port)
        self.ui = http_engine.UI_TOKEN
        self.agent = self.eng.tokens.mint("mcp:claude")
        self.acp = self.eng.tokens.mint("acp:hermes", plan=O.PlanContext(3))
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()
        http_engine.stop(self.eng)

    @property
    def proj(self) -> P.Project:
        return self.eng.projects["p1"]

    def head(self) -> dict:
        return self.proj.log.head()

    def req(self, method: str, path: str, body=None, token: str | None = None, headers: dict | None = None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        h = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        h.update(headers or {})
        data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        out = r.read()
        c.close()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, (json.loads(out) if out else None)

    def rpc(self, method: str, params: dict | None = None, token: str | None = None, mid=1):
        msg = {"jsonrpc": "2.0", "id": mid, "method": method}
        if params is not None:
            msg["params"] = params
        return self.req("POST", "/mcp", msg, token or self.agent)

    def mcp(self, name: str, args: dict, token: str | None = None) -> tuple[bool, dict]:
        st, _, j = self.rpc("tools/call", {"name": name, "arguments": args}, token)
        assert st == 200, (st, j)
        res = j["result"]
        if res["isError"]:
            return False, json.loads(res["content"][-1]["text"])
        return True, res["structuredContent"]

    def rest(self, tool: str, body: dict, token: str | None = None) -> tuple[bool, dict]:
        st, _, j = self.req("POST", f"/api/projects/p1/{tool}", body, token or self.agent)
        return st == 200, j

    def apply_args(self, *ops: dict, **extra) -> dict:
        args = {"base_version": self.proj.log.version, "ops": list(ops), "summary": "edit", "client_op_id": f"t{next(_keys)}"}
        args.update(extra)
        return args

    def mcp_apply(self, *ops: dict, token: str | None = None, **extra) -> tuple[bool, dict]:
        return self.mcp("timeline_apply", {"project_id": "p1", **self.apply_args(*ops, **extra)}, token)

    def rest_apply(self, *ops: dict, token: str | None = None, **extra) -> tuple[bool, dict]:
        return self.rest("timeline_apply", self.apply_args(*ops, **extra), token)
