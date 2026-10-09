"""S6 render v1 (Prove C11 / E4): a 3-clip + xfade + text + captions timeline renders to H.264/AAC
1080x1920 with duration and frame count within one frame, and SSIM >= 0.98 at five timestamps
against reference frames cut straight from the source with an independent FFmpeg command."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from s3_app import App
from test_s4_media import make_video, wait_ready

from hermes_studio import mcp_timeline as MT
from hermes_studio import media as M
from hermes_studio import render_timeline as R
from hermes_studio import timeline as T

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="needs ffmpeg")
S = T.TICK_RATE
SSIM_MIN = 0.98


def empty() -> dict:
    return T.new_timeline("p1")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(empty())
    yield a
    a.close()


def wait_render(app: App, rid: str, timeout: float = 240) -> dict:
    end = time.monotonic() + timeout
    while True:
        ok, st = app.mcp("render_status", {"project_id": "p1", "render_id": rid})
        assert ok, st
        if st["state"] not in ("queued", "running"):
            return st
        assert time.monotonic() < end, st
        time.sleep(0.2)


def ffprobe(path: Path) -> dict:
    p = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,nb_read_frames,duration:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(p.stdout)


def frame_png(src: Path, sec: float, dest: Path, vf: str = "") -> Path:
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{sec:.6f}", "-i", str(src), "-frames:v", "1"]
    subprocess.run([*cmd, *(["-vf", vf] if vf else []), str(dest)], check=True)
    return dest


def ssim(a: Path, b: Path) -> float:
    p = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(a), "-i", str(b), "-lavfi", "ssim", "-f", "null", "-"], capture_output=True, text=True
    )
    m = re.search(r"All:([0-9.]+)", p.stderr)
    assert m, p.stderr[-500:]
    return float(m.group(1))


def build_c11(app: App, src: Path) -> str:
    """c1 [0,3) src 0-3 s; c2 [2,5) src 5-8 s with a 1 s xfade from c1; c3 [5,8) src 10-13 s with a
    0.5 s fade out; title 0-1 s; a caption word 6-7 s. Returns the media id."""
    ok, imp = app.mcp("import_media", {"project_id": "p1", "path": str(src), "stages": ["proxy"]})
    assert ok, imp
    mid = imp["media_id"]
    wait_ready(app, mid)
    ops = [
        {"op": "insert_clip", "track": "V1", "media": mid, "src_s": [0, 3], "at_s": 0, "id": "c1"},
        {"op": "insert_clip", "track": "V1", "media": mid, "src_s": [5, 8], "at_s": 2, "id": "c2"},
        {"op": "insert_clip", "track": "V1", "media": mid, "src_s": [10, 13], "at_s": 5, "id": "c3", "fade_out_s": 0.5},
        {"op": "add_transition", "between": ["c1", "c2"], "dur_s": 1},
        {"op": "add_text", "text": "Hermes", "style": "pop", "at_s": 0, "dur_s": 1},
    ]
    ok, r = app.mcp_apply(*ops)
    assert ok, r
    M._write_json(M.cache_paths(app.proj.dir, mid)["words"], {"words": [{"w": "hello", "in": 11 * S, "out": 12 * S}]})
    return mid


def test_c11_render_ffprobe_and_ssim(app, tmp_path):
    src = make_video(tmp_path / "talk.mp4", seconds=16, size="1280x720", rate=30)
    build_c11(app, src)
    doc = app.proj.log.doc
    assert R.timeline_end(doc) == 8 * S and doc["size"] == [1080, 1920] and doc["fps"] == [30, 1]
    ok, r = app.mcp("render_timeline", {"project_id": "p1"})
    assert ok, r
    assert r["render_id"] == f"v{doc['version']:06d}-1080x1920-cap" and r["captions"] and not r["reused"]
    st = wait_render(app, r["render_id"])
    assert st["state"] == "ready", st
    out = app.proj.dir / st["path"]
    info = ffprobe(out)
    streams = {s["codec_type"]: s for s in info["streams"]}
    assert len(info["streams"]) == 2 and streams["video"]["codec_name"] == "h264" and streams["audio"]["codec_name"] == "aac"
    v = streams["video"]
    assert (v["width"], v["height"]) == (1080, 1920)
    frame = 1 / 30
    assert abs(float(info["format"]["duration"]) - 8.0) <= frame + 0.03  # container end incl. AAC padding
    assert abs(float(v["duration"]) - 8.0) <= frame
    assert abs(int(v["nb_read_frames"]) - 240) <= 1
    # SSIM at five timestamps against frames cut from the source independently
    # the reference goes through 4:2:0 like any H.264 delivery: a straight-to-RGB scale keeps full-res chroma and
    # scores ~0.979 even against a lossless 4:2:0 encode of the same frame
    cover = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p"
    for t, src_t in ((1.5, 1.5), (3.5, 6.5), (4.5, 7.5), (5.5, 10.5), (7.2, 12.2)):
        got = frame_png(out, t, tmp_path / f"got-{t}.png")
        ref = frame_png(src, src_t, tmp_path / f"ref-{t}.png", cover)
        score = ssim(got, ref)
        assert score >= SSIM_MIN, (t, score)
    # the crossfade midpoint is a blend of both clips; the title and caption are drawn
    mid = frame_png(out, 2.5, tmp_path / "mid.png")
    a = frame_png(src, 2.5, tmp_path / "a.png", cover)
    b = frame_png(src, 5.5, tmp_path / "b.png", cover)
    assert ssim(mid, a) < 0.97 and ssim(mid, b) < 0.97
    titled = frame_png(out, 0.5, tmp_path / "titled.png")
    assert ssim(titled, frame_png(src, 0.5, tmp_path / "plain.png", cover)) < 0.995
    # the same request reuses the render
    ok, again = app.mcp("render_timeline", {"project_id": "p1"})
    assert ok and again["reused"] and again["render_id"] == r["render_id"] and again["state"] == "ready"


def test_render_without_captions_and_small_size(app, tmp_path):
    src = make_video(tmp_path / "talk.mp4", seconds=16, size="320x180", rate=30)
    build_c11(app, src)
    ok, r = app.mcp("render_timeline", {"project_id": "p1", "width": 270, "height": 480, "captions": False})
    assert ok and r["render_id"].endswith("-270x480") and not r["captions"]
    st = wait_render(app, r["render_id"])
    assert st["state"] == "ready" and st["bytes"] > 0
    v = next(s for s in ffprobe(app.proj.dir / st["path"])["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (270, 480) and abs(int(v["nb_read_frames"]) - 240) <= 1


def test_render_progress_events(app, tmp_path):
    import http.client

    src = make_video(tmp_path / "v.mp4", seconds=16, size="320x180")
    build_c11(app, src)
    c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=60)
    c.request(
        "GET",
        "/api/projects/p1/events?",
        headers={
            "Host": f"127.0.0.1:{app.port}",
            "Authorization": f"Bearer {app.ui}",
            "Last-Event-ID": str(len(app.proj.log._entries)),
        },
    )
    resp = c.getresponse()
    ok, r = app.mcp("render_timeline", {"project_id": "p1", "width": 180, "height": 320})
    assert ok, r
    evs = []
    while not evs or evs[-1]["type"] not in ("render.ready", "render.failed"):
        line = resp.fp.readline().decode()
        assert not line.startswith("id: ")
        if line.startswith("data: "):
            evs.append(json.loads(line[6:]))
    c.close()
    assert evs[-1]["type"] == "render.ready" and evs[-1]["render_id"] == r["render_id"]
    prog = [e["progress"] for e in evs if e["type"] == "render.progress"]
    assert prog == sorted(prog) and prog[-1] == 1.0


@pytest.mark.parametrize(
    "args, want",
    [
        ({"width": 1081}, ("bad_arg", "/width")),
        ({"height": 8}, ("bad_arg", "/height")),
        ({"width": True}, ("bad_arg", "/width")),
        ({"captions": "yes"}, ("bad_arg", "/captions")),
        ({"zz": 1}, ("unknown_arg", "/zz")),
    ],
)
def test_render_refusals(app, args, want):
    ok, e = app.mcp("render_timeline", {"project_id": "p1", **args})
    assert not ok and (e["rule"], e["path"]) == want, e


def test_render_empty_timeline_scope_status_and_closed(app):
    ok, e = app.mcp("render_timeline", {"project_id": "p1"})
    assert not ok and e["rule"] == "bad_arg" and "empty" in e["error"]
    nr = app.eng.tokens.mint("mcp:nr", scopes={"read", "write"})
    ok, e = app.mcp("render_timeline", {"project_id": "p1"}, token=nr)
    assert not ok and e["code"] == "permission_denied"
    for rid, code in (("v000001-1080x1920", "not_found"), ("../x", "not_found")):
        ok, e = app.mcp("render_status", {"project_id": "p1", "render_id": rid})
        assert not ok and e["code"] == code and e["id"] == rid
    ok, e = app.mcp("render_status", {"project_id": "p1"})
    assert not ok and e["rule"] == "missing_arg"
    r = MT.call("render_timeline", {"project_id": "p1"}, MT.ClosedBackend())
    assert json.loads(r["content"][-1]["text"])["code"] == "engine_offline"


def test_windows_split_long_timelines_outside_transitions():
    d = T.new_timeline("p1")
    d["media"] = {"m1": {"path": "/x.mp4", "dur": 1000 * S, "fps": [30, 1]}}
    v1 = next(t for t in d["tracks"] if t["id"] == "V1")
    v1["items"] = [
        {"id": f"c{i}", "type": "clip", "media": "m1", "src": [i * S, (i + 1) * S], "at": i * S, "fade_in": 0, "fade_out": 0}
        for i in range(100)
    ]
    d = T.stamp_hash(d)[0]
    assert R.windows(d, 40) == [(0, 40 * S), (40 * S, 80 * S), (80 * S, 100 * S)]
    assert R.windows(d, 200) == [(0, 100 * S)]


def test_segmented_render_matches_frame_count(app, tmp_path):
    src = make_video(tmp_path / "talk.mp4", seconds=16, size="320x180")
    build_c11(app, src)
    doc = app.proj.log.doc
    out = tmp_path / "seg.mp4"
    res = R.render(doc, app.proj.dir, out, size=(180, 320), segment_over=1)
    assert (
        res["segments"] == 3
    )  # cuts at 2 s and 5 s: a cut at a transition's start is fine (clips are built whole, then trimmed)
    v = next(s for s in ffprobe(out)["streams"] if s["codec_type"] == "video")
    assert abs(int(v["nb_read_frames"]) - 240) <= 1


def test_rest_render_status_and_file(app, tmp_path):
    import http.client

    src = make_video(tmp_path / "v.mp4", seconds=16, size="320x180")
    build_c11(app, src)
    st, _, r = app.req("POST", "/api/projects/p1/render_timeline", {"width": 180, "height": 320}, app.ui)
    assert st == 200 and r["render_id"].startswith("v")
    rid = r["render_id"]
    st, _, early = app.req("GET", f"/api/projects/p1/renders/{rid}/file", token=app.ui)
    assert st in (200, 409)
    wait_render(app, rid)
    st, _, s = app.req("GET", f"/api/projects/p1/renders/{rid}", token=app.ui)
    assert st == 200 and s["state"] == "ready"
    c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=30)
    c.request(
        "GET",
        f"/api/projects/p1/renders/{rid}/file",
        headers={"Host": f"127.0.0.1:{app.port}", "Authorization": f"Bearer {app.ui}", "Range": "bytes=0-99"},
    )
    resp = c.getresponse()
    body = resp.read()
    c.close()
    assert resp.status == 206 and resp.getheader("Content-Type") == "video/mp4" and len(body) == 100
    st, _, e = app.req("GET", "/api/projects/p1/renders/..%2F..%2Fbase/file", token=app.ui)
    assert st == 404 and e["code"] == "not_found"
    nr = app.eng.tokens.mint("mcp:nr", scopes={"read", "write"})
    st, _, e = app.req("POST", "/api/projects/p1/render_timeline", {}, nr)
    assert st == 403


def test_captions_use_the_clip_styles(app, tmp_path):
    src = make_video(tmp_path / "talk.mp4", seconds=16, size="320x180")
    build_c11(app, src)
    ok, e = app.mcp("render_timeline", {"project_id": "p1", "caption_style": "comic"})
    assert not ok and (e["rule"], e["path"]) == ("bad_arg", "/caption_style")
    ok, r = app.mcp("render_timeline", {"project_id": "p1", "width": 360, "height": 640, "caption_style": "impact"})
    assert ok and r["render_id"].endswith("-360x640-cap-impact"), r
    st = wait_render(app, r["render_id"])
    assert st["state"] == "ready", st
    out = app.proj.dir / st["path"]
    cover = "scale=360:640:force_original_aspect_ratio=increase,crop=360:640,format=yuv420p"
    # 6.5 s is inside the caption word "hello" (c3 shows src 11-12 s at 6-7 s); 5.5 s has no caption
    with_cap = ssim(frame_png(out, 6.5, tmp_path / "c.png"), frame_png(src, 11.5, tmp_path / "cr.png", cover))
    without = ssim(frame_png(out, 5.5, tmp_path / "n.png"), frame_png(src, 10.5, tmp_path / "nr.png", cover))
    assert without > 0.95 and with_cap < without - 0.01, (with_cap, without)
    ok, s2 = app.mcp("render_status", {"project_id": "p1", "render_id": r["render_id"]})
    assert ok and s2["state"] == "ready"


def test_render_cancel_queued_and_running(app, tmp_path):
    src = make_video(tmp_path / "v.mp4", seconds=16, size="320x180")
    build_c11(app, src)
    ok, a = app.mcp("render_timeline", {"project_id": "p1", "width": 180, "height": 320})
    ok2, b = app.mcp("render_timeline", {"project_id": "p1", "width": 270, "height": 480})  # waits behind a
    assert ok and ok2 and b["state"] == "queued"
    ok, cb = app.mcp("render_cancel", {"project_id": "p1", "render_id": b["render_id"]})
    assert ok and cb["cancelling"], cb
    st, _, ca = app.req("POST", "/api/projects/p1/render_cancel", {"render_id": a["render_id"]}, app.ui)
    assert st == 200 and ca["render_id"] == a["render_id"]

    def settled(rid: str) -> dict:
        end = time.monotonic() + 60
        while time.monotonic() < end:
            ok, s = app.mcp("render_status", {"project_id": "p1", "render_id": rid})
            if s["state"] not in ("queued", "running"):
                return s
            time.sleep(0.1)
        raise AssertionError(rid)

    assert settled(b["render_id"])["state"] == "cancelled"
    assert settled(a["render_id"])["state"] in ("cancelled", "ready")  # it may have finished first
    ok, again = app.mcp("render_cancel", {"project_id": "p1", "render_id": b["render_id"]})
    assert ok and not again["cancelling"] and again["state"] == "cancelled"
    ok, fresh = app.mcp("render_timeline", {"project_id": "p1", "width": 270, "height": 480})
    assert ok and not fresh["reused"] and settled(b["render_id"])["state"] == "ready"  # a cancelled render starts afresh
    ok, e = app.mcp("render_cancel", {"project_id": "p1", "render_id": "v000099-180x320"})
    assert not ok and e["code"] == "not_found"


def test_render_again_after_stop_starts_afresh(app, monkeypatch, tmp_path):
    """Stop, then Render at once (before the stopped job has let go): the second render is a new
    job that finishes, and the stopped one can't overwrite its status."""
    import threading

    from hermes_studio import render_jobs as RJ

    gate = threading.Event()
    calls = []

    def fake(doc, project_dir, out, size, words, caption_style, on_progress, cancel):
        calls.append(out)
        while not gate.is_set():
            if cancel():
                raise RuntimeError("stopped")
            time.sleep(0.01)
        out.write_bytes(b"mp4")
        return {"segments": 1, "clips": 1}

    monkeypatch.setattr(RJ.R, "render", fake)
    monkeypatch.setattr(RJ.R, "timeline_end", lambda doc: 1)
    ok, a = app.mcp("render_timeline", {"project_id": "p1", "captions": False})
    assert ok and a["state"] == "queued", a
    end = time.monotonic() + 10
    while not calls and time.monotonic() < end:
        time.sleep(0.01)
    ok, _ = app.mcp("render_cancel", {"project_id": "p1", "render_id": a["render_id"]})
    ok, b = app.mcp("render_timeline", {"project_id": "p1", "captions": False})  # before the first has let go
    assert ok and not b["reused"] and b["state"] == "queued", b
    gate.set()
    end = time.monotonic() + 10
    while time.monotonic() < end:
        ok, st = app.mcp("render_status", {"project_id": "p1", "render_id": a["render_id"]})
        if st["state"] == "ready":
            break
        time.sleep(0.02)
    assert st["state"] == "ready" and len(calls) == 2, (st, calls)
