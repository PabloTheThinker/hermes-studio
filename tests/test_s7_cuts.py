"""S7 transcript cuts (Prove C12, filler part): a 40+ op filler cut is ONE log entry, and one
undo restores the hash. Plus pauses, ranges, preview, retry, skips and refusals."""

from __future__ import annotations

import pytest
from s3_app import App

from hermes_studio import cuts as CU
from hermes_studio import media as M
from hermes_studio import oplog as O
from hermes_studio import timeline as T

S = T.TICK_RATE
FRAME = S // 30
FILLERS = ("um", "uh", "Um,", "erm")


def doc0() -> dict:
    d = T.new_timeline("p1")
    d["media"] = {"m1": {"path": "/media/talk.mp4", "dur": 300 * S, "fps": [30, 1]}}
    return d


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(doc0())
    ok, r = a.mcp_apply({"op": "insert_clip", "track": "V1", "media": "m1", "src": [0, 120 * S], "at": 0, "id": "c1"})
    assert ok, r
    yield a
    a.close()


def speech(n: int = 80, every: int = 5) -> list[dict]:
    """n words, 0.5 s apart, each 0.3 s long; every ``every``-th one a filler."""
    out = []
    for i in range(n):
        w = FILLERS[i % len(FILLERS)] if i % every == every - 1 else f"word{i}"
        out.append({"w": w, "in": i * S // 2, "out": i * S // 2 + 3 * S // 10})
    return out


def words(app: App, ws: list[dict], mid: str = "m1") -> None:
    M._write_json(M.cache_paths(app.proj.dir, mid)["words"], {"words": ws})


def cut(app: App, **args) -> tuple[bool, dict]:
    base = {"project_id": "p1", "base_version": app.proj.log.version, "client_op_id": f"cut{app.proj.log.version}"}
    return app.mcp("transcript_cut", {**base, **args})


def test_c12_filler_cut_is_one_entry_and_one_undo_restores_the_hash(app):
    words(app, speech())
    before = app.head()
    entries = len(app.proj.log._entries)
    ok, r = cut(app, fillers=True)
    assert ok, r
    assert r["applied"] and len(app.proj.log._entries) == entries + 1  # ONE entry
    line = app.proj.log._entries[-1]
    assert len(line["ops"]) >= 40 and line["summary"].startswith("Cut 16 fillers"), (len(line["ops"]), line["summary"])
    assert len(r["cuts"]) == 16 and r["skipped"] == []
    ok, t = app.mcp("get_transcript", {"project_id": "p1"})
    assert ok and not any(w["w"].strip(",").lower() in ("um", "uh", "erm") for w in t["words"]) and len(t["words"]) == 64
    end = max(e for _, e in T.resolve(app.proj.log.doc).values())
    assert end == 120 * S - r["removed"]
    ok, u = app.mcp("history_undo", {"project_id": "p1", "client_op_id": "undo-cut", "op_id": r["op_id"]})
    assert ok, u
    assert app.head()["hash"] == before["hash"]


def test_cut_keeps_frame_grid_and_word_order(app):
    words(app, speech())
    ok, r = cut(app, fillers=True)
    assert ok
    for c in r["cuts"]:
        assert c["from"] % FRAME == 0 and c["to"] % FRAME == 0
    spans = T.resolve(app.proj.log.doc)
    v1 = next(tr for tr in app.proj.log.doc["tracks"] if tr["id"] == "V1")
    starts = sorted(spans[it["id"]] for it in v1["items"])
    assert all(a[1] == b[0] for a, b in zip(starts, starts[1:], strict=False))  # rippled shut: no gaps
    ok, t = app.mcp("get_transcript", {"project_id": "p1"})
    assert [w["w"] for w in t["words"]] == [w["w"] for w in speech() if w["w"].startswith("word")]


def test_preview_changes_nothing_and_matches_the_cut(app):
    words(app, speech(20))
    h0 = app.head()
    ok, p = cut(app, fillers=True, preview=True)
    assert ok and not p["applied"] and p["ops"] and app.head() == h0
    ok, r = cut(app, fillers=True)
    assert ok and r["cuts"] == p["cuts"] and app.proj.log._entries[-1]["ops"] == p["ops"]


def test_retry_returns_the_same_entry(app):
    words(app, speech(20))
    args = {"base_version": app.proj.log.version, "client_op_id": "same", "fillers": True}
    ok, a = app.mcp("transcript_cut", {"project_id": "p1", **args})
    ok2, b = app.mcp("transcript_cut", {"project_id": "p1", **args})
    assert ok and ok2 and a["op_id"] == b["op_id"] and len(app.proj.log._entries) == 2


def test_pauses_are_cut_down_to_keep_pause(app):
    ws = [{"w": "a", "in": 0, "out": S}, {"w": "b", "in": 4 * S, "out": 5 * S}, {"w": "c", "in": 5 * S + S // 5, "out": 6 * S}]
    words(app, ws)
    ok, r = cut(app, pauses=True)
    assert ok and len(r["cuts"]) == 1 and r["summary"].startswith("Cut 1 pause")
    c = r["cuts"][0]
    assert abs(c["from"] - (S + CU.KEEP_PAUSE // 2)) <= FRAME and abs(c["to"] - (4 * S - CU.KEEP_PAUSE // 2)) <= FRAME
    ok, t = app.mcp("get_transcript", {"project_id": "p1"})
    gap = t["words"][1]["at"] - t["words"][0]["end"]
    assert abs(gap - CU.KEEP_PAUSE) <= 2 * FRAME


def test_ranges_across_clips_and_whole_clip_starts(app):
    ok, r = app.mcp_apply(
        {"op": "insert_clip", "track": "V1", "media": "m1", "src": [200 * S, 210 * S], "at": 120 * S, "id": "c2"}
    )
    assert ok, r
    ok, r = cut(app, ranges=[{"from_s": 115, "to_s": 125}, {"from_s": 0, "to_s": 2}])
    assert ok, r
    assert sorted((c["clip"], c["from"], c["to"]) for c in r["cuts"]) == [
        ("c1", 0, 2 * S),
        ("c1", 115 * S, 120 * S),
        ("c2", 120 * S, 125 * S),
    ]
    assert max(e for _, e in T.resolve(app.proj.log.doc).values()) == 130 * S - 12 * S


def test_ranges_inside_a_transition_are_skipped(app):
    ok, r = app.mcp_apply(
        {"op": "insert_clip", "track": "V1", "media": "m1", "src": [200 * S, 210 * S], "at": 119 * S, "id": "c2"},
        {"op": "add_transition", "between": ["c1", "c2"], "dur": S},
    )
    assert ok, r
    ok, r = cut(app, ranges=[{"from_s": 119.2, "to_s": 119.8}, {"from_s": 10, "to_s": 11}])
    assert ok and [s["why"] for s in r["skipped"]] == ["inside a transition", "inside a transition"]
    assert [(c["clip"], c["from"]) for c in r["cuts"]] == [("c1", 10 * S)]


def test_nothing_to_cut_writes_nothing(app):
    words(app, [{"w": "hello", "in": 0, "out": S}])
    h0 = app.head()
    ok, r = cut(app, fillers=True)
    assert ok and not r["applied"] and r["cuts"] == [] and app.head() == h0


def test_stale_base_version_is_the_engines_conflict(app):
    words(app, speech(20))
    app.mcp_apply({"op": "add_marker", "at": 0, "label": "m"})
    ok, e = app.mcp("transcript_cut", {"project_id": "p1", "base_version": 0, "client_op_id": "old", "fillers": True})
    assert not ok and e["code"] == "conflict" and "history_diff" in e


@pytest.mark.parametrize(
    "args, want",
    [
        ({}, ("missing_arg", "/fillers")),
        ({"fillers": "yes"}, ("bad_arg", "/fillers")),
        ({"ranges": "0-1"}, ("bad_arg", "/ranges")),
        ({"ranges": [{"from_s": 2, "to_s": 1}]}, ("bad_arg", "/ranges/0/to_s")),
        ({"ranges": [{"from_s": -1, "to_s": 1}]}, ("bad_arg", "/ranges/0/from_s")),
        ({"ranges": [{"from": 0, "to": 1}]}, ("bad_arg", "/ranges/0")),
        ({"fillers": True, "zz": 1}, ("unknown_arg", "/zz")),
        ({"fillers": True, "preview": 1}, ("bad_arg", "/preview")),
    ],
)
def test_cut_refusals(app, args, want):
    h0 = app.head()
    ok, e = cut(app, **args)
    assert not ok and (e["rule"], e["path"]) == want, e
    assert app.head() == h0


def test_envelope_is_the_engines(app):
    ok, e = app.mcp("transcript_cut", {"project_id": "p1", "fillers": True, "client_op_id": "x"})
    assert not ok and (e["rule"], e["path"]) == ("missing_arg", "/base_version")
    ok, e = app.mcp("transcript_cut", {"project_id": "p1", "fillers": True, "base_version": 1})
    assert not ok and (e["rule"], e["path"]) == ("missing_arg", "/client_op_id")


def test_rest_and_actor(app):
    words(app, speech(20))
    st, _, r = app.req(
        "POST",
        "/api/projects/p1/transcript_cut",
        {"base_version": app.proj.log.version, "client_op_id": "rest", "fillers": True, "actor": {"kind": "human", "id": "x"}},
        app.agent,
    )
    assert st == 200 and r["applied"]
    assert app.proj.log._entries[-1]["actor"] == {"kind": "agent", "id": "claude"}


def test_compile_cuts_unit():
    d = T.stamp_hash(doc0())[0]
    log = O.Oplog(d)
    log.call(
        O.Session(O.Actor("human", "user")),
        "timeline_apply",
        {
            "client_op_id": "a",
            "base_version": 0,
            "summary": "s",
            "ops": [{"op": "insert_clip", "track": "V1", "media": "m1", "src": [0, 10 * S], "at": 0, "id": "c1"}],
        },
    )
    ops, applied, skipped = CU.compile_cuts(log.doc, [(S, 2 * S), (S + S // 2, 3 * S), (9 * S, 10 * S), (5 * S, 5 * S + 10)], "k")
    assert [(a["from"], a["to"]) for a in applied] == [(S, 3 * S), (9 * S, 10 * S)]  # overlapping ranges merged
    assert [s["why"] for s in skipped] == ["shorter than one frame"]
    # last cut first: 9-10 s (to the clip's end: one split), then 1-3 s (two splits), each middle ripple-deleted
    assert [(o["op"], o.get("at")) for o in ops] == [
        ("split_clip", 9 * S),
        ("delete_clip", None),
        ("split_clip", 3 * S),
        ("split_clip", S),
        ("delete_clip", None),
    ]
    log.call(
        O.Session(O.Actor("human", "user")),
        "timeline_apply",
        {"client_op_id": "b", "base_version": 1, "summary": "c", "ops": ops},
    )
    assert max(e for _, e in T.resolve(log.doc).values()) == 7 * S


def test_a_cut_too_big_for_one_entry_is_refused_whole(app):
    words(app, speech(240, every=1))  # 240 fillers in the 120 s clip: 720 ops
    h0 = app.head()
    ok, e = cut(app, fillers=True)
    assert not ok and e["rule"] == "bad_arg" and "500" in e["error"] and app.head() == h0
    ok, p = cut(app, fillers=True, preview=True)  # a preview still shows the whole plan
    assert ok and len(p["cuts"]) == 240
