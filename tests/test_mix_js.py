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
  setTargetAtTime(v, t) { this.events.push(["target", +v.toFixed(4)]); this.value = v; return this; }
}
class Node { constructor() { this.out = []; } connect(n) { this.out.push(n); return n; } disconnect() {} }
class Gain extends Node { constructor() { super(); this.gain = new Param(1); } }
class Src extends Node { constructor() { super(); this.started = null; } start(w, o, d) { this.started = [+w.toFixed(4), +o.toFixed(4), +d.toFixed(4)]; } stop() {} }
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
(async () => {
  const m = window.HSMix.create();
  await m.load(doc, "p");
  const ready = m.ready(doc);
  m.start(doc, play);
  const ctx = AC.last;
  const clips = ctx.sources.map((s) => {
    const clipGain = s.out[0], strip = clipGain.out[0];
    return { start: s.started, env: clipGain.gain.events, strip: strip.gain.events };
  });
  const now0 = m.now();
  ctx.currentTime += 1.5;
  console.log(JSON.stringify({ ready, MIX: window.HSMix.MIX, clips, now0, now15: +m.now().toFixed(4) }));
})();
"""


def _run(tmp_path, doc: dict, play: float) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    h = tmp_path / "harness.js"
    h.write_text(HARNESS)
    r = subprocess.run([node, str(h), str(MIX_JS), json.dumps(doc), str(play)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _clip(cid, at, src_in, src_out, **kw):
    return {"id": cid, "type": "clip", "file": f"{cid}.mp4", "at": at, "dur": src_out - src_in,
            "src_in": src_in, "src_out": src_out, "volume": kw.get("volume"),
            "fade_in": kw.get("fade_in", 0), "fade_out": kw.get("fade_out", 0), "media_dur": 30}


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
