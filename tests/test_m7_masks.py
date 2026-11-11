"""M7: feathered masks isolating grade or blur; preview = export."""

from __future__ import annotations

import copy
import json
import statistics
import subprocess
from pathlib import Path

import pytest

from hermes_studio import editor as E
from hermes_studio import mask as M
from hermes_studio import timeline as T

S = T.TICK_RATE


def _cut(pid: str, colour: str = "0x808080", size=(320, 180)):
    folder = E._dir(pid)
    (folder / "media").mkdir(parents=True, exist_ok=True)
    w, h = size
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={colour}:s={w}x{h}:d=2:r=30",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-qp", "0", str(folder / "media" / "v.mp4")],
        check=True, capture_output=True,
    )
    d = T.new_timeline(pid, size=size)
    by = {t["id"]: t for t in d["tracks"]}
    d["media"] = {"m1": {"path": "media/v.mp4", "dur": 2 * S, "fps": [30, 1]}}
    by["V1"]["items"] = [{"id": "c1", "type": "clip", "media": "m1", "src": [0, 2 * S], "at": 0, "fade_in": 0, "fade_out": 0}]
    d, _ = T.stamp_hash(d)
    (folder / "base.json").write_text(json.dumps(d))
    from hermes_studio import oplog as O

    E._save_current(folder, O.Oplog(d, path=folder / "oplog.jsonl").doc)
    return pid


def test_set_mask_and_clear_undo(home):
    pid = _cut("msk1")
    E.set_mask(pid, "c1", w=0.5, h=1.0, feather=0.06)
    row = next(i for t in E.view(E._log(E._dir(pid)).doc)["tracks"] for i in t["items"] if i["id"] == "c1")
    assert row["mask"]["w"] == pytest.approx(0.5) and row["mask"]["feather"] == pytest.approx(0.06)
    E.clear_mask(pid, "c1")
    assert "mask" not in next(i for t in E.view(E._log(E._dir(pid)).doc)["tracks"] for i in t["items"] if i["id"] == "c1")
    E.undo(pid)
    assert next(i for t in E.view(E._log(E._dir(pid)).doc)["tracks"] for i in t["items"] if i["id"] == "c1")["mask"]["w"] == pytest.approx(0.5)


def test_unset_mask_does_not_change_the_hash():
    from tests.test_timeline import _golden

    d = _golden()
    h = T.stamp_hash(d)[1]
    unset = copy.deepcopy(d)
    unset["tracks"][1]["items"][0].setdefault("props", {})["mask"] = None
    assert T.stamp_hash(unset)[1] == h


def _read_rgb(path: Path, x: int, y: int) -> tuple[int, int, int]:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "1", "-i", str(path), "-map", "0:v:0",
         "-vf", f"format=rgb24,crop=w=1:h=1:x={x}:y={y}", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True,
    ).stdout
    return raw[0], raw[1], raw[2]


def _expected_masked_gray(mx: float, my: float, w: float, h: float, feather: float, lx: float, ly: float) -> float:
    from hermes_studio import grade as G

    base = 128 / 255.0
    gp = G.preview(G.parse(G.store(lift=[0.25, 0.25, 0.25])))
    graded = gp["tables"][0][128]
    m = M.matte_at("rect", mx, my, w, h, feather, False, 320, 180, lx, ly)
    return (base * (1 - m) + graded * m) * 255


def test_masked_grade_render_matches_formula(home):
    from hermes_studio import render_timeline as R

    pid = _cut("mskrend", size=(320, 180))
    E.set_grade(pid, "c1", lift=[0.25, 0.25, 0.25])
    E.set_mask(pid, "c1", w=0.5, h=1.0, feather=0.08)
    res = R.render_project(pid)
    out = Path(res.get("path") or res.get("file"))
    pts = [(40, 90, 0.25), (280, 90, 0.75), (160, 90, 0.5), (150, 90, 0.48), (170, 90, 0.52)]
    deltas = []
    for x, y, lx in pts:
        got = _read_rgb(out, x, y)[0]
        want = _expected_masked_gray(0, 0, 0.5, 1.0, 0.08, lx, 0.5)
        deltas.append(abs(got - want))
    med = statistics.median(deltas)
    # yuv420 H.264 export shifts edge blends a few code values; interior samples stay at Δ≤2.
    assert med <= 3, (med, deltas)
    assert max(deltas) <= 4, (med, deltas)


def test_desk_mask_op(desk, home):
    pid = _cut("mskdesk")
    import http.client

    body = json.dumps({"op": "mask", "id": "c1", "w": 0.5, "h": 1, "feather": 0.05})
    c = http.client.HTTPConnection("127.0.0.1", desk, timeout=10)
    c.request("POST", f"/api/editor/{pid}", body=body, headers={"Host": f"127.0.0.1:{desk}", "Content-Type": "application/json"})
    res = json.loads(c.getresponse().read().decode())
    assert res.get("ok") is True
    clip = next(i for t in res["project"]["tracks"] for i in t["items"] if i["id"] == "c1")
    assert clip["mask"]["feather"] == pytest.approx(0.05)
