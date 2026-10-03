"""S4 media services: probe, add_media, import with background proxy/thumbs/wave and progress,
transcript -> timeline mapping (docs/plans/S4-SPEC.md)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from s3_app import App
from test_oplog import S, base

from hermes_studio import mcp_timeline as MT
from hermes_studio import media as M
from hermes_studio import media_jobs as MJ
from hermes_studio import oplog as O
from hermes_studio import timeline as T

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="needs ffmpeg")

HUMAN = O.Session(O.Actor("human", "user"))


def make_video(path: Path, seconds: float = 6, size: str = "320x180", rate: int = 30, audio: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size={size}:rate={rate}:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds}"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac", "-shortest"] if audio else []
    subprocess.run([*cmd, str(path)], check=True)
    return path


def make_audio(path: Path, seconds: float = 3) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=220:duration={seconds}",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def app(home):
    a = App(base())
    yield a
    a.close()


def wait_ready(app: App, mid: str, timeout: float = 120) -> dict:
    end = time.monotonic() + timeout
    while True:
        ok, st = app.mcp("media_status", {"project_id": "p1", "media_id": mid})
        assert ok, st
        if st["state"] not in ("queued", "running"):
            return st
        assert time.monotonic() < end, st
        time.sleep(0.1)


# --------------------------------------------------------------------------- probe


def test_probe_video_and_audio(home):
    v = M.probe(make_video(home / "v.mp4"))
    assert v["fps"] == [30, 1] and (v["width"], v["height"]) == (320, 180) and v["has_video"] and v["has_audio"]
    assert v["video_codec"] == "h264" and v["audio_codec"] == "aac" and v["rotation"] == 0 and not v["vfr"]
    assert abs(v["dur"] - 6 * T.TICK_RATE) < T.TICK_RATE // 10 and isinstance(v["dur"], int)
    a = M.probe(make_audio(home / "a.wav"))
    assert a["fps"] is None and not a["has_video"] and a["has_audio"] and a["dur"] == 3 * T.TICK_RATE


def test_probe_refuses_what_it_cannot_read(home):
    junk = home / "junk.mp4"
    junk.write_bytes(b"not a video")
    with pytest.raises(M.MediaError):
        M.probe(junk)
    with pytest.raises(M.MediaError):
        M.probe(home / "missing.mp4")


def test_seconds_to_ticks_is_exact():
    assert M._seconds_to_ticks("6.000000") == 6 * T.TICK_RATE
    assert M._seconds_to_ticks("0.000001") == 706  # 705.6 rounds half up
    assert M._seconds_to_ticks("N/A") is None and M._seconds_to_ticks("0") is None and M._seconds_to_ticks("-1") is None
    assert M._ratio("30000/1001") == M.Fraction(30000, 1001) and M._ratio("0/0") is None and M._ratio(None) is None


# --------------------------------------------------------------------------- add_media (engine)


def test_add_media_op_undo_redo_and_blocked_while_used():
    log = O.Oplog(base())
    h0 = log.doc["hash"]
    r = log.call(
        HUMAN,
        "timeline_apply",
        {
            "client_op_id": "a",
            "base_version": 0,
            "summary": "import",
            "ops": [{"op": "add_media", "path": "/x/a.mp4", "dur": 10 * S, "fps": [30, 1]}],
        },
    )
    assert log.doc["media"]["m3"] == {"path": "/x/a.mp4", "dur": 10 * S, "fps": [30, 1]} and r["changed_ids"] == ["m3"]
    c = log.call(
        HUMAN,
        "timeline_apply",
        {
            "client_op_id": "b",
            "base_version": 1,
            "summary": "use",
            "ops": [{"op": "insert_clip", "track": "V1", "media": "m3", "src": [0, S], "at": 30 * S}],
        },
    )
    with pytest.raises(O.OplogError) as e:
        log.call(HUMAN, "history_undo", {"client_op_id": "u1", "op_id": r["op_id"]})
    assert e.value.code == "undo_blocked"
    log.call(HUMAN, "history_undo", {"client_op_id": "u2", "op_id": c["op_id"]})
    u = log.call(HUMAN, "history_undo", {"client_op_id": "u3", "op_id": r["op_id"]})
    assert log.doc["hash"] == h0 and "m3" not in log.doc["media"]
    log.call(HUMAN, "history_redo", {"client_op_id": "r1", "op_id": u["op_id"]})
    assert log.doc["media"]["m3"]["path"] == "/x/a.mp4"
    again = O.Oplog.load(base(), _save(log))
    assert again.doc["hash"] == log.doc["hash"]


def _save(log: O.Oplog) -> str:
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as f:
        for e in log._entries:
            f.write(json.dumps(e) + "\n")
    return path


@pytest.mark.parametrize(
    "op, want",
    [
        ({"path": 5, "dur": S, "fps": [30, 1]}, ("wrong_type", "/media/m3/path")),
        ({"path": "a", "dur": -1, "fps": [30, 1]}, ("negative_time", "/media/m3/dur")),
        ({"path": "a", "dur": S, "fps": [0, 1]}, ("out_of_range", "/media/m3/fps")),
        ({"path": "a", "dur": S}, ("missing_arg", "/ops/0/fps")),
        ({"path": "a", "dur": S, "fps": None, "id": "c1"}, ("duplicate_id", "/ops/0/id")),
        ({"path": "a", "dur": S, "fps": None, "id": 5}, ("bad_arg", "/ops/0/id")),
        ({"path": "a", "dur": S, "fps": None, "zz": 1}, ("unknown_arg", "/ops/0/zz")),
    ],
)
def test_add_media_bad_args(op, want):
    log = O.Oplog(base())
    with pytest.raises(O.OplogError) as e:
        log.call(
            HUMAN, "timeline_apply", {"client_op_id": "a", "base_version": 0, "summary": "s", "ops": [{"op": "add_media", **op}]}
        )
    d = e.value.as_dict()
    assert (d.get("rule"), d.get("path")) == want, d
    assert log.version == 0


# --------------------------------------------------------------------------- transcript -> timeline


def test_timeline_words_maps_through_every_clip_that_shows_them():
    doc = T.stamp_hash(base())[0]
    # c1 shows m1 [0, 4s) at 0; c2 shows m1 [10s, 14s) at 4s; c3 shows m1 [20s, 24s) at 10s
    words = {
        "m1": [
            {"w": "a", "in": S // 2, "out": S},  # in c1
            {"w": "b", "in": 11 * S, "out": 12 * S},  # in c2
            {"w": "cut", "in": 5 * S, "out": 6 * S},  # in no clip
            {"w": "edge", "in": 3 * S + S // 2, "out": 5 * S},  # midpoint 4.25s: outside c1
            {"w": "e2", "in": 3 * S, "out": 4 * S + S // 4},  # midpoint 3.625s: in c1, clamped to its end
        ]
    }
    rows = M.timeline_words(doc, words)
    assert [(r["w"], r["clip"], r["at"], r["end"]) for r in rows] == [
        ("a", "c1", S // 2, S),
        ("e2", "c1", 3 * S, 4 * S),
        ("b", "c2", 5 * S, 6 * S),
    ]
    assert M.timeline_words(doc, {}) == []


def test_timeline_words_follow_speed():
    doc = base()
    doc["tracks"][[t["id"] for t in doc["tracks"]].index("V1")]["items"][0]["props"] = {"speed": [2, 1]}
    doc["tracks"][[t["id"] for t in doc["tracks"]].index("V1")]["items"][0]["src"] = [0, 8 * S]
    doc = T.stamp_hash(doc)[0]
    rows = M.timeline_words(doc, {"m1": [{"w": "x", "in": 4 * S, "out": 6 * S}]})
    assert [(r["at"], r["end"]) for r in rows] == [(2 * S, 3 * S)]


# --------------------------------------------------------------------------- import over /mcp


def test_import_media_end_to_end(app, home):
    src = make_video(home / "videos" / "talk.mp4")
    ok, r = app.mcp("import_media", {"project_id": "p1", "path": str(src), "client_op_id": "imp1"})
    assert ok, r
    mid = r["media_id"]
    assert (
        mid == "m3" and r["new_version"] == 1 and r["probe"]["fps"] == [30, 1] and r["status"]["state"] in ("queued", "running")
    )
    assert app.proj.log.doc["media"][mid] == {"path": str(src.resolve()), "dur": r["probe"]["dur"], "fps": [30, 1]}
    line = json.loads((app.proj.dir / "oplog.jsonl").read_text().splitlines()[-1])
    assert line["actor"] == {"kind": "agent", "id": "claude"} and line["ops"][0]["op"] == "add_media"
    st = wait_ready(app, mid)
    assert st["state"] == "ready" and st["progress"] == 1.0 and set(st["stages"]) == {"proxy", "thumbs", "wave"}, st
    assert all(s["state"] == "ready" for s in st["stages"].values())
    paths = M.cache_paths(app.proj.dir, mid)
    proxy = M.probe(paths["proxy"])
    assert proxy["height"] == 180 and proxy["fps"] == [30, 1] and proxy["has_audio"]  # never upscaled to 540
    assert st["stages"]["proxy"]["path"] == f"cache/proxy/{mid}.mp4"
    idx = json.loads(paths["thumbs_index"].read_text())
    assert idx["count"] == 3 and idx["height"] == M.THUMB_HEIGHT and paths["thumbs"].stat().st_size > 0
    wave = json.loads(paths["wave"].read_text())
    assert abs(wave["count"] - 600) <= 5 and all(-128 <= lo <= hi <= 127 for lo, hi in wave["peaks"])
    assert max(hi for _, hi in wave["peaks"]) > 8  # lavfi sine is 1/8 full scale: about 16, not silence
    # the retry returns the same write and starts nothing
    ok, again = app.mcp("import_media", {"project_id": "p1", "path": str(src), "client_op_id": "imp1"})
    assert ok, again
    assert again["op_id"] == r["op_id"] and again["media_id"] == mid and again["status"]["state"] == "ready"
    assert app.proj.log.version == 1
    # usable at once: a clip on the new media
    ok, c = app.mcp_apply({"op": "insert_clip", "track": "V1", "media": mid, "src": [0, 2 * S], "at": 30 * S})
    assert ok, c


def test_import_progress_reaches_sse_clients_without_ids(app, home):
    import http.client

    src = make_video(home / "v.mp4", seconds=4)
    c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=30)
    c.request("GET", "/api/projects/p1/events", headers={"Host": f"127.0.0.1:{app.port}", "Authorization": f"Bearer {app.ui}"})
    resp = c.getresponse()
    assert resp.status == 200
    ok, r = app.mcp("import_media", {"project_id": "p1", "path": str(src)})
    assert ok, r
    events, ids = [], []
    while not events or events[-1]["type"] != "media.ready":
        line = resp.fp.readline().decode()
        if line.startswith("id: "):
            ids.append(int(line[4:]))
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    c.close()
    assert events[0]["type"] == "op.applied" and ids == [1]  # only the log entry carries an id
    prog = [e for e in events if e["type"] == "media.progress"]
    assert prog and all(e["media_id"] == r["media_id"] and e["project_id"] == "p1" for e in prog)
    overall = [e["progress"] for e in prog]
    assert overall == sorted(overall) and overall[-1] == 1.0
    assert {e["stage"] for e in prog} == {"proxy", "thumbs", "wave"}
    assert events[-1]["state"] == "ready" and events[-1]["failed"] == []


def test_import_audio_only_skips_thumbs(app, home):
    ok, r = app.mcp("import_media", {"project_id": "p1", "path": str(make_audio(home / "a.wav"))})
    assert ok, r
    st = wait_ready(app, r["media_id"])
    assert st["state"] == "ready" and set(st["stages"]) == {"proxy", "wave"}
    assert app.proj.log.doc["media"][r["media_id"]]["fps"] is None


@pytest.mark.parametrize(
    "args, want",
    [
        ({"path": "/etc/passwd"}, ("invalid_op", "bad_arg", "/path")),
        ({"path": "https://example.com/v.mp4"}, ("invalid_op", "bad_arg", "/path")),
        ({"path": 5}, ("invalid_op", "bad_arg", "/path")),
        ({}, ("invalid_op", "bad_arg", "/path")),
        ({"path": "~/nope.mp4"}, ("not_found", "not_found", "/path")),
        ({"path": "~/v.mp4", "stages": ["proxy", "nope"]}, ("invalid_op", "bad_arg", "/stages/1")),
        ({"path": "~/v.mp4", "stages": "proxy"}, ("invalid_op", "bad_arg", "/stages")),
        ({"path": "~/v.mp4", "whisper": "huge"}, ("invalid_op", "bad_arg", "/whisper")),
        ({"path": "~/v.mp4", "zz": 1}, ("invalid_op", "unknown_arg", "/zz")),
    ],
)
def test_import_media_refusals_change_nothing(app, home, args, want):
    make_video(home / "v.mp4", seconds=1)
    h0 = app.head()
    ok, e = app.mcp("import_media", {"project_id": "p1", **args})
    assert not ok and (e["code"], e["rule"], e["path"]) == want, e
    assert app.head() == h0


def test_media_tools_project_checks_and_scopes(app, home):
    for name in ("import_media", "media_status", "get_transcript"):
        ok, e = app.mcp(name, {})
        assert not ok and (e["rule"], e["path"]) == ("missing_arg", "/project_id")
        extra = {"path": "x"} if name == "import_media" else {"media_id": "m1"}
        ok, e = app.mcp(name, {"project_id": "nope", **extra})
        assert not ok and e["code"] == "not_found" and e["id"] == "nope"
        ok, e = app.mcp(name, {"project_id": 5})
        assert not ok and (e["rule"], e["path"]) == ("bad_arg", "/project_id")
    ro = app.eng.tokens.mint("mcp:ro", scopes={"read"})
    ok, e = app.mcp("import_media", {"project_id": "p1", "path": "~/v.mp4"}, token=ro)
    assert not ok and e["code"] == "permission_denied"
    ok, e = app.mcp("media_status", {"project_id": "p1", "media_id": "zz"})
    assert not ok and e["code"] == "not_found" and e["id"] == "zz"
    ok, st = app.mcp("media_status", {"project_id": "p1", "media_id": "m1"})  # in the base doc, never imported
    assert ok and st["state"] == "none"
    ok, e = app.mcp("media_status", {"project_id": "p1", "media_id": "m1", "zz": 1})
    assert not ok and e["rule"] == "unknown_arg"


def test_get_transcript_reads_words_files(app):
    words = M.cache_paths(app.proj.dir, "m1")["words"]
    M._write_json(words, {"words": [{"w": "hi", "in": S // 2, "out": S}, {"w": "gone", "in": 5 * S, "out": 6 * S}]})
    ok, t = app.mcp("get_transcript", {"project_id": "p1"})
    assert (
        ok
        and t["media"] == ["m1"]
        and [(w["w"], w["clip"], w["at_s"], w["end_s"]) for w in t["words"]] == [("hi", "c1", 0.5, 1.0)]
    )
    assert t["version"] == app.head()["version"]
    ok, t = app.mcp("get_transcript", {"project_id": "p1", "media_id": "m2"})
    assert ok and t["words"] == [] and t["media"] == []


def test_closed_app_media_reads_and_offline_import(home):
    from hermes_studio import project as P

    P.create_project(base())
    backend = MT.ClosedBackend()
    r = MT.call("import_media", {"project_id": "p1", "path": "~/v.mp4"}, backend)
    assert r["isError"] and json.loads(r["content"][-1]["text"])["code"] == "engine_offline"
    r = MT.call("media_status", {"project_id": "p1", "media_id": "m1"}, backend)
    assert not r["isError"] and r["structuredContent"]["state"] == "none"
    d = P.project_dir("p1")
    M._write_json(M.cache_paths(d, "m1")["status"], {"media_id": "m1", "state": "running", "progress": 0.3, "stages": {}})
    r = MT.call("media_status", {"project_id": "p1", "media_id": "m1"}, backend)
    assert r["structuredContent"]["state"] == "interrupted"  # no worker owns it with the app closed


def test_tools_list_names():
    assert len(MT.TOOLS) == 32 and {"import_media", "media_status", "get_transcript"} <= set(MT.BY_NAME)


def test_status_reads_interrupted_when_no_worker_owns_it(home):
    d = home / "proj"
    M._write_json(M.cache_paths(d, "m9")["status"], {"media_id": "m9", "state": "queued", "stages": {}})
    assert MJ.read_status(d, "m9", set())["state"] == "interrupted"
    assert MJ.read_status(d, "m9", {"m9"})["state"] == "queued"
    assert MJ.read_status(d, "m8", set()) is None


# --------------------------------------------------------------------------- the S4 gate: a 20-minute import


@pytest.mark.skipif(os.environ.get("HERMES_SLOW_TESTS") != "1", reason="the 20-minute import gate; set HERMES_SLOW_TESTS=1")
def test_gate_twenty_minute_fixture_imports_with_progress(app, home):
    src = make_video(home / "long.mp4", seconds=20 * 60, size="640x360", rate=30)
    t0 = time.monotonic()
    ok, r = app.mcp("import_media", {"project_id": "p1", "path": str(src)})
    assert ok, r
    seen = []
    while True:
        ok, st = app.mcp("media_status", {"project_id": "p1", "media_id": r["media_id"]})
        seen.append(st["progress"])
        if st["state"] not in ("queued", "running"):
            break
        time.sleep(0.5)
    assert st["state"] == "ready", st
    assert seen == sorted(seen) and len(set(seen)) > 5  # progress moved, and only forward
    idx = json.loads(M.cache_paths(app.proj.dir, r["media_id"])["thumbs_index"].read_text())
    assert idx["count"] == 600
    print(f"20-min import: {time.monotonic() - t0:.1f}s")


# --------------------------------------------------------------------------- REST (the Edit page)


def test_rest_import_status_files_and_transcript(app, home):
    src = make_video(home / "v.mp4", seconds=2)
    st, _, r = app.req("POST", "/api/projects/p1/import_media", {"path": str(src), "actor": {"kind": "human", "id": "x"}}, app.ui)
    assert st == 200 and r["media_id"] == "m3", r
    assert app.proj.log._entries[-1]["actor"] == {"kind": "human", "id": "user"}  # the token's actor, never the body's
    wait_ready(app, "m3")
    st, _, s = app.req("GET", "/api/projects/p1/media/m3", token=app.ui)
    assert st == 200 and s["state"] == "ready"
    for name, ctype in (
        ("proxy", "video/mp4"),
        ("thumbs", "image/jpeg"),
        ("thumbs.json", "application/json"),
        ("wave", "application/json"),
    ):
        c = __import__("http.client").client.HTTPConnection("127.0.0.1", app.port, timeout=20)
        c.request(
            "GET",
            f"/api/projects/p1/media/m3/{name}",
            headers={"Host": f"127.0.0.1:{app.port}", "Authorization": f"Bearer {app.ui}"},
        )
        resp = c.getresponse()
        body = resp.read()
        c.close()
        assert resp.status == 200 and resp.getheader("Content-Type").startswith(ctype) and body, name
    st, _, e = app.req("GET", "/api/projects/p1/media/m3/words", token=app.ui)
    assert st == 404  # not asked for
    st, _, e = app.req("GET", "/api/projects/p1/media/zz/proxy", token=app.ui)
    assert st == 404 and e["code"] == "not_found" and e["id"] == "zz"
    st, _, e = app.req("GET", "/api/projects/p1/media/m3/..%2F..%2Fbase.json", token=app.ui)
    assert st == 404
    st, _, t = app.req("GET", "/api/projects/p1/transcript", token=app.ui)
    assert st == 200 and t["words"] == []
    st, _, _ = app.req("GET", "/api/projects/p1/media/m3", token=None)
    assert st == 401
