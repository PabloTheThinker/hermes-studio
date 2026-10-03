"""Editor polish: `hermes-studio cache`, and the engine half of the card-latency threshold
(PLAN-MERGED measurements: engine op -> sidebar card, p95 < 250 ms)."""

from __future__ import annotations

import json
import threading
import time

import pytest
from s3_app import App
from test_oplog import S, base

from hermes_studio import api
from hermes_studio import media as M
from hermes_studio.cli import main


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(base())
    yield a
    a.close()


def test_event_latency_p95_under_250_ms(app):
    """From sending a write over HTTP /mcp to its op.applied reaching an SSE client."""
    import http.client

    got: dict[int, float] = {}
    c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=30)
    c.request("GET", "/api/projects/p1/events", headers={"Host": f"127.0.0.1:{app.port}", "Authorization": f"Bearer {app.ui}"})
    r = c.getresponse()

    def read() -> None:
        while True:
            line = r.fp.readline().decode()
            if not line:
                return
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                got[ev["seq"]] = time.perf_counter()

    threading.Thread(target=read, daemon=True).start()
    time.sleep(0.2)
    sent: dict[int, float] = {}
    for i in range(200):
        t0 = time.perf_counter()
        ok, res = app.mcp_apply({"op": "add_marker", "at": i * S // 10, "label": f"m{i}"})
        assert ok, res
        sent[res["seq"]] = t0
    end = time.monotonic() + 10
    while len(got) < 200 and time.monotonic() < end:
        time.sleep(0.05)
    c.close()
    lat = sorted((got[s] - t) * 1000 for s, t in sent.items())
    p95 = lat[int(len(lat) * 0.95) - 1]
    print(f"engine op -> SSE event: p50 {lat[len(lat) // 2]:.1f} ms, p95 {p95:.1f} ms")
    assert len(lat) == 200 and p95 < 250


def test_cache_sizes_and_clear(app, capsys):
    d = app.proj.dir
    for kind, name, size in (
        ("frames", "a.jpg", 1000),
        ("work", "x/y.wav", 500),
        ("proxy", "m1.mp4", 4000),
        ("wave", "m1.json", 300),
    ):
        f = d / "cache" / kind / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x" * size)
    M._write_json(M.cache_paths(d, "m1")["words"], {"words": []})
    res = api.cache()
    row = res["projects"][0]
    assert row["bytes"]["frames"] == 1000 and row["bytes"]["proxy"] == 4000 and res["freed"] == 0
    res = api.cache(clear=True)
    assert res["freed"] == 1500 and res["cleared"] == ["frames", "work"]
    assert not (d / "cache" / "frames").exists() and (d / "cache" / "proxy" / "m1.mp4").exists()
    assert main(["cache", "--clear", "--all", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["freed"] == 4300 and not (d / "cache" / "proxy").exists()
    assert M.cache_paths(d, "m1")["words"].exists()  # Whisper words are never cleared
    assert (d / "oplog.jsonl").exists() and (d / "base.json").exists()
    assert main(["cache", "--all", "--json"]) == 2  # --all needs --clear


def test_caption_preview_styles_match_the_render():
    from hermes_studio import captions as C

    p = C.preview_styles()
    assert set(p["styles"]) == set(C.STYLES) and p["gap_s"] == C.GROUP_GAP_S and p["play_y"] == 1920
    pop = p["styles"]["pop"]
    assert pop == {
        "words_per_line": 3,
        "uppercase": False,
        "primary": "#ffffff",
        "highlight": "#ffe500",
        "outline": "#000000",
        "outline_w": 3,
        "size": 48,
        "margin_v": 88,
    }
    assert p["styles"]["impact"]["uppercase"] and p["styles"]["boxed"]["outline"] == "#2020e0"
