"""S3 /mcp timeline tools over HTTP and REST (S3-SPEC §1g/§1h, D15-D26, D29-D31; tests 88-100)."""

from __future__ import annotations

import json
import unicodedata

import pytest
from s3_app import App, key
from test_oplog import S, base

from hermes_studio import mcp_timeline as MT
from hermes_studio import oplog as O


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(base())
    yield a
    a.close()


def refused(app: App, ok_body: tuple[bool, dict], before: dict) -> dict:
    ok, body = ok_body
    assert not ok, body
    assert app.head() == before
    return body


def same_both(app: App, mcp_ops: list, http_ops: list, **extra) -> dict:
    h0 = app.head()
    m = refused(app, app.mcp_apply(*mcp_ops, **extra), h0)
    h = refused(app, app.rest_apply(*http_ops, **extra), h0)
    assert key(m) == key(h), (m, h)
    return m


# --------------------------------------------------------------------------- 88


@pytest.mark.parametrize(
    "op, want",
    [
        ({"id": 5, "text": "a"}, ("invalid_op", "bad_arg", "/ops/0/id", 0, False, None)),
        ({"id": True, "text": "a"}, ("invalid_op", "bad_arg", "/ops/0/id", 0, False, None)),
        ({"id": None, "text": "a"}, ("invalid_op", "bad_arg", "/ops/0/id", 0, False, None)),
        ({"id": ["x1"], "text": "a"}, ("invalid_op", "bad_arg", "/ops/0/id", 0, False, None)),
        ({"id": 5, "bogus": 1}, ("invalid_op", "unknown_arg", "/ops/0/bogus", 0, False, None)),
        ({"id": 5}, ("invalid_op", "bad_arg", "/ops/0/id", 0, False, None)),
        ({"id": "zz", "text": 5}, ("not_found", "not_found", "/ops/0/id", 0, True, "zz")),
        ({"id": "x1", "text": 5}, ("invalid_op", "wrong_type", "/ops/0/text", 0, True, "x1")),
        ({"id": "x1", "style": 5}, ("invalid_op", "wrong_type", "/ops/0/style", 0, True, "x1")),
        ({"id": "x1", "text": None}, ("invalid_op", "wrong_type", "/ops/0/text", 0, True, "x1")),
        ({"id": "x1", "style": {}}, ("invalid_op", "wrong_type", "/ops/0/style", 0, True, "x1")),
    ],
)
def test_88_edit_text_precheck_equals_engine(app, op, want):
    op = {"op": "edit_text", **op}
    e = same_both(app, [op], [op])
    got = key(e)
    assert got[1:] == want[1:] and e["code"] in ("invalid_op", "not_found")


# --------------------------------------------------------------------------- 89


def test_89_schemas_enforce_nothing_the_engine_does_not():
    for t in MT.TOOLS:
        s = json.dumps(t["inputSchema"])
        for banned in ('additionalProperties": false', "minItems", "maxItems", "minLength", "maxLength", '"required"'):
            assert banned not in s, (t["name"], banned)
    # 11 timeline + 3 media (S4) + 3 frames (S5) + 2 render (S6) + 1 cut (S7) + 4 gate (S8) + 2 projects (Edit page)
    assert {t["name"] for t in MT.TOOLS} == set(MT.NAMES) and len(MT.TOOLS) == 26


# Addendum (test 89): every public op, with args the engine would accept, so a non-string `id`
# is the one fault and every case reaches bad_arg at /ops/0/id. The create ops (id optional) too.
VALID_OPS = [
    {"op": "insert_clip", "track": "V1", "media": "m1", "src": [0, S], "at": 20 * S},
    {"op": "move_clip", "at": 30 * S},
    {"op": "trim_clip", "src_in": S // 2},
    {"op": "split_clip", "at": S},
    {"op": "delete_clip", "ripple": False},
    {"op": "set_props", "props": {}},
    {"op": "set_fade", "fade_in": 0},
    {"op": "set_anchor", "anchor": {"to": "c1", "offset": 0}},
    {"op": "edit_text", "text": "a"},
    {"op": "add_text", "dur": S, "text": "a", "style": "pop", "at": 0},
    {"op": "add_transition", "between": ["c1", "c2"], "dur": S // 2},
    {"op": "add_track", "role": "music"},
    {"op": "remove_track"},
    {"op": "add_marker", "at": 0, "label": "m"},
    {"op": "remove_marker"},
    {"op": "add_media", "path": "media/b.mp4", "dur": S, "fps": [30, 1]},  # S4
]
assert sorted(op["op"] for op in VALID_OPS) == sorted(O.PUBLIC_OPS)

WRITE_CASES = [
    ("timeline_apply", {"ops": [], "summary": "s", "base_version": 0}),
    ("timeline_apply", {"ops": [{"op": "add_marker", "at": 0, "label": "m"}] * 501, "summary": "s", "base_version": 0}),
    ("timeline_apply", {"ops": [{"op": "add_marker", "at": 0, "label": "m"}], "summary": "s", "base_version": "0"}),
    ("timeline_apply", {"ops": [{"op": "add_marker", "at": 0, "label": "m"}], "summary": "", "base_version": 0}),
    ("timeline_apply", {"ops": [{"op": "add_marker", "at": 0, "label": "m"}], "summary": "x" * 201, "base_version": 0}),
    (
        "timeline_apply",
        {"ops": [{"op": "add_marker", "at": 0, "label": "m"}], "summary": unicodedata.normalize("NFD", "Olé"), "base_version": 0},
    ),
    (
        "timeline_apply",
        {"ops": [{"op": "add_marker", "at": 0, "label": "m"}], "summary": "s", "base_version": 0, "group_id": None},
    ),
    ("timeline_apply", {"ops": [{"op": "add_marker", "at": 0, "label": "m"}], "summary": "s", "base_version": 0, "zz": 1}),
    ("timeline_apply", {"ops": [{"op": "add_marker", "at": 0, "label": "m", "zz": 1}], "summary": "s", "base_version": 0}),
    ("timeline_apply", {"ops": [{"op": "add_marker", "at": 0}], "summary": "s", "base_version": 0}),
    ("timeline_apply", {"summary": "s", "base_version": 0}),
    ("timeline_apply", {"ops": [{"op": "add_marker", "at": 0, "label": "m"}], "summary": "s"}),
    ("history_undo", {"op_id": None}),
    ("history_undo", {"op_id": "op-nope"}),
    ("history_undo", {"zz": 1}),
    ("history_redo", {"op_id": 5}),
    ("history_redo", {}),
] + [("timeline_apply", {"ops": [{**op, "id": 5}], "summary": "s", "base_version": 0}) for op in VALID_OPS]


@pytest.mark.parametrize("tool, args", WRITE_CASES)
def test_89_every_write_error_equals_the_engine(app, tool, args):
    h0 = app.head()
    args = {"client_op_id": "k89", **args}
    m = refused(app, app.mcp(tool, {"project_id": "p1", **args}), h0)
    h = refused(app, app.rest(tool, args), h0)
    assert key(m) == key(h), (m, h)
    assert m["code"] in O_CODES


@pytest.mark.parametrize("op", VALID_OPS, ids=[op["op"] for op in VALID_OPS])
def test_89_a_non_string_op_id_is_bad_arg_on_every_op(app, op):
    h0 = app.head()
    args = {"client_op_id": "k89", "ops": [{**op, "id": 5}], "summary": "s", "base_version": 0}
    m = refused(app, app.mcp("timeline_apply", {"project_id": "p1", **args}), h0)
    h = refused(app, app.rest("timeline_apply", args), h0)
    assert key(m) == key(h) == ("invalid_op", "bad_arg", "/ops/0/id", 0, False, None), (m, h)
    good = {**op, "id": ID_FOR[op["op"]]} if op["op"] in ID_FOR else op  # create ops: the engine picks the id
    ops = (
        [{"op": "move_clip", "id": "c2", "at": 3 * S + S // 2}, good] if op["op"] == "add_transition" else [good]
    )  # make the overlap
    ok, r = app.mcp("timeline_apply", {"project_id": "p1", **args, "client_op_id": "k89ok", "ops": ops})
    assert ok, r  # with a real id the same op goes through: the id was the only fault


ID_FOR = {
    "move_clip": "c3",
    "trim_clip": "c1",
    "split_clip": "c1",
    "delete_clip": "c3",
    "set_props": "c1",
    "set_fade": "c1",
    "set_anchor": "x1",
    "edit_text": "x1",
    "remove_track": "A2",
    "remove_marker": "k1",
}
O_CODES = {
    "invalid_op",
    "not_found",
    "conflict",
    "schema_mismatch",
    "invalid_doc",
    "failed",
    "nothing_to_undo",
    "nothing_to_redo",
}


@pytest.mark.parametrize("tool", ["history_list", "history_diff"])
@pytest.mark.parametrize(
    "args",
    [
        {"since_version": 0},
        {"since_version": -1},
        {"limit": 0},
        {"since_version": 0, "limit": 9999},
        {"since_version": 0, "limit": 2},
        {},
    ],
)
def test_89_history_reads_equal_http(app, tool, args):
    app.mcp_apply({"op": "add_marker", "at": 0, "label": "m"})
    ok, m = app.mcp(tool, {"project_id": "p1", **args})
    q = "&".join(f"{k}={v}" for k, v in args.items())
    path = "/api/projects/p1/history" + ("/diff" if tool == "history_diff" else "") + (f"?{q}" if q else "")
    st, _, h = app.req("GET", path, token=app.agent)
    assert (st == 200) == ok and (h == m if ok else key(h) == key(m)), (m, h)


def test_89_history_query_parity(app):
    """D26: unknown query params are ignored; a query "5" is the int 5; a /mcp JSON string is bad_arg."""
    st, _, h = app.req("GET", "/api/projects/p1/history?zz=1&since_version=0", token=app.agent)
    assert st == 200 and h["entries"] == []
    ok, m = app.mcp("history_list", {"project_id": "p1", "zz": 1})
    assert not ok and (m["rule"], m["path"]) == ("unknown_arg", "/zz")
    ok, m = app.mcp("history_list", {"project_id": "p1", "since_version": "0"})
    assert not ok and (m["rule"], m["path"]) == ("bad_arg", "/since_version")
    for raw in ("007", "-1", "%D9%A3", "", "+1"):
        st, _, h = app.req("GET", f"/api/projects/p1/history?since_version={raw}", token=app.agent)
        assert st != 200 and (h["rule"], h["path"]) == ("bad_arg", "/since_version"), raw
    st, _, h = app.req("GET", "/api/projects/p1/history/diff", token=app.agent)
    assert st != 200 and (h["rule"], h["path"]) == ("missing_arg", "/since_version")


@pytest.mark.parametrize("tool", ["get_timeline", "get_hash", "list_markers", "project_status", "export_otio"])
def test_89_simple_tools(app, tool):
    ok, e = app.mcp(tool, {"project_id": "p1", "zz": 1})
    assert not ok and (e["code"], e["rule"], e["path"]) == ("invalid_op", "unknown_arg", "/zz")
    ok, e = app.mcp(tool, {})
    assert not ok and (e["rule"], e["path"]) == ("missing_arg", "/project_id")
    ok, e = app.mcp(tool, {"project_id": 5})
    assert not ok and (e["rule"], e["path"]) == ("bad_arg", "/project_id") and "id" not in e
    ok, e = app.mcp(tool, {"project_id": "nope"})
    assert not ok and e["code"] == "not_found" and e["id"] == "nope"
    ok, r = app.mcp(tool, {"project_id": "p1"})
    assert ok, r


def test_89_reads_match_the_engine(app):
    app.mcp_apply({"op": "add_marker", "at": 3 * S, "label": "a"})
    ok, h = app.mcp("get_hash", {"project_id": "p1"})
    assert ok and h == app.head()
    ok, doc = app.mcp("get_timeline", {"project_id": "p1"})
    assert ok and doc == app.proj.log.doc
    ok, st = app.mcp("project_status", {"project_id": "p1"})
    assert ok and st["version"] == 1 and st["engine"]["port"] == app.port
    ok, mk = app.mcp("list_markers", {"project_id": "p1"})
    assert ok and [m["label"] for m in mk["markers"]] == ["here", "a"]
    ok, ex = app.mcp("export_otio", {"project_id": "p1"})
    assert ok and ex["path"].endswith("p1-v000001.otio")
    ok, v = app.mcp("validate_timeline", {"doc": app.proj.log.doc})
    assert ok and v == {"ok": True, "hash": app.head()["hash"]}
    bad = dict(app.proj.log.doc, hash="sha256:" + "0" * 64)
    ok, v = app.mcp("validate_timeline", {"doc": bad})
    assert not ok and v["rule"] == "hash_mismatch"


def test_89_forged_actor_and_step_get_engine_warnings(app):
    ok, r = app.mcp_apply({"op": "add_marker", "at": 3 * S, "label": "a", "step": 9}, actor={"kind": "human", "id": "x"})
    assert ok and [(w["code"], w["path"]) for w in r["warnings"]] == [
        ("ignored_field", "/actor"),
        ("ignored_field", "/ops/0/step"),
    ]
    line = (app.proj.dir / "oplog.jsonl").read_text()
    assert '"x"' not in line and '"step": 9' not in line and json.loads(line)["actor"] == {"kind": "agent", "id": "claude"}


# --------------------------------------------------------------------------- 90


@pytest.mark.parametrize("v", [True, False, float("nan"), float("inf"), float("-inf"), "1.5"])
def test_90_bad_seconds_are_bad_arg_with_no_engine_call(app, v):
    h0 = app.head()
    for op, arg in (
        ({"op": "add_marker", "label": "m", "at_s": v}, "at_s"),
        ({"op": "set_fade", "id": "c1", "fade_in_s": v}, "fade_in_s"),
    ):
        e = refused(app, app.mcp_apply(op), h0)
        assert (e["code"], e["rule"], e["path"], e["op_index"]) == ("invalid_op", "bad_arg", f"/ops/0/{arg}", 0)
    assert app.proj.log._results == {}  # no engine call: nothing cached, nothing reserved


def test_90_big_negative_and_minus_zero(app):
    h0 = app.head()
    for v, rule in ((1e308, "too_large"), (-1, "negative_time"), (-1.5, "negative_time")):
        e = refused(app, app.mcp_apply({"op": "add_marker", "label": "m", "at_s": v}), h0)
        assert (e["rule"], e["path"]) == (rule, "/ops/0/at_s"), e
        ticks = round(v * S) if v != 1e308 else int(v) * S
        h = refused(app, app.rest_apply({"op": "add_marker", "label": "m", "at": ticks}), h0)
        assert key(e)[:2] + key(e)[3:] == key(h)[:2] + key(h)[3:]  # the engine's answer, path rewritten to the _s arg
        e = refused(app, app.mcp_apply({"op": "set_fade", "id": "c1", "fade_in_s": v}), h0)
        assert (e["rule"], e["path"]) == (rule, "/ops/0/fade_in_s"), e
        h = refused(app, app.rest_apply({"op": "set_fade", "id": "c1", "fade_in": ticks}), h0)
        assert key(e)[:2] + key(e)[3:] == key(h)[:2] + key(h)[3:]
    ok, r = app.mcp_apply({"op": "add_marker", "label": "m", "at_s": -0.0})
    assert ok and r["used"]["at_s"] == {"ticks": 0, "seconds": 0}
    assert [m["at"] for m in app.proj.log.doc["markers"] if m["label"] == "m"] == [0]
    ok, r = app.mcp_apply({"op": "set_fade", "id": "c1", "fade_in_s": -0.0})
    assert ok and r["used"]["fade_in_s"] == {"ticks": 0, "seconds": 0}
    ok, r = app.mcp_apply({"op": "set_anchor", "id": "x1", "anchor": {"to": "c2", "offset_s": -1}})
    assert ok, r
    x1 = next(i for t in app.proj.log.doc["tracks"] for i in t["items"] if i["id"] == "x1")
    assert x1["anchor"]["offset"] == -S


# --------------------------------------------------------------------------- 91, 92


def test_91_float_seconds_retry_never_mismatches(app):
    args = {
        "project_id": "p1",
        "base_version": 0,
        "summary": "s",
        "client_op_id": "f",
        "ops": [{"op": "add_marker", "at_s": 0.3333333333333333, "label": "m"}],
    }
    ok, a = app.mcp("timeline_apply", args)
    assert ok and app.proj.log.doc["markers"][-1]["at"] == 235200000
    assert type(json.loads((app.proj.dir / "oplog.jsonl").read_text())["ops"][0]["at"]) is int
    ok, b = app.mcp("timeline_apply", args)
    assert ok and (b["op_id"], b["new_version"]) == (a["op_id"], a["new_version"])
    app.mcp_apply({"op": "add_marker", "at": 5 * S, "label": "z"})
    ok, c = app.mcp("timeline_apply", args)  # stale base_version, same key: still the cache
    assert ok and c["op_id"] == a["op_id"] and len(app.proj.log._entries) == 2
    mv = {
        "project_id": "p1",
        "base_version": 2,
        "summary": "s",
        "client_op_id": "mv",
        "ops": [{"op": "move_clip", "id": "c3", "at_s": 10.000000000000002}],
    }
    ok, m1 = app.mcp("timeline_apply", mv)
    ok2, m2 = app.mcp("timeline_apply", mv)
    assert ok and ok2 and m1["op_id"] == m2["op_id"] and len(app.proj.log._entries) == 3


def test_92_nfd_retries_never_mismatch(app):
    nfd = unicodedata.normalize("NFD", "Olé")
    h0 = app.head()
    for _ in range(2):
        e = refused(
            app,
            app.mcp(
                "timeline_apply",
                {
                    "project_id": "p1",
                    "base_version": 0,
                    "summary": "s",
                    "client_op_id": "n",
                    "ops": [{"op": "edit_text", "id": "x1", "text": nfd}],
                },
            ),
            h0,
        )
        assert (e["rule"], e["path"], e["id"]) == ("not_nfc", "/ops/0/text", "x1")
        e = refused(
            app,
            app.mcp(
                "timeline_apply",
                {
                    "project_id": "p1",
                    "base_version": 0,
                    "summary": "s",
                    "client_op_id": "n",
                    "ops": [{"op": "add_marker", "at": 0, "label": nfd}],
                },
            ),
            h0,
        )
        h = refused(
            app,
            app.rest(
                "timeline_apply",
                {"base_version": 0, "summary": "s", "client_op_id": "n", "ops": [{"op": "add_marker", "at": 0, "label": nfd}]},
            ),
            h0,
        )
        assert key(e) == key(h)  # the engine's answer (validator path, as at c6de84e)
        assert (e["rule"], e["path"], e["id"]) == ("not_nfc", "/markers/1/label", "mk1")  # O4: pinned literally
        e = refused(
            app,
            app.mcp(
                "timeline_apply",
                {
                    "project_id": "p1",
                    "base_version": 0,
                    "summary": nfd,
                    "client_op_id": "n",
                    "ops": [{"op": "add_marker", "at": 0, "label": "m"}],
                },
            ),
            h0,
        )
        assert (e["rule"], e["path"]) == ("bad_arg", "/summary")
    good = {
        "project_id": "p1",
        "base_version": 0,
        "summary": "s",
        "client_op_id": "n",
        "ops": [{"op": "edit_text", "id": "x1", "text": "Olé"}],
    }
    ok, a = app.mcp("timeline_apply", good)
    ok2, b = app.mcp("timeline_apply", good)
    assert ok and ok2 and a["op_id"] == b["op_id"] and len(app.proj.log._entries) == 1


# --------------------------------------------------------------------------- 94 (HTTP REST and the ACP /mcp path; stdio in test_s3_stdio)


def c5_calls(app: App, send) -> list[dict]:
    a = {
        "base_version": 0,
        "summary": "s",
        "client_op_id": "k70",
        "ops": [{"op": "add_marker", "at": 3 * S, "label": "a", "step": 9}],
        "actor": {"kind": "human", "id": "x"},
    }
    r1 = send("timeline_apply", a)
    r2 = send("timeline_apply", a)  # the test-93 exact retry
    u = send("history_undo", {"client_op_id": "u70", "op_id": r1["op_id"], "step": 7})
    rd = send("history_redo", {"client_op_id": "r70", "op_id": u["op_id"], "step": 7})
    return [r1, r2, u, rd]


def check_c5(app: App, out: list[dict], step) -> None:
    r1, r2, u, rd = out
    w = lambda r: [(x["code"], x["path"]) for x in r["warnings"]]  # noqa: E731
    assert w(r1) == w(r2) == [("ignored_field", "/actor"), ("ignored_field", "/ops/0/step")]
    assert r2["op_id"] == r1["op_id"] and w(u) == w(rd) == [("ignored_field", "/step")]
    raw = (app.proj.dir / "oplog.jsonl").read_text()
    assert '"x"' not in raw and "human" not in raw and '"step": 9' not in raw and '"step": 7' not in raw
    for line in raw.splitlines():
        e = json.loads(line)
        assert e["actor"] == {"kind": "agent", "id": "hermes"} and e.get("step") == step
        assert all("step" not in op for op in e["ops"])
    ok, hl = app.mcp("history_list", {"project_id": "p1"}, app.acp)
    assert ok and len(hl["entries"]) == 3 and all(e["actor"]["kind"] == "agent" for e in hl["entries"])


def strip_ids(out: list[dict]) -> list:
    return [{k: v for k, v in r.items() if k not in ("op_id", "undoes", "hash", "used")} for r in out]


def test_94_c5_over_http_and_acp(tmp_path, monkeypatch):
    results = []
    for path in ("http", "acp"):
        monkeypatch.setenv("HOME", str(tmp_path / path))
        app = App(base())
        try:
            if path == "http":

                def send(tool, args):
                    ok, r = app.rest(tool, args, app.acp)
                    assert ok, r
                    return r
            else:

                def send(tool, args):
                    ok, r = app.mcp(tool, {"project_id": "p1", **args}, app.acp)
                    assert ok, r
                    return r

            out = c5_calls(app, send)
            check_c5(app, out, 3)
            results.append(strip_ids(out))
        finally:
            app.close()
    assert results[0] == results[1]


# --------------------------------------------------------------------------- 95, 96


def test_95_seconds_order(app):
    h0 = app.head()
    cases = [
        ({"at": S, "at_s": 1, "label": "m", "bogus": 1}, ("unknown_arg", "/ops/0/bogus")),
        ({"at": S, "at_s": 1, "label": "m"}, ("bad_arg", "/ops/0/at_s")),
        ({"at_s": "x"}, ("missing_arg", "/ops/0/label")),
        ({"at_s": "x", "label": "m", "bogus": 1}, ("unknown_arg", "/ops/0/bogus")),
        ({"at_s": "x", "label": "m"}, ("bad_arg", "/ops/0/at_s")),
    ]
    for op, want in cases:
        e = refused(app, app.mcp_apply({"op": "add_marker", **op}), h0)
        assert (e["rule"], e["path"], e["op_index"]) == (*want, 0), (op, e)
        if want[0] != "bad_arg":  # byte-identical to HTTP sent the check view
            view = {k: v for k, v in op.items() if not k.endswith("_s")}
            if "at" not in view:
                view["at"] = 0
            h = refused(app, app.rest_apply({"op": "add_marker", **view}), h0)
            assert h == e
    e = refused(app, app.mcp_apply({"op": "set_fade", "id": "c1", "fade_in": 0, "fade_in_s": 0, "fade_out_s": "x"}), h0)
    assert (e["rule"], e["path"], e["op_index"]) == ("bad_arg", "/ops/0/fade_in_s", 0)
    ok, r = app.mcp_apply({"op": "add_marker", "at": S, "label": "m"})
    assert ok and "used" not in r and app.proj.log.doc["markers"][-1]["at"] == S


def test_96_offset_seconds_order(app):
    h0 = app.head()
    cases = [
        ({"id": "x1", "anchor": {"to": "c2", "offset": 0, "offset_s": 1}, "bogus": 1}, ("unknown_arg", "/ops/0/bogus")),
        ({"id": "x1", "anchor": {"to": "c2", "offset": 0, "offset_s": 1}}, ("bad_arg", "/ops/0/anchor/offset_s")),
        ({"anchor": {"to": "c2", "offset_s": "x"}}, ("missing_arg", "/ops/0/id")),
        ({"id": "x1", "anchor": {"to": "c2", "offset_s": "x"}, "bogus": 1}, ("unknown_arg", "/ops/0/bogus")),
        ({"id": "x1", "anchor": {"to": "c2", "offset_s": "x"}}, ("bad_arg", "/ops/0/anchor/offset_s")),
    ]
    for op, want in cases:
        e = refused(app, app.mcp_apply({"op": "set_anchor", **op}), h0)
        assert (e["rule"], e["path"], e["op_index"]) == (*want, 0), (op, e)
    e = refused(app, app.mcp_apply({"op": "add_text", "text": "t", "style": "pop", "anchor": {"to": "c2", "offset_s": "x"}}), h0)
    assert (e["rule"], e["path"]) == ("missing_arg", "/ops/0/dur")
    ok, r = app.mcp_apply({"op": "set_anchor", "id": "x1", "anchor": {"to": "c2", "offset": S}})
    assert ok and "used" not in r


# --------------------------------------------------------------------------- 97


ANCHOR_HOSTS = [
    ("set_anchor", {"id": "x1"}),
    ("add_text", {"dur": S, "text": "t", "style": "pop"}),
    ("insert_clip", {"track": "A2", "media": "m2", "src": [0, S]}),
]


@pytest.mark.parametrize("op, extra", ANCHOR_HOSTS)
def test_97_anchor_keys_by_name_http_equals_mcp(app, op, extra):
    h0 = app.head()
    for m_anchor, h_anchor, want in [
        ({"to": "c2", "offset_s": "x", "zz": 1}, {"to": "c2", "offset": 0, "zz": 1}, ("unknown_arg", "/ops/0/anchor/zz")),
        ({"offset_s": "x"}, {"offset": 0}, ("missing_arg", "/ops/0/anchor/to")),
        ({"to": "c2", "offset_s": 1, "zz": 1}, {"to": "c2", "offset": S, "zz": 1}, ("unknown_arg", "/ops/0/anchor/zz")),
        ({"offset_s": 1}, {"offset": S}, ("missing_arg", "/ops/0/anchor/to")),
    ]:
        m = refused(app, app.mcp_apply({"op": op, **extra, "anchor": m_anchor}), h0)
        h = refused(app, app.rest_apply({"op": op, **extra, "anchor": h_anchor}), h0)
        assert key(m) == key(h) == ("invalid_op", *want, 0, False, None), (m, h)
    e = refused(app, app.mcp_apply({"op": op, **extra, "anchor": {"to": "c2", "offset_s": "x"}, "bogus": 1}), h0)
    assert (e["rule"], e["path"]) == ("unknown_arg", "/ops/0/bogus")
    for anchor, want in [
        ({"to": "c2", "zz": 1}, ("unknown_arg", "/ops/0/anchor/zz")),
        ({}, ("missing_arg", "/ops/0/anchor/offset")),
    ]:
        h = refused(app, app.rest_apply({"op": op, **extra, "anchor": anchor}), h0)
        assert (h["rule"], h["path"]) == want


def test_97_set_anchor_precedence(app):
    h0 = app.head()
    e = refused(app, app.rest_apply({"op": "set_anchor", "id": "zz", "anchor": {"offset": 0}}), h0)
    assert (e["rule"], e["path"]) == ("missing_arg", "/ops/0/anchor/to") and "id" not in e
    e = refused(app, app.rest_apply({"op": "set_anchor", "id": "x1", "anchor": {"to": 5}}), h0)
    assert (e["rule"], e["path"]) == ("missing_arg", "/ops/0/anchor/offset")
    ok, _ = app.rest_apply({"op": "set_anchor", "id": "x1", "anchor": None, "at": 0})
    assert ok


# --------------------------------------------------------------------------- 98, 99, 100


def test_98_trim_clip_dur_s(app):
    h0 = app.head()
    e = refused(app, app.mcp_apply({"op": "trim_clip", "id": "c1", "dur_s": "x"}), h0)
    assert (e["rule"], e["path"]) == ("bad_arg", "/ops/0/dur_s")
    h = refused(app, app.rest_apply({"op": "trim_clip", "id": "c1", "dur": S}), h0)
    assert (h["rule"], h["path"]) == ("bad_arg", "/ops/0/id") and "id" not in h
    m = refused(app, app.mcp_apply({"op": "trim_clip", "id": "c1", "dur_s": 1}), h0)
    assert key(m) == key(h)


def test_99_batch_order_and_cached_key(app):
    h0 = app.head()
    e = refused(
        app, app.mcp_apply({"op": "move_clip", "id": "zz", "at_s": 0}, {"op": "add_marker", "at_s": "x", "label": "m"}), h0
    )
    assert (e["rule"], e["path"], e["op_index"]) == ("bad_arg", "/ops/1/at_s", 1)
    e = refused(
        app,
        app.mcp_apply({"op": "move_clip", "id": "zz", "at_s": 0, "bogus": 1}, {"op": "add_marker", "at_s": "x", "label": "m"}),
        h0,
    )
    assert (e["rule"], e["path"]) == ("unknown_arg", "/ops/0/bogus")
    h = refused(app, app.rest_apply({"op": "move_clip", "id": "zz", "at": 0}, {"op": "add_marker", "at": 0, "label": "m"}), h0)
    assert (h["code"], h["path"], h["id"]) == ("not_found", "/ops/0/id", "zz")
    ok, _ = app.mcp(
        "timeline_apply",
        {
            "project_id": "p1",
            "base_version": 0,
            "summary": "s",
            "client_op_id": "k",
            "ops": [{"op": "add_marker", "at": 0, "label": "m"}],
        },
    )
    assert ok
    h1 = app.head()
    e = refused(
        app,
        app.mcp(
            "timeline_apply",
            {
                "project_id": "p1",
                "base_version": 1,
                "summary": "s",
                "client_op_id": "k",
                "ops": [{"op": "add_marker", "at_s": "x", "label": "m"}],
            },
        ),
        h1,
    )
    assert (e["rule"], e["path"]) == ("bad_arg", "/ops/0/at_s")
    e = refused(
        app,
        app.mcp(
            "timeline_apply",
            {
                "project_id": "p1",
                "base_version": 1,
                "summary": "s",
                "client_op_id": "k",
                "ops": [{"op": "add_marker", "at_s": 1, "label": "m"}],
            },
        ),
        h1,
    )
    assert e["rule"] == "client_op_id_mismatch"


@pytest.mark.parametrize(
    "extra, ops0, want",
    [
        ({"summary": ""}, None, ("bad_arg", "/summary", None)),
        ({"bogus": 1}, None, ("unknown_arg", "/bogus", None)),
        ({"group_id": None}, None, ("bad_arg", "/group_id", None)),
        ({"base_version": "0"}, None, ("bad_arg", "/base_version", None)),
        ({}, 5, ("bad_arg", "/ops/0", 0)),
    ],
)
def test_100_envelope_before_the_mcp_op_stage(app, extra, ops0, want):
    h0 = app.head()
    m_ops = [{"op": "add_marker", "at_s": "x", "label": "m"}]
    h_ops = [{"op": "add_marker", "at": 0, "label": "m"}]
    if ops0 is not None:
        m_ops, h_ops = [ops0, *m_ops], [ops0, *h_ops]
    m = refused(app, app.mcp_apply(*m_ops, **extra), h0)
    h = refused(app, app.rest_apply(*h_ops, **extra), h0)
    assert key(m) == key(h) and (m["rule"], m["path"], m.get("op_index")) == want


def test_conflict_comes_after_the_mcp_op_stage(app):
    app.mcp_apply({"op": "add_marker", "at": 0, "label": "m"})
    h1 = app.head()
    e = refused(app, app.mcp_apply({"op": "add_marker", "at_s": "x", "label": "m"}, base_version=0), h1)
    assert e["rule"] == "bad_arg"
    e = refused(app, app.mcp_apply({"op": "add_marker", "at_s": 1, "label": "m"}, base_version=0), h1)
    assert e["code"] == "conflict"


# --------------------------------------------------------------------------- auth, scopes, SSE (D13, D16, D9)


def test_auth_and_scopes(app):
    st, h, j = app.req("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert st == 401
    st, _, j = app.req("POST", "/api/projects/p1/timeline_apply", {}, token="nope")
    assert st == 401
    ro = app.eng.tokens.mint("mcp:ro", scopes={"read"})
    ok, e = app.mcp_apply({"op": "add_marker", "at": 0, "label": "m"}, token=ro)
    assert not ok and e["code"] == "permission_denied"
    ok, _ = app.mcp("get_hash", {"project_id": "p1"}, ro)
    assert ok
    ok, r = app.rest_apply({"op": "add_marker", "at": 0, "label": "m"}, token=app.ui)
    assert ok and json.loads((app.proj.dir / "oplog.jsonl").read_text())["actor"]["kind"] == "human"
    st, _, j = app.req("GET", "/api/projects/p1/hash", token=app.ui)
    assert st == 200 and j == app.head()
    st, _, j = app.req("GET", "/api/projects/p1/status", token=app.ui)
    assert st == 200 and j["version"] == 1


def test_http_mcp_protocol(app):
    st, _, j = app.rpc("initialize", {"protocolVersion": "2025-06-18"})
    assert st == 200 and j["result"]["capabilities"]["resources"]["subscribe"] is True
    st, _, j = app.rpc("tools/list")
    assert [t["name"] for t in j["result"]["tools"]] == list(MT.NAMES)
    st, _, j = app.req("POST", "/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"}, app.agent)
    assert st == 202 and j is None
    st, h, j = app.req("POST", "/mcp", b"{nope", app.agent)
    assert st == 400 and j == {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
    assert h["connection"] == "close"
    st, _, j = app.req("POST", "/mcp", {"jsonrpc": "2.0", "id": 1}, app.agent)
    assert j["error"]["code"] == -32600
    st, _, j = app.rpc("tools/call", {"name": "get_hash", "arguments": 5})
    assert j["error"]["code"] == -32602
    st, _, j = app.rpc("resources/read", {"uri": "timeline://p1"})
    assert json.loads(j["result"]["contents"][0]["text"]) == app.proj.log.doc
    st, _, j = app.rpc("tools/call", {"name": "get_hash", "arguments": {"project_id": "p1"}})
    assert all(ord(c) < 128 for c in json.dumps(j, ensure_ascii=False))


def test_sse_events_and_last_event_id(app):
    import http.client

    app.mcp_apply({"op": "add_marker", "at": 0, "label": "a"})
    c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=10)
    c.request(
        "GET",
        "/api/projects/p1/events",
        headers={"Host": f"127.0.0.1:{app.port}", "Authorization": f"Bearer {app.ui}", "Last-Event-ID": "0"},
    )
    r = c.getresponse()
    assert r.status == 200 and r.getheader("Content-Type").startswith("text/event-stream")
    app.mcp_apply({"op": "add_marker", "at": S, "label": "b"})
    seen = []
    while len(seen) < 2:
        line = r.fp.readline().decode()
        if line.startswith("id: "):
            seen.append(int(line[4:]))
        if line.startswith("data: "):
            assert json.loads(line[6:])["project_id"] == "p1"
    assert seen == [1, 2]
    c.close()
    c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=10)
    c.request(
        "GET",
        "/api/projects/p1/events",
        headers={"Host": f"127.0.0.1:{app.port}", "Authorization": f"Bearer {app.ui}", "Last-Event-ID": "99"},
    )
    r = c.getresponse()
    got = b""
    while b"stream.reset" not in got:
        got += r.fp.readline()
    c.close()
    c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=10)
    c.request(
        "GET",
        "/api/projects/p1/events",
        headers={"Host": f"127.0.0.1:{app.port}", "Authorization": f"Bearer {app.ui}", "Last-Event-ID": "x"},
    )
    assert c.getresponse().status == 400
    c.close()


def test_used_reports_conversions(app):
    ok, r = app.mcp_apply({"op": "add_marker", "at_s": 1.5, "label": "m"})
    assert ok and r["used"] == {"at_s": {"ticks": 1058400000, "seconds": 1.5}}
    assert O.Oplog  # the engine never sees _s
    assert "at_s" not in (app.proj.dir / "oplog.jsonl").read_text()


# --------------------------------------------------------------------------- Glyph's fixes (Ada, 8:29 PM)


def test_get_routes_url_decode_the_project_id_like_post(app):
    ok, _ = app.rest_apply({"op": "add_marker", "at": 0, "label": "m"})
    assert ok
    for rest in ("hash", "status", "history", "history/diff?since_version=0"):
        st, _, plain = app.req("GET", f"/api/projects/p1/{rest}", token=app.ui)
        st2, _, enc = app.req("GET", f"/api/projects/%70%31/{rest}", token=app.ui)
        assert st == st2 == 200 and plain == enc, rest
    args = app.apply_args({"op": "add_marker", "at": S, "label": "n"})
    st, _, r = app.req("POST", "/api/projects/%70%31/timeline_apply", args, app.ui)
    assert st == 200 and r["new_version"] == 2
    st, _, e = app.req("GET", "/api/projects/%7A%7A/hash", token=app.ui)
    assert st != 200 and e["code"] == "not_found" and e["id"] == "zz"
    # decoded exactly once, after the split, on both methods: %25 stays a literal '%', %2F stays in the id
    for raw, want in (("%2570%2531", "%70%31"), ("p%2F1", "p/1")):
        st, _, g = app.req("GET", f"/api/projects/{raw}/hash", token=app.ui)
        st2, _, w = app.req(
            "POST", f"/api/projects/{raw}/timeline_apply", app.apply_args({"op": "add_marker", "at": 0, "label": "m"}), app.ui
        )
        assert st == st2 != 200 and g["code"] == w["code"] == "not_found" and g["id"] == w["id"] == want, (g, w)


def test_get_mcp_stream_hears_projects_opened_mid_stream(app):
    import http.client

    from hermes_studio import project as P

    c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=10)
    c.request("GET", "/mcp", headers={"Host": f"127.0.0.1:{app.port}", "Authorization": f"Bearer {app.agent}"})
    r = c.getresponse()
    assert r.status == 200 and r.getheader("Content-Type").startswith("text/event-stream")
    doc2 = base()
    doc2["id"] = "p2"
    d2 = P.create_project(doc2)  # after the stream connected; the engine opens it lazily on first use
    (d2 / "mode.json").write_text('{"mode": "auto"}')  # S8: agent writes apply (this test predates the gate)
    assert "p2" not in app.eng.projects
    ok, res = app.mcp(
        "timeline_apply",
        {
            "project_id": "p2",
            "base_version": 0,
            "summary": "s",
            "client_op_id": "k",
            "ops": [{"op": "add_marker", "at": 0, "label": "m"}],
        },
    )
    assert ok, res
    app.mcp_apply({"op": "add_marker", "at": 0, "label": "m"})
    uris = []
    while len(uris) < 2:
        line = r.fp.readline().decode()
        if line.startswith("data: "):
            note = json.loads(line[6:])
            assert note["method"] == "notifications/resources/updated"
            uris.append(note["params"]["uri"])
    assert uris == ["timeline://p2", "timeline://p1"]
    c.close()
