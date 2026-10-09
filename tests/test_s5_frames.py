"""S5 frame cache and frame tools (Prove C10): keys follow what is visible at t, edits elsewhere
keep frames cached, v(n) "after" is v(n+1) "before", the LRU cap holds."""

from __future__ import annotations

import base64
import io
import json
import shutil

import pytest
from s3_app import App
from test_oplog import S, base
from test_s4_media import make_video, wait_ready

from hermes_studio import frames as F
from hermes_studio import mcp_timeline as MT
from hermes_studio import oplog as O
from hermes_studio import timeline as T

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="needs ffmpeg")
HUMAN = O.Session(O.Actor("human", "user"))


def doc_of(log: O.Oplog) -> dict:
    return log.doc


def apply(log: O.Oplog, *ops: dict) -> dict:
    return log.call(
        HUMAN,
        "timeline_apply",
        {"client_op_id": f"k{log.version}", "base_version": log.version, "summary": "e", "ops": list(ops)},
    )


# --------------------------------------------------------------------------- recipe keys (no pixels)


def test_recipe_lists_only_what_is_visible():
    doc = T.stamp_hash(base())[0]
    r = F.recipe_at(doc, S // 2)  # c1 (m1 [0, 4s) at 0), mu1 is audio, x1 is at c2 + 1s = 5s
    assert (
        [v["media"] for v in r["video"]] == ["m1"] and r["text"] == [] and r["size"] == [320, round(320 * 1920 / 1080) // 2 * 2]
    )
    assert r["video"][0]["frame"] == 15  # 0.5 s at 30 fps
    r5 = F.recipe_at(doc, 5 * S + S // 2)
    assert [x["text"] for x in r5["text"]] == ["Hi"] and r5["video"][0]["src_t"] == 11 * S + S // 2
    gap = F.recipe_at(doc, 8 * S)  # c2 ends at 8s, c3 starts at 10s
    assert gap["video"] == [] and F.key_of(gap) != F.key_of(F.recipe_at(doc, S))


def test_c10_an_edit_elsewhere_keeps_the_key():
    log = O.Oplog(base())
    k5 = F.key_of(F.recipe_at(log.doc, S // 2))
    apply(log, {"op": "move_clip", "id": "c3", "at": 40 * S})  # far from 0.5 s
    apply(log, {"op": "add_marker", "at": 0, "label": "m"})  # markers aren't pixels
    assert F.key_of(F.recipe_at(log.doc, S // 2)) == k5 and log.doc["hash"] != T.stamp_hash(base())[0]["hash"]
    apply(log, {"op": "set_fade", "id": "c1", "fade_in": S})  # this one shows at 0.5 s
    assert F.key_of(F.recipe_at(log.doc, S // 2)) != k5


def test_c10_after_of_one_entry_is_before_of_the_next():
    log = O.Oplog(base())
    a = apply(log, {"op": "set_fade", "id": "c1", "fade_in": S})
    b = apply(log, {"op": "set_fade", "id": "c1", "fade_in": 2 * S})
    ea, eb = F.entry_frames(log, a["op_id"]), F.entry_frames(log, b["op_id"])
    assert ea["at"] == eb["at"] == 0
    assert F.key_of(ea["after"]) == F.key_of(eb["before"]) and F.key_of(ea["before"]) != F.key_of(ea["after"])
    assert ea["before_version"] == 0 and eb["after_version"] == 2


def test_first_changed_time_is_the_earliest_touched_start():
    log = O.Oplog(base())
    r = apply(log, {"op": "move_clip", "id": "c3", "at": 30 * S})
    assert F.entry_frames(log, r["op_id"])["at"] == 10 * S  # before: c3 started at 10 s
    r = apply(log, {"op": "add_marker", "at": 7 * S, "label": "m"})
    assert F.entry_frames(log, r["op_id"])["at"] == 7 * S
    assert F.entry_frames(log, "op-nope") == {}


def test_frames_snap_to_source_frames():
    doc = T.stamp_hash(base())[0]
    one = S // 30
    assert F.key_of(F.recipe_at(doc, one)) == F.key_of(F.recipe_at(doc, one + one // 3))  # same source frame
    assert F.key_of(F.recipe_at(doc, one)) != F.key_of(F.recipe_at(doc, 2 * one))


def test_transition_mixes_both_clips():
    log = O.Oplog(base())
    apply(log, {"op": "move_clip", "id": "c2", "at": 3 * S}, {"op": "add_transition", "between": ["c1", "c2"], "dur": S})
    r = F.recipe_at(log.doc, 3 * S + S // 4)
    assert [v["media"] for v in r["video"]] == ["m1", "m1"] and r["video"][1]["mix"] == "1/4"


# --------------------------------------------------------------------------- pixels and the cache


@pytest.fixture
def real(tmp_path, monkeypatch):
    """A doc whose m1 is a real 12 s testsrc video."""
    monkeypatch.setenv("HOME", str(tmp_path))
    src = make_video(tmp_path / "v.mp4", seconds=30, audio=False)
    d = base()
    d["media"]["m1"]["path"] = str(src)
    d["media"]["m1"]["dur"] = 30 * S
    return T.stamp_hash(d)[0], tmp_path


def _img(b: bytes):
    from PIL import Image

    return Image.open(io.BytesIO(b)).convert("RGB")


def test_render_draws_video_fades_and_text(real):
    doc, d = real
    shown = _img(F.render(F.recipe_at(doc, S), d))
    assert shown.size == (320, 568) and max(shown.getextrema()[0]) > 100  # testsrc is colourful
    black = _img(F.render(F.recipe_at(doc, 8 * S + S // 2), d))  # the gap
    assert black.getextrema() == ((0, 0), (0, 0), (0, 0))
    log = O.Oplog(doc)
    apply(log, {"op": "set_fade", "id": "c1", "fade_in": 2 * S})
    faded = _img(F.render(F.recipe_at(log.doc, S // 30), d))
    from PIL import ImageStat

    assert ImageStat.Stat(faded.convert("L")).mean[0] < ImageStat.Stat(shown.convert("L")).mean[0] / 10
    texted = F.render(F.recipe_at(doc, 5 * S + S // 2), d)  # x1 "Hi" shows 5-6 s over c2
    log2 = O.Oplog(doc)
    apply(log2, {"op": "edit_text", "id": "x1", "text": " "})
    plain = F.render(F.recipe_at(log2.doc, 5 * S + S // 2), d)
    assert plain != texted and _img(plain).size == _img(texted).size


def test_cache_hits_and_lru_cap(real):
    doc, d = real
    c = F.FrameCache(d / "p")
    k, p, hit = c.get(F.recipe_at(doc, S))
    assert not hit and p.is_file() and p.name == f"{k}.jpg"
    k2, _, hit = c.get(F.recipe_at(doc, S))
    assert hit and k2 == k and (c.hits, c.misses) == (1, 1)
    size = p.stat().st_size
    c.cap = int(size * 3.5)
    import os
    import time

    keys = [k]
    for i, t in enumerate((2 * S, 3 * S, 11 * S, 12 * S)):
        time.sleep(0.01)
        keys.append(c.get(F.recipe_at(doc, t))[0])
        if i == 1:
            os.utime(c.path(k))  # touch the first: now the 2 s frame is the oldest
    left = {f.stem for f in c.dir.glob("*.jpg")}
    assert sum(f.stat().st_size for f in c.dir.glob("*.jpg")) <= c.cap
    assert k in left and keys[1] not in left and keys[-1] in left


# --------------------------------------------------------------------------- tools over /mcp


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(base())
    yield a
    a.close()


def raw_call(app: App, name: str, args: dict, token: str | None = None) -> dict:
    st, _, j = app.rpc("tools/call", {"name": name, "arguments": {"project_id": "p1", **args}}, token)
    assert st == 200
    return j["result"]


def test_frame_tools_end_to_end(app, tmp_path):
    src = make_video(tmp_path / "talk.mp4", seconds=8)
    ok, imp = app.mcp("import_media", {"project_id": "p1", "path": str(src)})
    assert ok, imp
    wait_ready(app, imp["media_id"])
    ok, ins = app.mcp_apply({"op": "insert_clip", "track": "V1", "media": imp["media_id"], "src": [0, 4 * S], "at": 20 * S})
    assert ok, ins
    r = raw_call(app, "timeline_frames", {"at_s": [20.5, 1]})
    assert not r["isError"] and [c["type"] for c in r["content"]] == ["text", "image", "image"]
    frames = r["structuredContent"]["frames"]
    assert [f["cached"] for f in frames] == [False, False] and frames[0]["at"] == 20 * S + S // 2
    img = _img(base64.b64decode(r["content"][1]["data"]))
    assert img.size[0] == 320
    again = raw_call(app, "timeline_frames", {"at_s": [20.5], "images": False})
    assert again["structuredContent"]["frames"][0] == {**frames[0], "cached": True} and len(again["content"]) == 1
    # an edit elsewhere leaves 20.5 s cached
    app.mcp_apply({"op": "add_marker", "at": 0, "label": "m"})
    assert raw_call(app, "timeline_frames", {"at_s": [20.5], "images": False})["structuredContent"]["frames"][0]["cached"]
    h = raw_call(app, "history_frames", {"op_id": ins["op_id"]})
    hs = h["structuredContent"]
    assert not h["isError"] and hs["at"] == 20 * S and hs["before_version"] == 1 and hs["after_version"] == 2, hs
    now = raw_call(app, "timeline_frames", {"at": [20 * S], "images": False})["structuredContent"]["frames"][0]
    assert now["key"] == hs["after"]["key"] and now["cached"]  # v2's "after" is today's frame (the marker didn't touch it)
    assert hs["before"]["key"] != hs["after"]["key"] and len(h["content"]) == 3
    sheet = raw_call(app, "timeline_contact_sheet", {"count": 6, "cols": 3})
    ss = sheet["structuredContent"]
    assert not sheet["isError"] and len(ss["frames"]) == 6 and ss["to"] == 24 * S and len(sheet["content"]) == 2
    s_img = _img(base64.b64decode(sheet["content"][1]["data"]))
    assert s_img.size[0] == 3 * 320


@pytest.mark.parametrize(
    "name, args, want",
    [
        ("timeline_frames", {}, ("missing_arg", "/at_s")),
        ("timeline_frames", {"at_s": [1], "at": [1]}, ("bad_arg", "/at_s")),
        ("timeline_frames", {"at_s": []}, ("bad_arg", "/at_s")),
        ("timeline_frames", {"at_s": [1] * 13}, ("bad_arg", "/at_s")),
        ("timeline_frames", {"at_s": [-1]}, ("bad_arg", "/at_s/0")),
        ("timeline_frames", {"at_s": [True]}, ("bad_arg", "/at_s/0")),
        ("timeline_frames", {"at": [1.5]}, ("bad_arg", "/at/0")),
        ("timeline_frames", {"at_s": [1], "width": 5000}, ("bad_arg", "/width")),
        ("timeline_frames", {"at_s": [1], "images": "no"}, ("bad_arg", "/images")),
        ("timeline_frames", {"at_s": [1], "zz": 1}, ("unknown_arg", "/zz")),
        ("timeline_contact_sheet", {"count": 0}, ("bad_arg", "/count")),
        ("timeline_contact_sheet", {"from_s": 5, "to_s": 5}, ("bad_arg", "/to_s")),
        ("timeline_contact_sheet", {"cols": 13}, ("bad_arg", "/cols")),
        ("history_frames", {}, ("missing_arg", "/op_id")),
        ("history_frames", {"op_id": 5}, ("bad_arg", "/op_id")),
        ("history_frames", {"op_id": "op-nope"}, ("not_found", "/op_id")),
    ],
)
def test_frame_tool_refusals(app, name, args, want):
    r = raw_call(app, name, args)
    assert r["isError"]
    e = json.loads(r["content"][-1]["text"])
    assert (e.get("rule"), e.get("path")) == want, e


def test_frame_tools_need_render_scope_and_a_running_app(app, tmp_path):
    no_render = app.eng.tokens.mint("mcp:nr", scopes={"read", "write"})
    e = json.loads(raw_call(app, "timeline_frames", {"at_s": [1]}, no_render)["content"][-1]["text"])
    assert e["code"] == "permission_denied" and "render" in e["error"]
    r = MT.call("timeline_frames", {"project_id": "p1", "at_s": [1]}, MT.ClosedBackend())
    assert r["isError"] and json.loads(r["content"][-1]["text"])["code"] == "engine_offline"
    r = MT.call("timeline_frames", {"project_id": "nope", "at_s": [1]}, MT.ClosedBackend())
    assert json.loads(r["content"][-1]["text"])["code"] == "not_found"


def test_rest_frame_route(app):
    import http.client

    def get(path: str, token: str | None):
        c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=30)
        hd = {"Host": f"127.0.0.1:{app.port}"}
        if token:
            hd["Authorization"] = f"Bearer {token}"
        c.request("GET", path, headers=hd)
        r = c.getresponse()
        body = r.read()
        c.close()
        return r, body

    r, body = get(f"/api/projects/p1/frame?at={S}&width=160", app.ui)
    assert r.status == 200 and r.getheader("Content-Type") == "image/jpeg" and r.getheader("X-Frame-Cached") == "0"
    assert _img(body).size == (160, 284)
    r2, _ = get(f"/api/projects/p1/frame?at={S}&width=160", app.ui)
    assert r2.getheader("X-Frame-Cached") == "1" and r2.getheader("X-Frame-Key") == r.getheader("X-Frame-Key")
    r, body = get("/api/projects/p1/frame", app.ui)
    assert r.status == 400 and json.loads(body)["path"] == "/at"
    r, body = get("/api/projects/p1/frame?at=-1", app.ui)
    assert r.status == 400 and json.loads(body)["path"] == "/at"
    nr = app.eng.tokens.mint("mcp:nr", scopes={"read"})
    r, body = get(f"/api/projects/p1/frame?at={S}", nr)
    assert r.status == 403
