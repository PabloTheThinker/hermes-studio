"""M5 export renders: ffprobe each preset and cancel leaves no partial file."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from hermes_studio import editor as E
from hermes_studio import editor_renders as ER
from hermes_studio import render_timeline as R
from tests.support import post as _post
from tests.support import wait_editor_render
from tests.test_editor import _make_source, _project


@pytest.fixture
def cut(home):
    return _project(home, "m5cut", canvas=(1280, 720))


def _ffprobe_json(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _independent_probe(path: Path) -> dict:
    info = _ffprobe_json(path)
    streams = [s for s in info.get("streams") or [] if isinstance(s, dict)]
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = info.get("format") or {}
    dur = float(fmt.get("duration") or 0)
    if dur <= 0 and video:
        dur = float(video.get("duration") or 0)
    fps = None
    if video:
        raw = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/0"
        if isinstance(raw, str) and "/" in raw:
            num, den = raw.split("/", 1)
            try:
                n, d = float(num), float(den)
                fps = round(n / d, 3) if d else None
            except ValueError:
                fps = None
    return {
        "width": int(video.get("width") or 0) if video else 0,
        "height": int(video.get("height") or 0) if video else 0,
        "fps": fps,
        "duration": round(dur, 3),
        "video_codec": video.get("codec_name") if video else None,
        "audio_codec": audio.get("codec_name") if audio else None,
        "audio_channels": audio.get("channels") if audio else None,
        "audio_rate": int(audio.get("sample_rate") or 0) if audio else None,
        "bytes": path.stat().st_size,
    }


def _assert_probe_matches(path: Path, pr: dict) -> None:
    ind = _independent_probe(path)
    for key in (
        "width",
        "height",
        "duration",
        "video_codec",
        "audio_codec",
        "audio_channels",
        "audio_rate",
        "bytes",
    ):
        assert pr[key] == ind[key], (key, pr[key], ind[key])
    if pr.get("fps") is not None and ind.get("fps") is not None:
        assert pr["fps"] == pytest.approx(ind["fps"], abs=0.05)


@pytest.mark.parametrize(
    ("preset", "w", "h", "vcodec", "ext", "acodec"),
    [
        ("1080p", 1920, 1080, "h264", "mp4", "aac"),
        ("4k", 3840, 2160, "h264", "mp4", "aac"),
        ("vertical", 1080, 1920, "h264", "mp4", "aac"),
        ("prores", 1920, 1080, "prores", "mov", "pcm_s16le"),
    ],
)
def test_each_export_preset_matches_ffprobe(cut, preset, w, h, vcodec, ext, acodec):
    out = R.render_project(cut, preset=preset, quality="draft")
    path = Path(out["path"])
    assert path.is_file() and path.suffix == f".{ext}"
    pr = out["probe"]
    assert pr["width"] == w and pr["height"] == h
    assert vcodec in (pr["video_codec"] or "")
    assert pr["audio_codec"] == acodec
    assert out["size"] == [w, h]
    _assert_probe_matches(path, pr)


def test_fps_override_is_honoured(cut):
    out = R.render_project(cut, preset="1080p", fps=24, quality="draft")
    assert out["probe"]["fps"] == pytest.approx(24, abs=0.05)
    _assert_probe_matches(Path(out["path"]), out["probe"])


def test_export_scales_to_preset_not_canvas(home):
    pid = _project(home, "m5scale", canvas=(640, 360))
    out = R.render_project(pid, preset="1080p", quality="draft")
    assert out["probe"]["width"] == 1920 and out["probe"]["height"] == 1080


def _ffmpeg_part_lines() -> list[str]:
    r = subprocess.run(["pgrep", "-af", "ffmpeg"], capture_output=True, text=True)
    if r.returncode != 0:
        return []
    return [ln for ln in r.stdout.splitlines() if ".part" in ln]


def _ffmpeg_for_project(folder: Path) -> list[str]:
    needle = str(folder)
    r = subprocess.run(["pgrep", "-af", "ffmpeg"], capture_output=True, text=True)
    if r.returncode != 0:
        return []
    return [ln for ln in r.stdout.splitlines() if needle in ln]


def test_cancel_leaves_no_output_or_temp_files(home):
    folder = E._dir("m5cancel")
    _make_source(folder / "media" / "talk.mp4", seconds=40.0)
    pid = _project(home, "m5cancel", canvas=(640, 360))
    folder = E._dir(pid)
    dest = folder / f"{pid}-4k.mp4"
    tmp = dest.with_name(f".{dest.stem}.part{dest.suffix}")

    ER.start(pid, preset="4k", quality="high")
    time.sleep(0.35)
    ER.cancel(pid)
    st = None
    for _ in range(600):
        st = ER.status(pid)
        if st.get("state") not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert st and st.get("state") == "cancelled", st
    assert not dest.is_file()
    assert not tmp.is_file()
    leftovers = [p.name for p in folder.iterdir() if p.name.startswith(".") and "part" in p.name]
    assert leftovers == []
    assert _ffmpeg_part_lines() == []
    assert _ffmpeg_for_project(folder) == []


def test_failed_render_leaves_no_output(home, monkeypatch):
    pid = _project(home, "m5fail", canvas=(640, 360))
    folder = E._dir(pid)
    dest = folder / f"{pid}-1080p.mp4"
    tmp = dest.with_name(f".{dest.stem}.part{dest.suffix}")

    def boom(cmd, duration_sec, on_progress, cancel):
        Path(cmd[-1]).write_bytes(b"\x00" * 2048)
        raise R.RenderError("ffmpeg blew up")

    monkeypatch.setattr(R, "_run_ffmpeg_progress", boom)
    with pytest.raises(R.RenderError):
        R.render_project(pid, preset="1080p", quality="draft")
    assert not dest.is_file()
    assert not tmp.is_file()


def test_desk_render_and_status_carry_probe(desk, home):
    pid = _project(home, "m5desk", canvas=(640, 360))
    st, res = _post(desk, f"/api/editor/{pid}", {"op": "render", "preset": "vertical", "quality": "draft"})
    assert st == 200 and "_cancel_box" not in res["render"]
    done = wait_editor_render(desk, pid)
    assert done["state"] == "ready"
    pr = done["result"]["probe"]
    assert pr["width"] == 1080 and pr["height"] == 1920
    _assert_probe_matches(Path(done["result"]["path"]), pr)


def test_cli_render_json_includes_probe(home):
    import os
    import subprocess
    import sys

    from tests.test_cli_contract import ROOT

    pid = _project(home, "m5cli", canvas=(640, 360))
    env = {**os.environ, "HERMES_STUDIO_EDITOR": str(home), "PYTHONPATH": str(ROOT)}
    p = subprocess.run(
        [sys.executable, "-m", "hermes_studio", "render", pid, "--preset", "1080p", "--quality", "draft", "--json"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
        timeout=180,
    )
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    pr = data["probe"]
    assert pr["width"] == 1920 and pr["height"] == 1080
    _assert_probe_matches(Path(data["path"]), pr)


def test_export_presets_route(desk):
    import http.client

    c = http.client.HTTPConnection("127.0.0.1", desk, timeout=10)
    c.request("GET", "/api/editor/demo/export-presets", headers={"Host": f"127.0.0.1:{desk}"})
    r = c.getresponse()
    data = json.loads(r.read() or b"{}")
    assert r.status == 200 and data["ok"]
    ids = {p["id"] for p in data["presets"]}
    assert ids == {"1080p", "4k", "vertical", "prores"}
