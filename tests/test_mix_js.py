"""The preview mixer (ui/mix.js), run under Node against a recording fake of Web Audio.

The browser checks prove it plays; these prove it schedules what the render renders: the same
source offsets, the same fades, the same role weights, the same mute/solo/gain rules.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from hermes_studio import render_timeline as R

MIX_JS = Path(__file__).resolve().parent.parent / "hermes_studio" / "ui" / "mix.js"

HARNESS = r"""
const fs = require("fs"), vm = require("vm");
class Param {
  constructor(v) { this.value = v; this.events = []; }
  setValueAtTime(v, t) { this.events.push(["set", +v.toFixed(4), +t.toFixed(4)]); return this; }
  linearRampToValueAtTime(v, t) { this.events.push(["ramp", +v.toFixed(4), +t.toFixed(4)]); return this; }
  exponentialRampToValueAtTime(v, t) { this.events.push(["exp", +v.toFixed(4), +t.toFixed(4)]); return this; }
  setTargetAtTime(v, t) { this.events.push(["target", +v.toFixed(4)]); this.value = v; return this; }
}
class Node { constructor() { this.out = []; } connect(n) { this.out.push(n); return n; } disconnect() {} }
class Gain extends Node { constructor() { super(); this.gain = new Param(1); } }
class Src extends Node { constructor() { super(); this.started = null; this.playbackRate = new Param(1); } start(w, o, d) { this.started = [+w.toFixed(4), +o.toFixed(4), +d.toFixed(4)]; } stop() {} }
class Analyser extends Node { constructor() { super(); this.fftSize = 8; } getFloatTimeDomainData(a) { a.fill(0); } }
class Comp extends Node { constructor() { super(); for (const k of ["threshold", "knee", "ratio", "attack", "release"]) this[k] = new Param(0); } }
class AC {
  constructor() { this.currentTime = 10; this.state = "running"; this.destination = new Node(); this.sources = []; AC.last = this; }
  createGain() { return new Gain(); }
  createBufferSource() { const s = new Src(); this.sources.push(s); return s; }
  createAnalyser() { return new Analyser(); }
  createDynamicsCompressor() { return new Comp(); }
  resume() {}
  decodeAudioData() { return Promise.resolve({ duration: 30 }); }
}
global.window = { AudioContext: AC };
global.fetch = async () => ({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) });
vm.runInThisContext(fs.readFileSync(process.argv[2], "utf8"));

const doc = JSON.parse(process.argv[3]);
const play = Number(process.argv[4]);
const speed = Number(process.argv[5] || 1);
(async () => {
  const m = window.HSMix.create();
  await m.load(doc, "p");
  const ready = m.ready(doc);
  m.start(doc, play, speed);
  const ctx = AC.last;
  const clips = ctx.sources.map((s) => {
    // source -> fade gain -> [envelope gain] -> track strip (whose output is the meter)
    const clipGain = s.out[0];
    let node = clipGain.out[0], envelope = null;
    if (!(node.out[0] instanceof Analyser)) { envelope = node.gain.events; node = node.out[0]; }
    return { start: s.started, rate: +s.playbackRate.value.toFixed(4), rates: s.playbackRate.events, env: clipGain.gain.events, envelope, strip: node.gain.events };
  });
  const now0 = m.now();
  ctx.currentTime += 1.5;
  console.log(JSON.stringify({ ready, MIX: window.HSMix.MIX, clips, now0, now15: +m.now().toFixed(4) }));
})();
"""


def _run(tmp_path, doc: dict, play: float, speed: float = 1) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    h = tmp_path / "harness.js"
    h.write_text(HARNESS)
    r = subprocess.run([node, str(h), str(MIX_JS), json.dumps(doc), str(play), str(speed)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _clip(cid, at, src_in, src_out, **kw):
    return {"id": cid, "type": "clip", "file": f"{cid}.mp4", "at": at, "dur": src_out - src_in,
            "src_in": src_in, "src_out": src_out, "volume": kw.get("volume"),
            "fade_in": kw.get("fade_in", 0), "fade_out": kw.get("fade_out", 0), "media_dur": 30,
            "gain_keys": kw.get("gain_keys")}


def _doc(*, a1=None, a2=None, voice=None, music=None):
    return {"tracks": [
        {"id": "V1", "role": "main", "items": []},
        {"id": "A1", "role": "voice", "items": voice or [], **(a1 or {})},
        {"id": "A2", "role": "music", "items": music or [], **(a2 or {})},
    ]}


def test_role_weights_match_the_render(tmp_path):
    out = _run(tmp_path, _doc(), 0)
    assert out["MIX"] == R.MIX


def test_a_clip_is_scheduled_at_its_source_offset_from_mid_clip(tmp_path):
    # Voice clip on the timeline at 2s playing source 5..9 at half volume; play from 3s.
    out = _run(tmp_path, _doc(voice=[_clip("a1", 2, 5, 9, volume=0.5)]), 3)
    assert out["ready"] is True
    (c,) = out["clips"]
    t0 = 10.06  # currentTime 10 + the 60 ms lead
    assert c["start"] == [t0, 6.0, 3.0]  # when, offset into the source, remaining length
    assert c["env"] == [["set", 0.5, t0]]  # level = volume x voice weight 1.0
    # The playhead is the audio clock: it holds during the lead, then runs at real time.
    assert out["now0"] == 3 and abs(out["now15"] - (3 + 1.5 - 0.06)) < 1e-6


def test_a_later_clip_waits_and_fades_like_afade(tmp_path):
    music = [_clip("m1", 2, 0, 4, volume=1.0, fade_in=1, fade_out=2)]
    out = _run(tmp_path, _doc(music=music), 0)
    (c,) = out["clips"]
    when = 10.06 + 2
    assert c["start"] == [round(when, 4), 0.0, 4.0]
    w = R.MIX["music"]
    r = lambda x: round(x, 4)  # noqa: E731 -- the harness rounds to 4 places
    assert c["env"] == [["set", 0.0, r(when)], ["ramp", w, r(when + 1)], ["set", w, r(when + 2)], ["ramp", 0.0, r(when + 4)]]


def test_a_clip_that_already_ended_is_not_scheduled(tmp_path):
    out = _run(tmp_path, _doc(voice=[_clip("a1", 0, 0, 2), _clip("a2", 2, 2, 6)]), 3)
    assert [c["start"][1] for c in out["clips"]] == [3.0]  # only a2, 1s into it


@pytest.mark.parametrize(
    ("a1", "a2", "want"),
    [
        ({}, {}, (1.0, 1.0)),
        ({"mute": True}, {}, (0.0, 1.0)),
        ({"solo": True}, {}, (1.0, 0.0)),  # any solo silences every track not soloed
        ({"solo": True, "gain": 0.5}, {"solo": True}, (0.5, 1.0)),
        ({"gain": 0.0}, {"gain": 2.0}, (0.0, 2.0)),
    ],
)
def test_track_strips_follow_mute_solo_and_gain(tmp_path, a1, a2, want):
    out = _run(tmp_path, _doc(a1=a1, a2=a2, voice=[_clip("a1", 0, 0, 4)], music=[_clip("m1", 0, 0, 4)]), 0)
    strips = [c["strip"][-1][1] for c in out["clips"]]
    assert tuple(strips) == want


def test_a_2x_shuttle_halves_the_wall_times_but_not_the_source_offsets(tmp_path):
    """J/K/L 2x: the clip still plays its own source span (offset and length in source
    seconds) but twice as fast, so its start waits half as long and its fades take half as
    long; the playhead runs at twice real time."""
    music = [_clip("m1", 2, 0, 4, volume=1.0, fade_in=1, fade_out=2)]
    out = _run(tmp_path, _doc(music=music), 0, 2)
    (c,) = out["clips"]
    when = round(10.06 + 2 / 2, 4)
    assert c["rate"] == 2
    assert c["start"] == [when, 0.0, 4.0]
    w = R.MIX["music"]
    r = lambda x: round(x, 4)  # noqa: E731
    assert c["env"] == [["set", 0.0, when], ["ramp", w, r(when + 0.5)], ["set", w, r(when + 1)], ["ramp", 0.0, r(when + 2)]]
    assert abs(out["now15"] - 2 * (1.5 - 0.06)) < 1e-6


def test_the_volume_envelope_is_automated_like_the_render(tmp_path):
    """Keys 1.0 @1s, 0.25 @1.2s on a clip played from 0.5s into it: the envelope starts at its
    value there (1.0), ramps to 0.25 at the 1.2s key, then holds -- the render's rule."""
    keys = [{"at": 1.0, "gain": 1.0}, {"at": 1.2, "gain": 0.25}]
    out = _run(tmp_path, _doc(voice=[_clip("a1", 2, 0, 4, gain_keys=keys)]), 2.5)
    (c,) = out["clips"]
    t0 = 10.06
    assert c["envelope"] == [["set", 1.0, t0], ["ramp", 1.0, round(t0 + 0.5, 4)], ["ramp", 0.25, round(t0 + 0.7, 4)]]
    # Started after the last key: it simply holds the last value.
    out = _run(tmp_path, _doc(voice=[_clip("a1", 0, 0, 4, gain_keys=keys)]), 3)
    assert out["clips"][0]["envelope"] == [["set", 0.25, t0]]
    # No envelope: no extra stage.
    out = _run(tmp_path, _doc(voice=[_clip("a1", 0, 0, 4)]), 0)
    assert out["clips"][0]["envelope"] is None


# ---- retime: the preview's time map is the render's ------------------------------------------

MAP_HARNESS = r"""
const fs = require("fs"), vm = require("vm");
global.window = {};
vm.runInThisContext(fs.readFileSync(process.argv[2], "utf8"));
const c = JSON.parse(process.argv[3]);
const ts = JSON.parse(process.argv[4]);
console.log(JSON.stringify({ src: ts.map((t) => window.HSMix.srcAt(c, t)), back: ts.map((t) => window.HSMix.tlAt(c, window.HSMix.srcAt(c, t))), sp: ts.map((t) => window.HSMix.speedAt(c, t)), kt: window.HSMix.keyTimes(c) }));
"""


def _map(tmp_path, clip, ts):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    h = tmp_path / "map.js"
    h.write_text(MAP_HARNESS)
    r = subprocess.run([node, str(h), str(MIX_JS), json.dumps(clip), json.dumps(ts)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.parametrize(
    "keys",
    [
        None,  # constant speed
        [(0.0, 0.5), (8.0, 2.0)],
        [(0.0, 1.0), (2.0, 0.5), (6.0, 2.0)],
        [(2.0, 0.25), (5.0, 4.0)],  # first key late: the first speed holds before it
    ],
)
def test_the_preview_time_map_is_the_timelines(tmp_path, keys):
    """HSMix.srcAt (page + mixer) and timeline.source_offset (frame cache + render sizing) give
    the same source second at every point of the clip, for constant speed and for ramps."""
    from hermes_studio import timeline as T

    s = T.TICK_RATE
    item = {"type": "clip", "src": [0, 8 * s], "props": {"speed": [3, 2]}}
    clip = {"src_in": 0, "src_out": 8, "speed": 1.5}
    if keys:
        item["props"]["speed_keys"] = [{"at": int(a * s), "speed": list(__import__("fractions").Fraction(v).limit_denominator(1000).as_integer_ratio())} for a, v in keys]
        clip["speed_keys"] = [[a, v] for a, v in keys]
    L = T.item_duration(item) / s
    clip["dur"] = L
    ts = [L * i / 40 for i in range(40)]
    js = _map(tmp_path, clip, ts)
    py = [T.source_offset(item, int(round(t * s))) / s for t in ts]
    assert max(abs(a - b) for a, b in zip(js["src"], py)) < 1e-4
    # tlAt is srcAt's inverse (the film path places the playhead with it).
    assert max(abs(a - b) for a, b in zip(js["back"], ts)) < 1e-6


def test_a_2x_sound_clip_plays_its_source_twice_as_fast(tmp_path):
    c = _clip("a1", 0, 0, 8)
    c["speed"], c["dur"] = 2.0, 4.0
    out = _run(tmp_path, _doc(voice=[c]), 1)  # 1s into the timeline = 2s into the source
    (x,) = out["clips"]
    assert x["start"] == [10.06, 2.0, 6.0]
    assert x["rate"] == 2.0


def test_a_ramped_sound_clip_follows_the_ramp_exactly(tmp_path):
    """0.5x -> 2x over the first 4s of source, then 2x held: the rate starts at 0.5 and rises
    exponentially to 2 exactly at the key's timeline time (4 ln4 / 1.5 = 3.697s) -- the speed
    is s0*e^(k w) in playback time, which is what exponentialRamp draws -- then holds."""
    import math

    c = _clip("a1", 0, 0, 8)
    t_key = 4 * math.log(4) / 1.5
    c["speed_keys"], c["dur"] = [[0, 0.5], [4, 2.0]], t_key + 4 / 2.0
    out = _run(tmp_path, _doc(voice=[c]), 0)
    (x,) = out["clips"]
    assert x["start"] == [10.06, 0.0, 8.0]
    assert x["rates"] == [["set", 0.5, 10.06], ["exp", 2.0, round(10.06 + t_key, 4)]]


def test_a_ramped_sound_clip_started_mid_ramp_picks_up_the_right_rate(tmp_path):
    """Play from 2s on the timeline, inside the ramp: the buffer starts at the source second the
    render shows there, at that moment's speed."""
    import math

    from hermes_studio import timeline as T

    c = _clip("a1", 0, 0, 8)
    t_key = 4 * math.log(4) / 1.5
    c["speed_keys"], c["dur"] = [[0, 0.5], [4, 2.0]], t_key + 2.0
    out = _run(tmp_path, _doc(voice=[c]), 2)
    (x,) = out["clips"]
    k = 1.5 / 4
    src = 0.5 * (math.exp(k * 2) - 1) / k  # the inverse of the integral at 2s
    assert x["start"][1] == pytest.approx(src, abs=1e-3)
    assert x["rates"][0][1] == pytest.approx(0.5 + k * src, abs=1e-3)  # speed at that source time
    s = T.TICK_RATE
    item = {"type": "clip", "src": [0, 8 * s], "props": {"speed_keys": [{"at": 0, "speed": [1, 2]}, {"at": 4 * s, "speed": [2, 1]}]}}
    assert T.source_offset(item, 2 * s) / s == pytest.approx(src, abs=1e-6)
