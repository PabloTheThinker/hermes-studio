"""Shot changes: the S4 `scenes` stage, `get_scenes` through the clips, and the REST route."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from s3_app import App
from test_s4_media import make_audio, wait_ready

from hermes_studio import media as M
from hermes_studio import timeline as T

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="needs ffmpeg")
S = T.TICK_RATE


def three_shots(path: Path) -> Path:
    """3 s testsrc, 3 s colour bars, 3 s mandelbrot: shot changes at 3 s and 6 s."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=30:duration=3",
            "-f",
            "lavfi",
            "-i",
            "smptebars=size=320x180:rate=30:duration=3",
            "-f",
            "lavfi",
            "-i",
            "mandelbrot=size=320x180:rate=30",
            "-filter_complex",
            "[2:v]trim=duration=3,setpts=PTS-STARTPTS[m];[0:v][1:v][m]concat=n=3:v=1[v]",
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(T.new_timeline("p1"))
    yield a
    a.close()


def test_make_scenes_finds_the_cuts(tmp_path):
    src = three_shots(tmp_path / "v.mp4")
    info = M.probe(src)
    out = M.make_scenes(src, tmp_path / "s.json", info)
    assert out == {"count": 2}
    assert M.read_json(tmp_path / "s.json") == {"threshold": M.SCENE_THRESHOLD, "cuts": [3 * S, 6 * S]}


def test_timeline_scenes_maps_through_clips():
    d = T.new_timeline("p1")
    d["media"] = {"m1": {"path": "/v.mp4", "dur": 9 * S, "fps": [30, 1]}}
    v1 = next(t for t in d["tracks"] if t["id"] == "V1")
    v1["items"] = [
        {"id": "a", "type": "clip", "media": "m1", "src": [S, 8 * S], "at": 10 * S, "fade_in": 0, "fade_out": 0},
        {
            "id": "b",
            "type": "clip",
            "media": "m1",
            "src": [3 * S, 5 * S],
            "at": 17 * S,
            "fade_in": 0,
            "fade_out": 0,
            "props": {"speed": [2, 1]},
        },
    ]
    d = T.stamp_hash(d)[0]
    rows = M.timeline_scenes(d, {"m1": [3 * S, 6 * S]})
    assert [(r["clip"], r["at"]) for r in rows] == [("a", 12 * S), ("a", 15 * S)]  # 3 s is b's start: not inside


def test_import_with_scenes_and_split_at_them(app, tmp_path):
    src = three_shots(tmp_path / "Videos" / "v.mp4")
    ok, r = app.mcp("import_media", {"project_id": "p1", "path": str(src), "stages": ["scenes"]})
    assert ok, r
    st = wait_ready(app, r["media_id"])
    assert st["state"] == "ready" and st["stages"]["scenes"]["count"] == 2
    ok, c = app.mcp_apply({"op": "insert_clip", "track": "V1", "media": r["media_id"], "src_s": [1, 8], "at_s": 0, "id": "c1"})
    assert ok, c
    ok, sc = app.mcp("get_scenes", {"project_id": "p1"})
    assert ok and [(x["clip"], x["at_s"]) for x in sc["cuts"]] == [("c1", 2.0), ("c1", 5.0)]
    st_, _, rest = app.req("GET", "/api/projects/p1/scenes", token=app.ui)
    assert st_ == 200 and rest["cuts"] == sc["cuts"]
    ok, sp = app.mcp_apply(
        {"op": "split_clip", "id": "c1", "at": 5 * S, "ids": ["c1a", "c1b"]},
        {"op": "split_clip", "id": "c1a", "at": 2 * S, "ids": ["c1c", "c1d"]},
    )
    assert ok, sp
    v1 = next(t for t in app.proj.log.doc["tracks"] if t["id"] == "V1")
    assert sorted(T.resolve(app.proj.log.doc)[i["id"]][0] for i in v1["items"]) == [0, 2 * S, 5 * S]
    ok, sc2 = app.mcp("get_scenes", {"project_id": "p1"})
    assert sc2["cuts"] == []  # every shot change now sits on a cut


def test_audio_only_skips_scenes_and_refusals(app, tmp_path):
    ok, r = app.mcp(
        "import_media", {"project_id": "p1", "path": str(make_audio(tmp_path / "a.wav")), "stages": ["scenes", "wave"]}
    )
    assert ok
    st = wait_ready(app, r["media_id"])
    assert set(st["stages"]) == {"wave"}
    ok, e = app.mcp("get_scenes", {"project_id": "p1", "media_id": "zz"})
    assert not ok and e["code"] == "not_found"
    ok, e = app.mcp("get_scenes", {"project_id": "p1", "zz": 1})
    assert not ok and e["rule"] == "unknown_arg"
