"""S3: the project store, lock, tokens and event bus (S3-SPEC §1-§3, D1-D14, D19, D28; C3/C4/C7/C8),
and the engine changes (§4 C5 rules 1-5 / test 93, D4, D10, D19, the conflict cap)."""

from __future__ import annotations

import json
import os
import stat
import threading

import pytest
from test_oplog import HUMAN, S, base, hermes, new_log

from hermes_studio import oplog as O
from hermes_studio import project as P
from hermes_studio import timeline as T


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def marker(i: int, at: int | None = None) -> dict:
    return {"op": "add_marker", "at": (i + 3) * S if at is None else at, "label": f"m{i}"}


def write(p: P.Project, session: O.Session, *ops: dict, key: str, **extra) -> dict:
    args = {"base_version": p.log.version, "ops": list(ops), "summary": "edit", "client_op_id": key, **extra}
    return p.write(session, "timeline_apply", args)


def opened(eng: P.Engine | None = None, pid: str = "p1") -> tuple[P.Engine, P.Project]:
    eng = eng or P.Engine(port=4242)
    return eng, eng.open(pid)


def tree(d) -> dict:
    out = {}
    for root, _dirs, files in os.walk(d):
        for f in files:
            pth = os.path.join(root, f)
            st = os.stat(pth)
            out[pth] = (open(pth, "rb").read(), st.st_mtime_ns)
    return out


# --------------------------------------------------------------------------- engine changes


def test_93_c5_retry_returns_cache_plus_its_own_strip_warnings_live_and_after_load(tmp_path):
    path = tmp_path / "oplog.jsonl"
    log = new_log(path=path)
    forged = {"base_version": 0, "ops": [{"op": "add_marker", "at": 3 * S, "label": "a", "step": 9}], "summary": "s",
              "client_op_id": "k", "actor": {"kind": "human", "id": "x"}}
    a = log.call(hermes(3), "timeline_apply", forged)
    want = ["/actor", "/ops/0/step"]
    assert [w["path"] for w in a["warnings"]] == want and all(w["code"] == "ignored_field" for w in a["warnings"])
    clean = {k: v for k, v in forged.items() if k != "actor"}
    clean["ops"] = [{k: v for k, v in forged["ops"][0].items() if k != "step"}]
    other_step = json.loads(json.dumps(forged))
    other_step["ops"][0]["step"] = 2

    def same(r, paths):
        assert {k: v for k, v in r.items() if k != "warnings"} == {k: v for k, v in a.items() if k != "warnings"}
        assert [w["path"] for w in r["warnings"]] == paths

    same(log.call(hermes(3), "timeline_apply", forged), want)  # (i)
    same(log.call(hermes(3), "timeline_apply", clean), [])  # (ii) dropped: none
    same(log.call(hermes(3), "timeline_apply", other_step), want)  # (iii)
    b_args = {"base_version": 1, "ops": [marker(1)], "summary": "b", "client_op_id": "c"}
    b = log.call(hermes(3), "timeline_apply", b_args)
    assert b["warnings"] == []
    rb = log.call(hermes(3), "timeline_apply", {**b_args, "actor": {"kind": "agent", "id": "z"}})  # (iv)
    assert [w["path"] for w in rb["warnings"]] == ["/actor"] and rb["op_id"] == b["op_id"]
    u_args = {"client_op_id": "u", "op_id": b["op_id"], "step": 7}
    u = log.call(hermes(3), "history_undo", u_args)
    assert [w["path"] for w in u["warnings"]] == ["/step"]
    raw = path.read_bytes()
    assert b"warnings" not in raw and b'"x"' not in raw  # S3 lines stay byte-identical to the old format
    again = O.Oplog.load(base(), path)
    same(again.call(hermes(3), "timeline_apply", forged), want)  # (v)
    same(again.call(hermes(3), "timeline_apply", clean), [])  # (vii)
    rb2 = again.call(hermes(3), "timeline_apply", {**b_args, "actor": {"kind": "agent", "id": "z"}})  # (viii)
    assert [w["path"] for w in rb2["warnings"]] == ["/actor"] and rb2["op_id"] == b["op_id"]
    ru = again.call(hermes(3), "history_undo", u_args)  # (vi)
    assert [w["path"] for w in ru["warnings"]] == ["/step"] and ru["op_id"] == u["op_id"]
    assert path.read_bytes() == raw and len(again._entries) == 3


def test_stored_result_warnings_line_key_shape():
    line = json.loads(json.dumps(O.Oplog(base())._entries))  # []
    assert line == []
    good = {k: None for k in O.LINE_FIELDS}
    O._check_line(good)
    O._check_line({**good, "warnings": [{"code": "future", "path": "/ops/0", "message": "m"}]})
    for bad in ([], [{"code": "ignored_field", "path": "", "message": "m"}], [{"code": "x"}], "x", [5]):
        with pytest.raises(ValueError, match="not an oplog line"):
            O._check_line({**good, "warnings": bad})


def test_d4_non_string_project_id_is_bad_arg_with_no_id():
    log = new_log()
    for pid in (5, None, True, []):
        with pytest.raises(O.OplogError) as e:
            log.call(HUMAN, "timeline_apply", {"base_version": 0, "ops": [marker(0)], "summary": "s", "client_op_id": "k", "project_id": pid})
        d = e.value.as_dict()
        assert (d["code"], d["rule"], d["path"]) == ("invalid_op", "bad_arg", "/project_id") and "id" not in d
    with pytest.raises(O.OplogError) as e:
        log.call(HUMAN, "timeline_apply", {"base_version": 0, "ops": [marker(0)], "summary": "s", "client_op_id": "k", "project_id": "zz"})
    assert e.value.as_dict()["id"] == "zz" and e.value.code == "not_found"


def test_d10_d19_history_pages_and_records_carry_hash():
    log = new_log()
    for i in range(7):
        log.call(HUMAN, "timeline_apply", {"base_version": i, "ops": [marker(i)], "summary": "s", "client_op_id": f"k{i}"})
    page = log.history_list(since_version=0, limit=3)
    assert [e["seq"] for e in page["entries"]] == [1, 2, 3] and page["next_since_version"] == 3 and page["head_version"] == 7
    assert log.history_list(since_version=6)["next_since_version"] is None
    assert log.history_list(since_version=99) == {"entries": [], "next_since_version": None, "head_version": 7}
    assert len(log.history_list()["entries"]) == 7
    d = log.history_diff(since_version=5)
    assert [r["new_version"] for r in d["records"]] == [6, 7] and d["records"][-1]["hash"] == log.doc["hash"]
    assert set(d["records"][0]) == {"seq", "op_id", "group_id", "actor", "summary", "base_version", "new_version", "hash", "changed_ids", "undoes"}
    cases = [
        ("history_list", {"since_version": "5"}, "bad_arg", "/since_version"),
        ("history_list", {"since_version": None}, "bad_arg", "/since_version"),
        ("history_list", {"since_version": -1}, "bad_arg", "/since_version"),
        ("history_list", {"since_version": True}, "bad_arg", "/since_version"),
        ("history_list", {"since_version": 1.5}, "bad_arg", "/since_version"),
        ("history_list", {"limit": 0}, "bad_arg", "/limit"),
        ("history_list", {"limit": 201}, "bad_arg", "/limit"),
        ("history_diff", {"since_version": 0, "limit": 501}, "bad_arg", "/limit"),
        ("history_diff", {}, "missing_arg", "/since_version"),
        ("history_diff", {"zz": 1}, "unknown_arg", "/zz"),
        ("history_list", {"since_version": "x", "limit": "y"}, "bad_arg", "/since_version"),
    ]
    for tool, args, rule, path in cases:
        with pytest.raises(O.OplogError) as e:
            getattr(log, tool)(**args)
        dd = e.value.as_dict()
        assert (dd["code"], dd["rule"], dd["path"]) == ("invalid_op", rule, path) and "id" not in dd, (tool, args)
    assert log.history_diff(since_version=0, limit=500)["next_since_version"] is None


def test_conflict_cap_and_truncated_flag():
    log = new_log()
    for i in range(205):
        log.call(HUMAN, "timeline_apply", {"base_version": i, "ops": [marker(i)], "summary": "s", "client_op_id": f"k{i}"})
    with pytest.raises(O.OplogError) as e:
        log.call(HUMAN, "timeline_apply", {"base_version": 0, "ops": [marker(999)], "summary": "s", "client_op_id": "x"})
    d = e.value.as_dict()
    assert len(d["history_diff"]) == 200 and d["history_diff_truncated"] is True and d["history_diff"][-1]["new_version"] == 200
    assert list(d).index("history_diff_truncated") == list(d).index("history_diff") + 1
    with pytest.raises(O.OplogError) as e:
        log.call(HUMAN, "timeline_apply", {"base_version": 204, "ops": [marker(999)], "summary": "s", "client_op_id": "y"})
    assert e.value.as_dict()["history_diff_truncated"] is False and len(e.value.as_dict()["history_diff"]) == 1


def test_head_is_one_read():
    log = new_log()
    log.call(HUMAN, "timeline_apply", {"base_version": 0, "ops": [marker(0)], "summary": "s", "client_op_id": "k"})
    assert log.head() == {"project_id": "p1", "schema_version": T.SCHEMA_VERSION, "version": 1, "hash": log.doc["hash"], "seq": 1}


def test_check_op_args_steps_and_anchor_keys():
    assert O.check_op_args({"op": "add_marker", "at": 0, "label": "x"}, 0) is None
    e = O.check_op_args(5, 2).as_dict()
    assert (e["rule"], e["path"], e["op_index"]) == ("bad_arg", "/ops/2", 2)
    assert O.check_op_args({"op": "zz"}, 0).as_dict()["rule"] == "unknown_op"
    e = O.check_op_args({"op": "set_anchor", "id": "x1", "anchor": {"to": "c2", "zz": 1}}, 0).as_dict()
    assert (e["rule"], e["path"]) == ("unknown_arg", "/ops/0/anchor/zz") and "id" not in e and "problems" not in e
    e = O.check_op_args({"op": "add_text", "dur": S, "text": "a", "style": "pop", "anchor": {}}, 1).as_dict()
    assert (e["rule"], e["path"], e["op_index"]) == ("missing_arg", "/ops/1/anchor/offset", 1)
    assert O.check_op_args({"op": "set_anchor", "id": "x1", "anchor": None, "at": 0}, 0) is None
    assert O.check_op_args({"op": "set_anchor", "id": "x1", "anchor": 5}, 0) is None
    assert O.check_op_args({"op": "set_anchor", "id": "x1", "anchor": {}}, 0, internal=True) is None
    log = new_log()
    for op, path, rule in [
        ({"op": "set_anchor", "id": "zz", "anchor": {"offset": 0}}, "/ops/0/anchor/to", "missing_arg"),
        ({"op": "set_anchor", "id": "x1", "anchor": {"to": 5}}, "/ops/0/anchor/offset", "missing_arg"),
        ({"op": "set_anchor", "id": "x1", "anchor": {"to": "c2", "zz": 1}}, "/ops/0/anchor/zz", "unknown_arg"),
    ]:
        with pytest.raises(O.OplogError) as e:
            log.call(HUMAN, "timeline_apply", {"base_version": 0, "ops": [op], "summary": "s", "client_op_id": "k"})
        d = e.value.as_dict()
        assert (d["rule"], d["path"], d["op_index"]) == (rule, path, 0) and "id" not in d and "problems" not in d


# --------------------------------------------------------------------------- store: open, commit, recover (D1, D2)


def test_commit_order_writes_cache_and_snapshots(home):
    P.create_project(base())
    eng, p = opened()
    for i in range(50):
        write(p, HUMAN, marker(i), key=f"k{i}")
    d = p.dir
    doc = json.loads((d / "timeline.json").read_text())
    assert doc == p.log.doc and doc["version"] == 50
    snap = json.loads((d / "snapshots" / "v000050.json").read_text())
    assert snap["hash"] == doc["hash"] and len((d / "oplog.jsonl").read_bytes().splitlines()) == 50
    eng.close()
    again = O.Oplog.load(json.loads((d / "base.json").read_text()), d / "oplog.jsonl")
    assert again.doc["hash"] == doc["hash"]  # C4: replay = live


def test_torn_final_line_truncated_on_open_and_missing_newline_repaired(home):
    P.create_project(base())
    eng, p = opened()
    write(p, HUMAN, marker(0), key="a")
    write(p, HUMAN, marker(1), key="b")
    eng.close()
    log = p.dir / "oplog.jsonl"
    good = log.read_bytes()
    log.write_bytes(good + b'{"seq":3,"op_id":"x"')  # torn
    eng, p = opened()
    assert log.read_bytes() == good and p.log.version == 2
    eng.close()
    log.write_bytes(good[:-1])  # valid final line, no '\n'
    eng, p = opened()
    assert log.read_bytes() == good
    write(p, HUMAN, marker(2), key="c")
    eng.close()
    lines = log.read_bytes().splitlines()
    assert len(lines) == 3 and all(json.loads(x) for x in lines)
    assert O.Oplog.load(base(), log).version == 3


def test_61d_corrupt_middle_line_is_failed_with_seq_open_and_closed(home):
    P.create_project(base())
    eng, p = opened()
    for i in range(3):
        write(p, HUMAN, marker(i), key=f"k{i}")
    eng.close()
    log = p.dir / "oplog.jsonl"
    good = log.read_bytes().splitlines(keepends=True)
    variants = {
        "bad json": (good[0] + b"{nope\n" + good[2], 2, "not valid JSON"),
        "unknown key": (good[0] + json.dumps({**json.loads(good[1]), "zz": 1}).encode() + b"\n" + good[2], 2, "not an oplog line"),
        "out of sequence": (good[0] + good[2], 3, "out of sequence"),
        "tampered final hash": (good[0] + good[1] + json.dumps({**json.loads(good[2]), "hash": "sha256:" + "0" * 64}).encode() + b"\n", 3,
                                "replay does not reproduce the entry"),
    }
    for name, (raw, seq, reason) in variants.items():
        log.write_bytes(raw)
        with pytest.raises(P.ToolError) as e:
            P.ClosedProject("p1")
        d = e.value.as_dict()
        assert (d["code"], d["seq"], d["error"]) == ("failed", seq, f"oplog line {seq}: {reason}"), name
        assert d["hint"] == P.LOG_HINT and "rule" not in d and "hash" not in d
        eng, p = opened()
        with pytest.raises(P.ToolError) as e2:
            p.oplog()
        assert e2.value.as_dict() == d, name
        with pytest.raises(P.ToolError):
            write(p, HUMAN, marker(9), key="w") if p.log else p.write(HUMAN, "timeline_apply", {})
        eng.close()
    # a tampered middle hash is caught by the open app's replay (finding 8: the closed fast path may serve it)
    mid = json.dumps({**json.loads(good[1]), "hash": "sha256:" + "1" * 64}).encode() + b"\n"
    log.write_bytes(good[0] + mid + good[2])
    eng, p = opened()
    with pytest.raises(P.ToolError) as e:
        p.oplog()
    assert e.value.as_dict()["seq"] == 2
    eng.close()


def test_61_base_json_faults_never_hash(home):
    d = base()
    d["schema_version"] = "hs.timeline/2"
    P.create_project(base())
    root = P.project_dir("p1")
    (root / "base.json").write_text(json.dumps(d))
    with pytest.raises(P.ToolError) as e:
        P.ClosedProject("p1")
    x = e.value.as_dict()
    assert (x["code"], x["rule"], x["path"], x["expected"], x["got"]) == ("schema_mismatch", "bad_schema", "/schema_version", T.SCHEMA_VERSION, "hs.timeline/2")
    stale, _ = T.stamp_hash(base())
    stale["hash"] = "sha256:" + "0" * 64
    (root / "base.json").write_text(json.dumps(stale))
    with pytest.raises(P.ToolError) as e:
        P.ClosedProject("p1")
    x = e.value.as_dict()
    assert (x["code"], x["rule"], x["path"]) == ("invalid_doc", "hash_mismatch", "/hash") and "id" not in x
    assert x["problems"] == T.validate(stale) and "hash" not in {k for k in x if k != "problems"}
    eng, p = opened()
    with pytest.raises(P.ToolError) as e2:
        p.status()
    assert e2.value.as_dict() == x
    eng.close()
    (root / "base.json").write_text("{nope")
    with pytest.raises(P.ToolError) as e:
        P.ClosedProject("p1")
    assert e.value.code == "failed"


def test_61c_a_bad_cache_is_never_an_error(home):
    P.create_project(base())
    eng, p = opened()
    write(p, HUMAN, marker(0), key="a")
    head = p.log.head()
    eng.close()
    root = p.dir
    for junk in (b"{nope", json.dumps({**json.loads((root / "timeline.json").read_text()), "schema_version": "x"}).encode()):
        (root / "timeline.json").write_bytes(junk)
        before = tree(root)
        c = P.ClosedProject("p1")
        assert c.log.head() == head and c.log.doc["hash"] == head["hash"]
        assert tree(root) == before  # the closed app writes nothing
        eng, p = opened()
        assert json.loads((root / "timeline.json").read_text())["hash"] == head["hash"]  # rewritten on open
        eng.close()
        (root / "snapshots").mkdir(exist_ok=True)


def test_58_closed_app_reads_are_read_only_and_follow_the_log(home):
    P.create_project(base())
    eng, p = opened()
    for i in range(51):
        write(p, HUMAN, marker(i), key=f"k{i}")
    head = p.log.head()
    eng.close()
    root = p.dir
    (root / "timeline.json").unlink()  # forces a replay from the v50 snapshot
    log = root / "oplog.jsonl"
    torn = log.read_bytes() + b'{"seq": 52'
    log.write_bytes(torn)
    before = tree(root)
    c = P.ClosedProject("p1")
    assert c.log.head() == head and c.status()["engine"] is None
    assert tree(root) == before and log.read_bytes() == torn  # torn tail skipped in memory, never truncated


def test_d5_d6_lock_second_engine_and_stale_lock(home):
    P.create_project(base())
    eng, p = opened()
    info = json.loads((p.dir / ".lock").read_text())
    assert set(info) == {"pid", "port", "started_at", "engine_version", "attach_token_sha256"} and info["port"] == 4242
    assert info["started_at"].endswith("Z")
    attach = p.dir / ".attach"
    assert stat.S_IMODE(attach.stat().st_mode) == 0o600
    assert P._sha(attach.read_text()) == info["attach_token_sha256"]
    assert P.engine_holding(p.dir)["port"] == 4242
    with pytest.raises(Exception) as e:
        P.Engine(port=5555).open("p1")
    assert e.value.code == "failed" and str(os.getpid()) in e.value.message and "4242" in e.value.message
    assert e.value.hint == P.LOCKED_HINT and "rule" not in e.value.as_dict()
    st = P.ClosedProject("p1").status()
    assert st["engine"] == {"pid": os.getpid(), "port": 4242, "started_at": info["started_at"]} and st["mode"] is None
    eng.close()
    assert not attach.exists() and P.engine_holding(p.dir) is None  # stale .lock file: no OS lock
    eng2, p2 = opened(P.Engine(port=6000))
    assert json.loads((p.dir / ".lock").read_text())["port"] == 6000
    eng2.close()


def test_d3_writes_are_serialised(home):
    P.create_project(base())
    eng, p = opened()
    errs = []

    def go(i):
        try:
            with p.mutex:
                v = p.log.version
            p.write(HUMAN, "timeline_apply", {"base_version": v, "ops": [marker(i)], "summary": "s", "client_op_id": f"t{i}"})
        except O.OplogError as e:
            errs.append(e.code)

    ths = [threading.Thread(target=go, args=(i,)) for i in range(20)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert set(errs) <= {"conflict"} and p.log.version == 20 - len(errs)
    assert O.Oplog.load(base(), p.dir / "oplog.jsonl").doc == p.log.doc
    eng.close()


def test_d9_d11_events_replay_and_reset(home):
    P.create_project(base())
    eng, p = opened()
    sub, replay, reset = p.subscribe(None)
    r = write(p, hermes(3), marker(0), key="a")
    p.write(hermes(3), "timeline_apply", {"base_version": 0, "ops": [marker(0)], "summary": "edit", "client_op_id": "a"})  # cached retry: no event
    p.write(hermes(3), "history_undo", {"client_op_id": "u", "op_id": r["op_id"]})
    evs = [sub.q.get_nowait() for _ in range(sub.q.qsize())]
    assert [e["type"] for e in evs] == ["op.applied", "op.undone"] and [e["seq"] for e in evs] == [1, 2]
    assert evs[0]["project_id"] == "p1" and evs[0]["step"] == 3 and evs[1]["undoes"] == [r["op_id"]]
    assert set(evs[0]) == {"type", "project_id", "seq", "op_id", "group_id", "actor", "step", "summary", "base_version",
                           "new_version", "hash", "changed_ids", "undoes"}
    _, replay, reset = p.subscribe(1)
    assert [e["seq"] for e in replay] == [2] and reset is None
    _, replay, reset = p.subscribe(9)
    assert replay == [] and reset == 2
    eng.close()


def test_d11_slow_client_is_dropped(home):
    P.create_project(base())
    eng, p = opened()
    sub, _, _ = p.subscribe(None)
    for _ in range(P.EVENT_QUEUE_MAX):
        sub.put({"seq": 0})
    assert not sub.dropped.is_set()
    write(p, HUMAN, marker(0), key="a")
    assert sub.dropped.is_set() and sub not in p.subscribers
    eng.close()


def test_d13_tokens():
    t = P.Tokens()
    ui, agent, acp, ctl = t.mint("ui"), t.mint("mcp:claude"), t.mint("acp:hermes", plan=O.PlanContext(3)), t.mint("control")
    assert len({ui, agent, acp, ctl}) == 4 and all(len(x) == 64 for x in (ui, agent, acp, ctl))
    assert t.resolve(ui).session.actor.kind == "human"
    assert t.resolve(agent).session.actor == O.Actor("agent", "claude") and t.resolve(agent).session.step() is None
    assert t.resolve(acp).session.step() == 3 and t.resolve(ctl).session is None
    assert t.resolve("nope") is None and t.resolve("") is None
    ro = t.mint("mcp:r", scopes={"read"})
    assert t.resolve(ro).scopes == frozenset({"read"})
    with pytest.raises(ValueError):
        t.mint("root")
