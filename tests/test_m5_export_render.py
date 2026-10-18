"""M5 export renders: ffprobe each preset and cancel leaves no partial file."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from hermes_studio import editor as E
from hermes_studio import editor_renders as ER
from hermes_studio import render_timeline as R
from hermes_studio import timeline as T
from tests.test_editor import _make_source, _project


@pytest.fixture
def cut(home):
    return _project(home, "m5cut", canvas=(1280, 720))


def _ffprobe_line(path: Path) -> str:
    p = R.probe_export(path)
    return (
        f"{path.name}: {p['width']}x{p['height']} {p['fps']}fps "
        f"{p['duration']}s v={p['video_codec']} a={p['audio_codec']} ch={p['audio_channels']} rate={p['audio_rate']}"
    )


@pytest.mark.parametrize(
    ("preset", "w", "h", "vcodec"),
    [
        ("1080p", 1920, 1080, "h264"),
        ("4k", 3840, 2160, "h264"),
        ("vertical", 1080, 1920, "h264"),
        ("prores", 1920, 1080, "prores"),
    ],
)
def test_each_export_preset_matches_ffprobe(cut, preset, w, h, vcodec):
    out = R.render_project(cut, preset=preset, quality="draft")
    path = Path(out["path"])
    assert path.is_file()
    pr = out["probe"]
    assert pr["width"] == w and pr["height"] == h
    assert pr["audio_codec"] is not None
    assert vcodec in (pr["video_codec"] or "")
    assert out["size"] == [w, h]
    print(_ffprobe_line(path))


def test_fps_override_is_honoured(cut):
    out = R.render_project(cut, preset="1080p", fps=24, quality="draft")
    assert out["probe"]["fps"] == pytest.approx(24, abs=0.05)


def test_cancel_leaves_no_output_or_temp_files(home):
    folder = E._dir("m5cancel")
    _make_source(folder / "media" / "talk.mp4", seconds=25.0)
    pid = _project(home, "m5cancel", canvas=(640, 360))
    folder = E._dir(pid)
    dest = folder / f"{pid}-4k.mp4"
    tmp = dest.with_name(f".{dest.stem}.part{dest.suffix}")

    ER.start(pid, preset="4k", quality="high")
    time.sleep(0.2)
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
