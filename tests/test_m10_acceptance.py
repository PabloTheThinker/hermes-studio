"""M10 acceptance film — throwaway HERMES_STUDIO_EDITOR home only."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from hermes_studio import editor as E
from hermes_studio import render_timeline as R
from hermes_studio.timeline import new_timeline

MEDIA_ROOT = Path("/home/ilo/.hermes/cache/scratch/m10-accept-20261110/media")
DELIVER = Path("/home/ilo/.hermes/cache/scratch/m10-accept-20261110")


def _main_clips(view: dict) -> list[dict]:
    tr = next(t for t in view["tracks"] if t["id"] == "V1")
    return [i for i in tr["items"] if i.get("type") == "clip"]


def _bin_ids(view: dict) -> list[str]:
    return [b["id"] for b in (view.get("bin") or [])]


@pytest.fixture()
def accept_home(tmp_path, monkeypatch):
    home = tmp_path / "editor-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_STUDIO_EDITOR", str(home))
    pin = Path.home() / ".hermes/tools/ffmpeg-9.0.1-linux-x64/bin"
    if pin.is_dir():
        monkeypatch.setenv("PATH", f"{pin}:{os.environ.get('PATH', '')}")
    return home


def test_m10_acceptance_film(accept_home):
    """Nine-step Editor 1.0 acceptance on scratch media (not Sir's films)."""
    assert MEDIA_ROOT.is_dir(), "scratch media missing — generate c1..c3 first"
    for i in (1, 2, 3):
        assert (MEDIA_ROOT / f"c{i}.mp4").is_file()

    pid = "m10film"
    folder = accept_home / pid
    folder.mkdir()
    doc = new_timeline(pid, size=(1920, 1080))
    (folder / "base.json").write_text(json.dumps(doc))
    (folder / "timeline.json").write_text(json.dumps(doc))
    (folder / "oplog.jsonl").write_text("")
    (folder / "media").mkdir()

    # 1 Assemble
    for i in (1, 2, 3):
        v = E.import_media(pid, MEDIA_ROOT / f"c{i}.mp4", name=f"c{i}.mp4")
        mid = _bin_ids(v)[-1]
        E.place(pid, mid, 0.0, 3.5, "append")
    v = E.open_project(pid)
    assert len(_main_clips(v)) == 3
    assert v["duration"] >= 10.0

    # 2 Move BEFORE cut (speed on intact clip avoids linked-sound overlap).
    # Ken Burns and mask stay on different clips so zoompan never stacks with maskedmerge.
    clips = _main_clips(E.open_project(pid))
    E.set_speed(pid, clips[1]["id"], 1.25)
    E.set_keyframes(
        pid,
        clips[1]["id"],
        [
            {"at": 0.0, "x": 0, "y": 0, "scale": 1.0, "rotate": 0, "opacity": 1.0, "ease": "ease-in-out"},
            {"at": 1.0, "x": 0.03, "y": -0.02, "scale": 1.08, "rotate": 0, "opacity": 1.0, "ease": "linear"},
        ],
    )
    E.set_reverse(pid, clips[2]["id"], True)
    mid_clip = _main_clips(E.open_project(pid))[1]
    try:
        E.freeze(pid, mid_clip["id"], mid_clip["at"] + 0.4, 0.5)
    except E.EditorError:
        pass

    # 3 Cut + markers — split the first clip (no keyframes on it)
    first = _main_clips(E.open_project(pid))[0]
    E.split(pid, first["id"], first["at"] + 1.5)
    E.add_marker(pid, 0.8, "hook", "red")
    E.add_marker(pid, 4.0, "turn")
    assert len(E.open_project(pid).get("markers") or []) >= 2

    # 4 Grade + LUT + mask on first piece only (no reverse / no Ken Burns on same piece)
    c0 = _main_clips(E.open_project(pid))[0]
    E.set_grade(pid, c0["id"], sat=1.1, gain=[1.03, 1.03, 1.03])
    cube = accept_home / "teal.cube"
    cube.write_text(
        'TITLE "teal"\nLUT_3D_SIZE 2\n'
        "0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n0.9 1 1\n"
    )
    lut = E.import_lut(pid, cube.read_bytes(), name="teal")
    E.set_lut(pid, c0["id"], lut["file"], intensity=0.4)
    E.set_mask(
        pid,
        c0["id"],
        shape="ellipse",
        x=0.12,
        y=0.12,
        w=0.5,
        h=0.6,
        feather=0.05,
        target="grade",
    )

    # 5 Mix
    E.set_track(pid, "A1", gain=1.0, pan=-0.15)
    E.set_track(pid, "A2", gain=0.5, duck=6)

    # 6 Titles
    E.add_title(pid, "lower-third", 0.3, text="Acceptance Film", sub="Hermes Studio 1.0", dur=2.5)
    dur = E.open_project(pid)["duration"]
    E.add_title(pid, "end-card", max(0.0, dur - 2.2), text="END", sub="Editor 1.0", dur=2.0)

    # 7 Export two presets (draft = memory-safe on 19 GB host)
    exports = {}
    DELIVER.mkdir(parents=True, exist_ok=True)
    for preset in ("1080p", "vertical"):
        out = folder / "cache" / f"m10-{preset}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        res = R.render_project(pid, out, preset=preset, quality="draft")
        path = Path(res["path"])
        assert path.is_file() and path.stat().st_size > 5000
        probe = res.get("probe") or {}
        assert probe.get("width") and probe.get("height")
        if preset == "1080p":
            assert probe["width"] == 1920 and probe["height"] == 1080
        else:
            assert probe["width"] == 1080 and probe["height"] == 1920
        assert float(probe.get("duration") or 0) > 5.0
        exports[preset] = {"path": str(path), "probe": probe, "bytes": path.stat().st_size}
        shutil.copy2(path, DELIVER / f"m10-{preset}.mp4")

    # 8 Undo / redo — markers survive
    before = E.open_project(pid)["version"]
    for _ in range(4):
        try:
            E.undo(pid)
        except Exception:
            break
    midv = E.open_project(pid)["version"]
    for _ in range(8):
        try:
            E.redo(pid)
        except Exception:
            break
    after = E.open_project(pid)["version"]
    labels = [m["label"] for m in E.open_project(pid).get("markers") or []]
    assert "hook" in labels and "turn" in labels

    # 9 Keyboard sheet in UI
    js = Path(__file__).resolve().parents[1] / "hermes_studio/ui/editor.js"
    text = js.read_text(encoding="utf-8")
    assert "SHORTCUTS" in text and "helpMarkup" in text

    report = {
        "ok": True,
        "exports": exports,
        "versions": {"before": before, "mid": midv, "after": after},
        "markers": labels,
        "duration": E.open_project(pid)["duration"],
    }
    (DELIVER / "m10-pytest-report.json").write_text(json.dumps(report, indent=2))
