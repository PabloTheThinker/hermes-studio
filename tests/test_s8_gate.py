"""S8 engine mode gate (Prove C12 gate part, E5): Ask refuses agent writes even over plain MCP,
Propose parks them (needs_approval + pending_id, approval.pending), a person applies or skips
each exactly once, nothing ever resolves itself, and parked writes survive a restart."""

from __future__ import annotations

import json
import time

import pytest
from s3_app import App
from test_oplog import S, base

from hermes_studio import gate as G
from hermes_studio import oplog as O
from hermes_studio import project as P


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(base(), mode="propose")
    yield a
    a.close()


def marker(label: str = "m", at: int = 0) -> dict:
    return {"op": "add_marker", "at": at, "label": label}


def agent_apply(app: App, *ops, key: str, token: str | None = None, **extra) -> tuple[bool, dict]:
    args = {
        "project_id": "p1",
        "base_version": app.proj.log.version,
        "summary": "agent edit",
        "client_op_id": key,
        "ops": list(ops),
        **extra,
    }
    return app.mcp("timeline_apply", args, token)


def resolve(app: App, pid: str, decision: str = "apply", rest: bool = False, token: str | None = None) -> tuple[bool, dict]:
    return app.mcp(
        "approval_resolve", {"project_id": "p1", "pending_id": pid, "decision": decision, "rest": rest}, token or app.ui
    )


def test_default_mode_is_propose(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    d = P.create_project(base())
    assert G.mode_of(d) == "propose"
    assert P.ClosedProject("p1").status()["mode"] == "propose"


def test_c12_ask_mode_refuses_agent_writes_over_plain_mcp_and_rest(app):
    ok, r = app.mcp("set_mode", {"project_id": "p1", "mode": "ask"}, app.ui)
    assert ok and r == {"mode": "ask", "was": "propose"}
    h0 = app.head()
    ok, e = agent_apply(app, marker(), key="a1")
    assert not ok and e["code"] == "permission_denied"
    ok, e = app.rest_apply(marker())  # REST with the agent token
    assert not ok and e["code"] == "permission_denied"
    for tool, args in (("history_undo", {"op_id": "op-x"}), ("transcript_cut", {"fillers": True, "base_version": 0})):
        ok, e = app.mcp(tool, {"project_id": "p1", "client_op_id": "z", **args})
        assert not ok and e["code"] == "permission_denied", (tool, e)
    assert app.head() == h0
    ok, r = app.mcp_apply(marker("human"), token=app.ui)  # a person still edits in Ask mode
    assert ok and app.head()["version"] == 1
    ok, st = app.mcp("project_status", {"project_id": "p1"})
    assert ok and st["mode"] == "ask"


def test_c12_propose_parks_the_write(app):
    h0 = app.head()
    ok, e = agent_apply(app, marker(), key="p1")
    assert not ok and e["code"] == "needs_approval" and e["pending_id"].startswith("pend-")
    assert app.head() == h0 and app.proj.log._entries == []  # nothing logged, hash unchanged
    st, _, body = app.req(
        "POST",
        "/api/projects/p1/timeline_apply",
        {"base_version": 0, "summary": "s", "client_op_id": "rest1", "ops": [marker()]},
        app.agent,
    )
    assert st == 202 and body["code"] == "needs_approval"
    ok, lst = app.mcp("approval_list", {"project_id": "p1"})
    assert ok and lst["mode"] == "propose" and [p["state"] for p in lst["pending"]] == ["pending", "pending"]
    rec = lst["pending"][0]
    assert rec["actor"] == {"kind": "agent", "id": "claude"} and rec["summary"] == "agent edit" and rec["n_ops"] == 1
    assert "args" not in rec
    ok, again = agent_apply(app, marker(), key="p1")  # a retry is the same parked write
    assert not ok and again["pending_id"] == e["pending_id"]
    assert len(app.mcp("approval_list", {"project_id": "p1"})[1]["pending"]) == 2


def test_e5_apply_exactly_once_and_the_retry_gets_the_result(app):
    ok, e = agent_apply(app, marker(), key="k")
    pid = e["pending_id"]
    ok, r = resolve(app, pid)
    assert ok and r["resolved"]["state"] == "applied" and r["also"] == []
    res = r["resolved"]["result"]
    entry = app.proj.log._entries[-1]
    assert res["op_id"] == entry["op_id"] and entry["actor"] == {"kind": "agent", "id": "claude"} and app.head()["version"] == 1
    ok, r2 = resolve(app, pid, "skip")  # a late or repeated answer changes nothing
    assert ok and r2["resolved"]["state"] == "applied" and len(app.proj.log._entries) == 1
    ok, again = agent_apply(app, marker(), key="k", base_version=0)  # the agent's retry: the engine's cached result
    assert ok and again["op_id"] == res["op_id"] and len(app.proj.log._entries) == 1
    ok, st = app.mcp("approval_status", {"project_id": "p1", "pending_id": pid})
    assert ok and st["state"] == "applied" and st["result"]["op_id"] == res["op_id"]


def test_e5_skip_and_the_retry_says_skipped(app):
    ok, e = agent_apply(app, marker(), key="s")
    ok, r = resolve(app, e["pending_id"], "skip")
    assert ok and r["resolved"]["state"] == "skipped" and app.proj.log._entries == []
    ok, again = agent_apply(app, marker(), key="s")
    assert ok and again["status"] == "skipped" and again["pending_id"] == e["pending_id"]
    ok, r = resolve(app, e["pending_id"], "apply")
    assert ok and r["resolved"]["state"] == "skipped" and app.proj.log._entries == []


def test_e5_apply_the_rest_is_per_agent(app):
    other = app.eng.tokens.mint("mcp:cursor")
    pa = agent_apply(app, marker("a"), key="a")[1]["pending_id"]
    pb = agent_apply(app, marker("b", S), key="b")[1]["pending_id"]
    pc = agent_apply(app, marker("c", 2 * S), key="c", token=other)[1]["pending_id"]
    ok, r = resolve(app, pa, rest=True)
    assert ok and r["resolved"]["state"] == "applied" and [x["pending_id"] for x in r["also"]] == [pb]
    assert [x["state"] for x in r["also"]] == ["failed"]  # b was parked at version 0; a moved the head: conflict
    assert r["also"][0]["error"]["code"] == "conflict"
    ok, st = app.mcp("approval_status", {"project_id": "p1", "pending_id": pc})
    assert st["state"] == "pending"


def test_e5_a_human_edit_in_between_makes_apply_fail_with_conflict(app):
    pid = agent_apply(app, marker("agent"), key="x")[1]["pending_id"]
    ok, _ = app.mcp_apply(marker("human"), token=app.ui)
    assert ok
    ok, r = resolve(app, pid)
    assert ok and r["resolved"]["state"] == "failed" and r["resolved"]["error"]["code"] == "conflict"
    assert [e["actor"]["kind"] for e in app.proj.log._entries] == ["human"]  # the human's op stays; nothing else


def test_e5_nothing_resolves_itself(app):
    pid = agent_apply(app, marker(), key="t")[1]["pending_id"]
    time.sleep(0.5)
    ok, st = app.mcp("approval_status", {"project_id": "p1", "pending_id": pid})
    assert st["state"] == "pending" and app.proj.log._entries == []


def test_invalid_or_stale_writes_are_refused_not_parked(app):
    ok, e = agent_apply(app, {"op": "add_marker", "at": -1, "label": "m"}, key="bad")
    assert not ok and e["code"] == "invalid_op"
    ok, e = app.mcp(
        "timeline_apply", {"project_id": "p1", "base_version": 9, "summary": "s", "client_op_id": "st", "ops": [marker()]}
    )
    assert not ok and e["code"] == "conflict"
    assert app.mcp("approval_list", {"project_id": "p1"})[1]["pending"] == []


def test_only_a_person_resolves_or_sets_the_mode(app):
    pid = agent_apply(app, marker(), key="q")[1]["pending_id"]
    ok, e = resolve(app, pid, token=app.agent)
    assert not ok and e["code"] == "permission_denied"
    ok, e = app.mcp("set_mode", {"project_id": "p1", "mode": "auto"}, app.agent)
    assert not ok and e["code"] == "permission_denied"
    ok, e = app.mcp("set_mode", {"project_id": "p1", "mode": "auto"}, app.acp)  # Hermes over ACP is an agent too
    assert not ok and e["code"] == "permission_denied"
    assert app.proj.mode == "propose"


@pytest.mark.parametrize(
    "args, want",
    [
        ({"decision": "apply"}, ("missing_arg", "/pending_id")),
        ({"pending_id": "pend-0"}, ("missing_arg", "/decision")),
        ({"pending_id": "pend-0", "decision": "maybe"}, ("bad_arg", "/decision")),
        ({"pending_id": "pend-0", "decision": "apply", "rest": 1}, ("bad_arg", "/rest")),
        ({"pending_id": "pend-0", "decision": "apply", "zz": 1}, ("unknown_arg", "/zz")),
        ({"pending_id": "../../base", "decision": "apply"}, ("not_found", "/pending_id")),
    ],
)
def test_resolve_refusals(app, args, want):
    ok, e = app.mcp("approval_resolve", {"project_id": "p1", **args}, app.ui)
    assert not ok and (e["rule"], e["path"]) == want, e


def test_auto_applies_and_mode_persists_with_an_event(app):
    import http.client

    c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=10)
    c.request("GET", "/api/projects/p1/events", headers={"Host": f"127.0.0.1:{app.port}", "Authorization": f"Bearer {app.ui}"})
    resp = c.getresponse()
    ok, r = app.mcp("set_mode", {"project_id": "p1", "mode": "auto"}, app.ui)
    assert ok and json.loads((app.proj.dir / "mode.json").read_text()) == {"mode": "auto"}
    ok, r = agent_apply(app, marker(), key="auto1")
    assert ok and r["new_version"] == 1
    pid = None
    ok, _ = app.mcp("set_mode", {"project_id": "p1", "mode": "propose"}, app.ui)
    ok, e = agent_apply(app, marker("x", S), key="prop1")
    pid = e["pending_id"]
    seen = []
    while len(seen) < 4:
        line = resp.fp.readline().decode()
        if line.startswith("data: "):
            seen.append(json.loads(line[6:]))
    c.close()
    assert [x["type"] for x in seen] == ["mode.changed", "op.applied", "mode.changed", "approval.pending"]
    assert seen[-1]["pending_id"] == pid and "args" not in seen[-1]


def test_parked_writes_survive_a_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    P.create_project(base())
    agent = O.Session(O.Actor("agent", "claude"))
    eng = P.Engine(port=1)
    p = eng.open("p1")
    with pytest.raises(P.ToolError) as e:
        p.write(agent, "timeline_apply", {"base_version": 0, "summary": "s", "client_op_id": "r", "ops": [marker()]})
    pid = e.value.extra["pending_id"]
    eng.close()
    eng = P.Engine(port=2)
    p = eng.open("p1")
    assert [x["pending_id"] for x in G.listing(p, {})["pending"]] == [pid]
    out = G.resolve(p, O.Session(O.Actor("human", "user")), {"pending_id": pid, "decision": "apply"})
    assert out["resolved"]["state"] == "applied" and p.log.version == 1 and p.log._entries[-1]["actor"]["id"] == "claude"
    eng.close()


def test_transcript_cut_parks_as_one_edit(app):
    from hermes_studio import media as M

    M._write_json(
        M.cache_paths(app.proj.dir, "m1")["words"],
        {
            "words": [
                {"w": "so", "in": 0, "out": S // 4},
                {"w": "um", "in": S // 2, "out": 3 * S // 4},
                {"w": "yes", "in": S, "out": 5 * S // 4},
            ]
        },
    )
    ok, e = app.mcp("transcript_cut", {"project_id": "p1", "base_version": 0, "client_op_id": "cut", "fillers": True})
    assert not ok and e["code"] == "needs_approval"
    ok, r = resolve(app, e["pending_id"])
    assert ok and r["resolved"]["state"] == "applied" and len(app.proj.log._entries) == 1
    assert app.proj.log._entries[0]["summary"].startswith("Cut 1 filler")


def test_import_parks_then_builds_after_apply(app, tmp_path):
    import shutil

    if not shutil.which("ffmpeg"):
        pytest.skip("needs ffmpeg")
    from test_s4_media import make_video, wait_ready

    src = make_video(tmp_path / "v.mp4", seconds=2)
    ok, e = app.mcp("import_media", {"project_id": "p1", "path": str(src), "client_op_id": "imp", "stages": ["wave"]})
    assert not ok and e["code"] == "needs_approval"
    assert "m3" not in app.proj.log.doc["media"]
    ok, r = resolve(app, e["pending_id"])
    assert ok and r["resolved"]["state"] == "applied" and "m3" in app.proj.log.doc["media"]
    st = wait_ready(app, "m3")
    assert st["state"] == "ready" and set(st["stages"]) == {"wave"}


def test_preview_says_what_apply_would_do(app):
    pid = agent_apply(app, {"op": "delete_clip", "id": "c3", "ripple": False}, key="pv")[1]["pending_id"]
    h0 = app.head()
    ok, st = app.mcp("approval_status", {"project_id": "p1", "pending_id": pid, "preview": True})
    assert ok and st["state"] == "pending", st
    pv = st["preview"]
    assert pv["would_apply"] and pv["changed_ids"] == ["c3"] and pv["length_s"] == 8.0 and "  c3 " not in pv["outline"]
    assert app.head() == h0 and app.proj.log._entries == []  # a preview writes nothing
    ok, plain = app.mcp("approval_status", {"project_id": "p1", "pending_id": pid})
    assert ok and "preview" not in plain
    st_code, _, rest = app.req("GET", f"/api/projects/p1/approvals/{pid}?preview=1", token=app.ui)
    assert st_code == 200 and rest["preview"] == pv
    ok, _ = app.mcp_apply(marker("human"), token=app.ui)  # now Apply would meet a conflict, and the preview says so
    ok, st = app.mcp("approval_status", {"project_id": "p1", "pending_id": pid, "preview": True})
    assert ok and not st["preview"]["would_apply"] and st["preview"]["error"]["code"] == "conflict"
    resolve(app, pid, "skip")
    ok, st = app.mcp("approval_status", {"project_id": "p1", "pending_id": pid, "preview": True})
    assert ok and st["state"] == "skipped" and "preview" not in st
    ok, e = app.mcp("approval_status", {"project_id": "p1", "pending_id": pid, "preview": "yes"})
    assert not ok and (e["rule"], e["path"]) == ("bad_arg", "/preview")
