"""The Phase 1 headline run (PLAN-MERGED §7, scripted): an agent over plain MCP, in Propose mode,
imports a talk, places it trimmed, removes the fillers, adds a title and renders 9:16; a person
approves each step. Checks E1 (one op.applied per approved step), E2 (undoing every step in
reverse restores each earlier hash) and E4 (the render's streams, size, duration and frame count)."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time

import pytest
from s3_app import App
from test_s4_media import make_video, wait_ready
from test_s6_render import wait_render

from hermes_studio import media as M
from hermes_studio import timeline as T

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="needs ffmpeg")
S = T.TICK_RATE


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(T.new_timeline("p1"), mode="propose")
    yield a
    a.close()


def events(app: App, out: list, stop: threading.Event) -> None:
    import http.client

    c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=120)
    c.request("GET", "/api/projects/p1/events", headers={"Host": f"127.0.0.1:{app.port}", "Authorization": f"Bearer {app.ui}"})
    r = c.getresponse()
    while not stop.is_set():
        line = r.fp.readline().decode()
        if not line:
            return
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))


def step(app: App, tool: str, args: dict) -> dict:
    """The agent calls; Propose parks it; the person applies; the agent reads the outcome."""
    ok, e = app.mcp(tool, {"project_id": "p1", **args})
    assert not ok and e["code"] == "needs_approval", e
    ok, r = app.mcp("approval_resolve", {"project_id": "p1", "pending_id": e["pending_id"], "decision": "apply"}, app.ui)
    assert ok and r["resolved"]["state"] == "applied", r
    ok, st = app.mcp("approval_status", {"project_id": "p1", "pending_id": e["pending_id"]})
    assert ok and st["state"] == "applied"
    return st["result"]


def test_headline_run(app, tmp_path):
    seen: list = []
    stop = threading.Event()
    threading.Thread(target=events, args=(app, seen, stop), daemon=True).start()
    time.sleep(0.3)
    src = make_video(tmp_path / "Videos" / "talk.mp4", seconds=20, size="640x360")
    hashes = [app.head()["hash"]]

    imp = step(app, "import_media", {"path": str(src), "client_op_id": "s1", "stages": ["proxy", "thumbs", "wave"]})
    hashes.append(imp["hash"])
    mid = next(iter(app.proj.log.doc["media"]))
    wait_ready(app, mid)
    # words with fillers (Whisper's output, without downloading a model in CI)
    words = []
    for i in range(30):
        words.append({"w": "um" if i % 6 == 5 else f"w{i}", "in": i * S // 2, "out": i * S // 2 + 3 * S // 10})
    M._write_json(M.cache_paths(app.proj.dir, mid)["words"], {"words": words})

    place = step(
        app,
        "timeline_apply",
        {
            "base_version": app.proj.log.version,
            "client_op_id": "s2",
            "summary": "Place the talk, 15 s",
            "ops": [{"op": "insert_clip", "track": "V1", "media": mid, "src_s": [0, 15], "at_s": 0}],
        },
    )
    hashes.append(place["hash"])
    cut = step(app, "transcript_cut", {"base_version": app.proj.log.version, "client_op_id": "s3", "fillers": True})
    hashes.append(cut["hash"])
    assert len(app.proj.log._entries[-1]["ops"]) >= 10  # 5 fillers, one entry
    title = step(
        app,
        "timeline_apply",
        {
            "base_version": app.proj.log.version,
            "client_op_id": "s4",
            "summary": "Title",
            "ops": [{"op": "add_text", "text": "Hermes", "style": "pop", "at_s": 0, "dur_s": 2}],
        },
    )
    hashes.append(title["hash"])

    # E4: the render
    ok, r = app.mcp("render_timeline", {"project_id": "p1", "captions": False})
    assert ok, r
    st = wait_render(app, r["render_id"])
    assert st["state"] == "ready", st
    end = max(e for _, e in T.resolve(app.proj.log.doc).values())
    p = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,nb_read_frames,duration",
            "-of",
            "json",
            str(app.proj.dir / st["path"]),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    streams = {s["codec_type"]: s for s in json.loads(p.stdout)["streams"]}
    v = streams["video"]
    assert (streams["video"]["codec_name"], streams["audio"]["codec_name"]) == ("h264", "aac")
    assert (v["width"], v["height"]) == (1080, 1920)
    assert abs(float(v["duration"]) - end / S) <= 1 / 30
    assert abs(int(v["nb_read_frames"]) - round(end / S * 30)) <= 1

    # E1: one op.applied per approved step, each after its approval.pending
    time.sleep(0.5)
    applied = [e for e in seen if e["type"] == "op.applied"]
    assert [e["summary"] for e in applied][:4] == [
        "Import talk.mp4",
        "Place the talk, 15 s",
        app.proj.log._entries[2]["summary"],
        "Title",
    ]
    pend = [e for e in seen if e["type"] == "approval.pending"]
    assert len(pend) == 4 and all(seen.index(p) < seen.index(a) for p, a in zip(pend, applied, strict=False))

    # E2: undo each step in reverse; the hash before each step comes back
    for i, op_id in enumerate(reversed([e["op_id"] for e in app.proj.log._entries[:4]])):
        ok, u = app.mcp("history_undo", {"project_id": "p1", "client_op_id": f"undo{i}", "op_id": op_id}, app.ui)
        assert ok, u
        assert app.head()["hash"] == hashes[-2 - i]
    stop.set()
