"""Render a timeline document to a file with ffmpeg.

The op log decides what the cut is; this module turns that decision into pixels and
sound. Nothing here writes the timeline: it only reads it.

Shape of a render:
  * Every clip on the main track is trimmed from its source, scaled to the canvas
    with ``contain`` (the whole frame is kept, never cropped) and laid end to end.
    A gap between clips renders as black, not a frozen frame.
  * Voice and music items are placed at their own times on the timeline through
    ``adelay``, so a gap in a sound track stays a gap instead of being squeezed.
    Voice sits at full level, music under it. Output is loudness-normalised.
  * Text items burn in as captions through the same ASS builder the clips use, so
    the Edit page and a finished clip look like the same product.
  * The output is exactly the canvas size: a Phone cut is 1080x1920, a Desktop cut
    1920x1080, with no guessing.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from collections.abc import Callable
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any

from hermes_studio import grade as _G
from hermes_studio import timeline as T
from hermes_studio.editor import EditorError, resolve_media

# Voice is the story; music sits under it.
MIX = {"voice": 1.0, "music": 0.35}


class RenderError(Exception):
    pass


def _run(cmd: list[str], *, timeout: int = 7200) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RenderError(proc.stderr[-2500:] or "ffmpeg failed")


def _probe_size(path: Path) -> tuple[int, int]:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        w, h = (int(x) for x in proc.stdout.strip().split(",")[:2])
    except ValueError as exc:
        raise RenderError(f"cannot read that picture: {path.name}") from exc
    if proc.returncode != 0 or w <= 0 or h <= 0:
        raise RenderError(f"cannot read that picture: {path.name}")
    return w, h


def _has_audio(path: Path) -> bool:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode == 0 and "audio" in proc.stdout


def _fps(doc: dict) -> float:
    raw = doc.get("fps") or [30, 1]
    try:
        num, den = int(raw[0]), int(raw[1])
    except (IndexError, TypeError, ValueError):
        return 30.0
    return num / den if num > 0 and den > 0 else 30.0


def _t2s(ticks: int, rate: int) -> float:
    return ticks / rate


def _speed(it: dict) -> float:
    """The clip's playback speed as a float. props.speed is a reduced [num, den] pair; a
    missing or invalid value means real time (1.0)."""
    props = it.get("props") or {}
    raw = props.get("speed")
    try:
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            num, den = float(raw[0]), float(raw[1])
            if den != 0 and num > 0:
                return num / den
        if isinstance(raw, (int, float)) and raw > 0:
            return float(raw)
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return 1.0


def _crop(it: dict) -> dict | None:
    """The clip's crop box, or None. props.crop is {x, y, w, h} as fractions of the source
    frame (0-1), each a reduced [num, den] pair (the schema stores ratios that way). A
    missing/empty/identity box means no crop."""

    def frac(v: Any) -> float | None:
        if isinstance(v, (list, tuple)) and len(v) == 2:
            try:
                num, den = float(v[0]), float(v[1])
                return num / den if den != 0 else None
            except (TypeError, ValueError, ZeroDivisionError):
                return None
        if isinstance(v, (int, float)):
            return float(v)
        return None

    raw = (it.get("props") or {}).get("crop")
    if not isinstance(raw, dict):
        return None
    vals = {k: frac(raw.get(k)) for k in ("x", "y", "w", "h")}
    if any(v is None for v in vals.values()):
        return None
    x, y, w, h = vals["x"], vals["y"], vals["w"], vals["h"]
    if not all(0.0 <= v <= 1.0 for v in (x, y, w, h)):
        return None
    if w <= 0 or h <= 0 or x + w > 1.0 + 1e-6 or y + h > 1.0 + 1e-6:
        return None
    if x == 0.0 and y == 0.0 and w == 1.0 and h == 1.0:
        return None
    return {"x": x, "y": y, "w": w, "h": h}


# Named looks are grades now (grade.LOOKS): see grade.py for the fitted presets.


def _transform(it: dict) -> dict | None:
    """The clip's transform, or None. props.transform is {x, y, scale, rotate} -- position as a
    fraction of the canvas, a positive scale multiplier, and rotation in degrees, each a
    reduced [num, den] pair. The identity (0, 0, 1, 0) means no transform."""

    def frac(v: Any) -> float | None:
        if isinstance(v, (list, tuple)) and len(v) == 2:
            try:
                num, den = float(v[0]), float(v[1])
                return num / den if den != 0 else None
            except (TypeError, ValueError, ZeroDivisionError):
                return None
        if isinstance(v, (int, float)):
            return float(v)
        return None

    raw = (it.get("props") or {}).get("transform")
    if not isinstance(raw, dict):
        return None
    vals = {k: frac(raw.get(k)) for k in ("x", "y", "scale", "rotate")}
    if any(v is None for v in vals.values()):
        return None
    x, y, scale, rotate = vals["x"], vals["y"], vals["scale"], vals["rotate"]
    if scale <= 0:
        return None
    if x == 0.0 and y == 0.0 and scale == 1.0 and rotate == 0.0:
        return None
    return {"x": x, "y": y, "scale": scale, "rotate": rotate}


def _keyframes(it: dict, rate: int) -> list[dict] | None:
    """The clip's keyframes as plain floats, `at` in seconds from the clip's start, sorted.
    None when there are none. Each is {at, x, y, scale, rotate}; the values match the
    transform's ranges and are stored as [num, den] pairs."""

    def frac(v: Any) -> float | None:
        if isinstance(v, (list, tuple)) and len(v) == 2:
            try:
                num, den = float(v[0]), float(v[1])
                return num / den if den != 0 else None
            except (TypeError, ValueError, ZeroDivisionError):
                return None
        if isinstance(v, (int, float)):
            return float(v)
        return None

    raw = (it.get("props") or {}).get("keyframes")
    if not isinstance(raw, list) or not raw:
        return None
    out = []
    for kf in raw:
        if not isinstance(kf, dict):
            return None
        at = kf.get("at")
        if not isinstance(at, int):
            return None
        vals = {k: frac(kf.get(k)) for k in ("x", "y", "scale", "rotate")}
        if any(v is None for v in vals.values()):
            return None
        if vals["scale"] <= 0:
            return None
        out.append({"at": at / rate, **vals})
    out.sort(key=lambda k: k["at"])
    return out or None


def _level(raw: Any) -> float:
    """A level stored as a reduced [num, den] pair (0 to 4 per the schema) as a float; a
    missing or invalid value means unity (1.0). Used for clip volume and track gain alike."""
    try:
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            num, den = float(raw[0]), float(raw[1])
            if den != 0 and num >= 0:
                return min(num / den, 4.0)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw >= 0:
            return min(float(raw), 4.0)
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return 1.0


def _balance(raw: Any) -> float:
    """A track balance stored as a [num, den] pair, as a float in -1..1; 0 (centre) when missing.
    ``_level`` is for volumes and gains, which are never negative -- it reads a stored -1 as
    unity, which would pan a hard-left track hard RIGHT. Pan is signed, so it gets its own reader."""
    try:
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            num, den = float(raw[0]), float(raw[1])
            if den != 0:
                return max(-1.0, min(1.0, num / den))
    except (TypeError, ValueError):
        pass
    return 0.0


def _volume(it: dict) -> float:
    """The clip's playback volume (props.volume) as a float."""
    return _level((it.get("props") or {}).get("volume"))


def _speed_keys(it: dict, rate: int) -> list[dict] | None:
    """The clip's speed ramp as [{at: clip-local seconds, speed: float}] on its own window, or
    None: timeline.ramp_curve, so a split piece renders exactly its part of the original ramp
    and the render, view and time map read one curve."""
    curve = T.ramp_curve(it) if it.get("src") else None
    return [{"at": a, "speed": v} for a, v in curve] if curve else None


def _ramp_pts(kfs: list[dict]) -> str:
    """A setpts expression that plays a clip through a speed ramp.

    The output time of a source frame at ``t`` seconds (clip-local) is the integral of 1/speed
    from 0 to ``t``. Between two keys the speed is linear in ``t`` so 1/speed integrates to a
    natural log; before the first key and after the last the speed holds (a plain divide).

    ``t`` is ``(PTS-STARTPTS)*TB`` -- ffmpeg's own ``TB``, the stream's real timebase -- and the
    result is divided by ``TB`` to get back to PTS units. Segment offsets are summed FORWARD from
    the clip start, so each piece starts where the one before it ended. (The first version
    divided by a made-up 1e6 ticks/s and summed offsets from the end; three-key ramps showed
    frames up to 140 off.) Speeds and times are rendered with enough digits for frame accuracy.
    """
    def v(x: float) -> str:
        return f"{x:.9f}"

    pts = [(float(k["at"]), float(k["speed"])) for k in kfs]
    t = "((PTS-STARTPTS)*TB)"
    # Output seconds at each key, summed forward. Before key 0 the first speed holds.
    starts = [pts[0][0] / pts[0][1]]
    for (ta, sa), (tb, sb) in zip(pts, pts[1:], strict=False):
        d = tb - ta
        if d <= 0:
            starts.append(starts[-1])
            continue
        k = (sb - sa) / d
        starts.append(starts[-1] + (d / sa if abs(k) < 1e-12 else (math.log(sb) - math.log(sa)) / k))
    # After the last key: hold the last speed.
    ta, sa = pts[-1]
    expr = f"{v(starts[-1])}+({t}-{v(ta)})/{v(sa)}"
    for i in range(len(pts) - 2, -1, -1):
        (ta, sa), (tb, sb) = pts[i], pts[i + 1]
        if tb <= ta:
            continue
        k = (sb - sa) / (tb - ta)
        if abs(k) < 1e-12:
            piece = f"{v(starts[i])}+({t}-{v(ta)})/{v(sa)}"
        else:
            piece = f"{v(starts[i])}+log(({v(sa)}+{v(k)}*({t}-{v(ta)}))/{v(sa)})/{v(k)}"
        expr = f"if(lt({t},{v(tb)}),{piece},{expr})"
    expr = f"if(lt({t},{v(pts[0][0])}),{t}/{v(pts[0][1])},{expr})"
    return f"({expr})/TB"


def _gain_keys(it: dict, rate: int) -> list[dict] | None:
    """The clip's volume envelope as [{at: clip-local seconds, gain: float}], or None."""
    raw = (it.get("props") or {}).get("gain_keys")
    if not isinstance(raw, list) or not raw:
        return None
    out = []
    for k in raw:
        if isinstance(k, dict) and isinstance(k.get("at"), int):
            out.append({"at": _t2s(k["at"], rate), "gain": _level(k.get("gain"))})
    return out or None


TB = 1000000.0  # internal 'seconds' unit for a speed-ramp setpts expression


REVERSE_CHUNK_S = 4.0  # seconds per reversed piece: ffmpeg's reverse filter buffers every frame


def _reversed_source(folder: Path, path: Path, i0: int, o1: int, rate: int) -> Path:
    """The source window [i0, o1) played backwards, as a cached file the render then treats as an
    ordinary forward clip (so speed, ramps, grade and fades apply to it unchanged).

    ffmpeg's ``reverse``/``areverse`` hold the whole input in memory -- about 2.8 GB for 30 s of
    1080p -- so the window is cut into REVERSE_CHUNK_S pieces from the END, each reversed on its
    own, and joined in that order. Sound is reversed with it (PCM, so the pieces join without
    codec priming gaps). Keyed by the file's size and mtime plus the window, under
    <project>/cache/reverse."""
    import hashlib

    st = path.stat()
    key = hashlib.sha1(f"{path.name}|{st.st_size}|{st.st_mtime_ns}|{i0}|{o1}|{rate}|rev2".encode(), usedforsecurity=False).hexdigest()[:16]
    out = folder / "cache" / "reverse" / f"{key}.mov"
    if out.is_file() and out.stat().st_size > 0:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    a, b = i0 / rate, o1 / rate
    audio = _has_audio(path)
    work = out.parent / f".{key}.parts"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    try:
        parts, hi, n = [], b, 0
        while hi - a > 1e-6:
            lo = max(a, hi - REVERSE_CHUNK_S)
            part = work / f"{n:04d}.mov"
            # -ss AND -t on the INPUT: reverse reads to end of stream, so an output -t let it
            # buffer the rest of the file and kept the wrong frames (every piece came out as
            # the file's last seconds).
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{lo:.6f}", "-t", f"{hi - lo:.6f}",
                   "-i", str(path), "-map", "0:v:0", "-vf", "reverse"]
            if audio:
                cmd += ["-map", "0:a:0", "-af", "areverse", "-c:a", "pcm_s16le", "-ar", "48000"]
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p", str(part)]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            if r.returncode != 0 or not part.is_file():
                raise RenderError("could not reverse the clip: " + (r.stderr or "").strip()[-300:])
            parts.append(part)
            hi, n = lo, n + 1
        lst = work / "list.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
        tmp = out.with_name(f".{key}.tmp.mov")
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-c", "copy", str(tmp)], capture_output=True, text=True, timeout=1800)
        if r.returncode != 0 or not tmp.is_file():
            raise RenderError("could not join the reversed clip: " + (r.stderr or "").strip()[-300:])
        tmp.replace(out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def _atempo(tempo: float) -> str:
    """The atempo filter chain that plays at ``tempo``. atempo accepts 0.5 to 100, so a tempo
    below 0.5 (a clip slower than half speed) chains halves until the rest fits: 0.1x is
    0.5,0.5,0.4. Pitch is preserved throughout, which is what a retime should sound like."""
    if abs(tempo - 1.0) < 1e-9:
        return ""
    if tempo >= 0.5:
        return f"atempo={tempo:.6f}"
    parts = []
    rest = tempo
    while rest < 0.5 - 1e-9:
        parts.append("atempo=0.5")
        rest *= 2.0
    parts.append(f"atempo={rest:.6f}")
    return ",".join(parts)


def _audio_segments(row: dict, rate: int) -> list[tuple[float, float, str]]:
    """How an audio item is retimed: [(source start s, source end s, atempo chain)], in order,
    concatenated by the caller. One segment for a constant speed; one per ramp segment otherwise.

    For a segment where the speed ramps s0 -> s1 across D seconds of source, the picture runs
    D * ln(s1/s0) / (s1 - s0) seconds, so the tempo that makes the SOUND come out at exactly that
    length is (s1 - s0) / ln(s1/s0) -- which tends to s0 as s1 tends to s0. Splitting on the
    source clock keeps the total equal to the picture's integral, so sound and picture stay in
    step; each segment is time-stretched with its pitch kept."""
    i0, o1 = row["src"]
    dur = _t2s(o1 - i0, rate)
    sk = row.get("speed_keys")
    if not sk or len(sk) < 2:
        return [(0.0, dur, _atempo(float(row.get("speed") or 1.0)))]
    ks = [(k["at"], k["speed"]) for k in sk]

    def speed_at(t: float) -> float:
        if t <= ks[0][0]:
            return ks[0][1]
        for (ta, sa), (tb, sb) in zip(ks, ks[1:], strict=False):
            if t <= tb:
                return sa + (sb - sa) * (t - ta) / (tb - ta) if tb > ta else sb
        return ks[-1][1]

    bounds = sorted({0.0, dur, *(min(dur, max(0.0, t)) for t, _ in ks)})
    out = []
    for a_t, b_t in zip(bounds, bounds[1:], strict=False):
        if b_t - a_t < 1e-6:
            continue
        s0, s1 = speed_at(a_t), speed_at(b_t)
        if abs(s1 - s0) < 1e-9:
            tempo = s0
        else:
            tempo = (s1 - s0) / math.log(s1 / s0)
        out.append((a_t, b_t, _atempo(tempo)))
    return out


def _ass_escape_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _canvas(doc: dict) -> tuple[int, int]:
    size = list(doc.get("size") or [1920, 1080])
    try:
        w, h = int(size[0]), int(size[1])
    except (IndexError, TypeError, ValueError) as exc:
        raise RenderError("canvas is not a width and a height") from exc
    if not (1 <= w <= 16384 and 1 <= h <= 16384):
        raise RenderError("canvas must be 1 to 16384 on each side")
    return w, h


def _contain(sw: int, sh: int, w: int, h: int) -> tuple[int, int, int, int]:
    """Scale to fit the canvas, centred. Widths are even so the encoder is happy."""
    if sw <= 0 or sh <= 0 or w <= 0 or h <= 0:
        raise RenderError("canvas must be 1 to 16384 on each side")
    scale = min(w / sw, h / sh)
    dw = max(2, int(round(sw * scale)) // 2 * 2)
    dh = max(2, int(round(sh * scale)) // 2 * 2)
    return dw, dh, (w - dw) // 2, (h - dh) // 2


# --------------------------------------------------------------------------- plan


def _build_plan(doc: dict, folder: Path) -> dict:
    """Turn a timeline doc into a render plan. Pure: ffmpeg is never touched here."""
    w, h = _canvas(doc)
    rate = doc["tick_rate"]
    media = doc.get("media") or {}

    def items(role: str) -> list[dict]:
        for tr in doc["tracks"]:
            if tr.get("role") == role:
                return [it for it in tr["items"] if "at" in it and it.get("type") != "transition"]
        return []

    main = sorted(items("main"), key=lambda it: it["at"])
    if not main:
        raise RenderError("nothing on the main track")

    inputs: list[dict] = []
    seen: dict[str, int] = {}
    end_tick = 0
    cursor = 0
    for it in main:
        i0, o1 = it["src"]
        if i0 >= o1:
            raise RenderError("a clip has no length")
        speed = _speed(it)
        speed_keys = _speed_keys(it, rate)
        # The clip's length on the timeline is the one length rule the schema, view and ripple
        # use: source range / speed, a ramp's integral, or a freeze frame's hold.
        tl_dur = T.item_duration(it)
        if tl_dur <= 0:
            raise RenderError("a clip has no length")
        rel = str(media.get(it.get("media") or "", {}).get("path") or "")
        if not rel:
            raise RenderError("a clip has no picture")
        path = resolve_media(folder, rel)
        if not path.is_file():
            raise RenderError(f"picture file is missing: {path.name}")
        if (it.get("props") or {}).get("reverse") is True:
            # Reversed: render from the backwards copy of the window, which is a forward clip.
            path = _reversed_source(folder, path, i0, o1, rate)
            rel = "reverse/" + path.name
            i0, o1 = 0, o1 - i0
        if cursor < it["at"]:
            inputs.append({"role": "gap", "at": cursor, "end": it["at"]})
        cursor = it["at"] + tl_dur
        end_tick = max(end_tick, cursor)
        idx = seen.get(rel)
        crop = _crop(it)
        look = str((it.get("props") or {}).get("look") or "").strip() or None
        transform = _transform(it)
        keyframes = _keyframes(it, rate)
        fi, fo = it.get("fade_in") or 0, it.get("fade_out") or 0
        props_ = it.get("props") or {}
        # A legacy props.look renders as that look's grade (the eq/colorbalance chains are gone).
        grade = _G.parse(props_.get("grade") or (_G.look(look) if look in _G.LOOKS else None))
        hold = props_.get("hold") if isinstance(props_.get("hold"), int) and props_.get("hold") > 0 else None
        clip_extra = {"crop": crop, "look": look, "grade": grade, "fade_in": fi, "fade_out": fo, "transform": transform,
                      "keyframes": keyframes, "speed_keys": None if hold else speed_keys, "tl_dur": tl_dur, "hold": hold}
        if idx is None:
            idx = len(inputs)
            seen[rel] = idx
            sw, sh = _probe_size(path)
            inputs.append({"role": "clip", "idx": idx, "path": path, "src": (i0, o1), "at": it["at"], "size": (sw, sh), "id": it.get("id"), "speed": speed, **clip_extra})
        else:
            inputs.append({"role": "clip", "idx": idx, "path": path, "src": (i0, o1), "at": it["at"], "size": None, "id": it.get("id"), "speed": speed, **clip_extra})

    audio: list[dict] = []
    # Every audio track, not just the first of each role (a second voice or music track used to
    # be dropped silently). The mixer strip decides what is heard: a muted track is silent; when
    # any track is soloed only soloed tracks play; gain scales every clip on the track. A muted
    # clip still counts toward the length, so muting never changes how long the cut is.
    audio_tracks = [tr for tr in doc["tracks"] if tr.get("role") in ("voice", "music")]
    any_solo = any(tr.get("solo") for tr in audio_tracks)
    sounding: dict[str, bool] = {}
    for tr in audio_tracks:
        role = tr["role"]
        gain = _level(tr.get("gain"))
        audible = not tr.get("mute") and (not any_solo or bool(tr.get("solo"))) and gain > 0
        for it in tr["items"]:
            if "at" not in it or it.get("type") == "transition":
                continue
            i0, o1 = it["src"]
            rel = str(media.get(it.get("media") or "", {}).get("path") or "")
            if not rel or i0 >= o1:
                continue
            # A retimed sound item occupies (source range) / speed ticks on the timeline, the
            # same as its picture -- not the raw source range. Otherwise a 2x clip's sound padded
            # the timeline to 8s while the picture was 4s.
            # A retimed sound item occupies its retimed length (the one length rule), not the raw
            # source range -- a 2x clip's sound used to pad the timeline to the source length.
            _at_dur = T.item_duration(it)
            end_tick = max(end_tick, it["at"] + _at_dur)
            if not audible:
                continue
            path = resolve_media(folder, rel)
            if not path.is_file():
                raise RenderError(f"sound file is missing: {path.name}")
            # A sound item on a file with no sound stream (a silent screen recording, the demo
            # plate) plays as silence. It used to reach the graph as [n:a] and fail the whole
            # render with "matches no streams".
            if rel not in sounding:
                sounding[rel] = _has_audio(path)
            if not sounding[rel]:
                continue
            if (it.get("props") or {}).get("reverse") is True:
                path = _reversed_source(folder, path, i0, o1, rate)
                rel = "reverse/" + path.name
                i0, o1 = 0, o1 - i0
            idx = seen.get(rel)
            if idx is None:
                idx = len(inputs)
                seen[rel] = idx
                inputs.append({"role": "sound", "idx": idx, "path": path, "src": None, "at": it["at"], "size": None})
            audio.append(
                {
                    "idx": idx,
                    "role": role,
                    "track": tr["id"],
                    "src": (i0, o1),
                    "at": it["at"],
                    "fade_in": it.get("fade_in") or 0,
                    "fade_out": it.get("fade_out") or 0,
                    "volume": _volume(it) * gain,
                    "pan": _balance(tr.get("pan")),  # -1..1 track balance (unity at centre)
                    "duck": T.duck_envelope(doc, tr),
                    "gain_keys": _gain_keys(it, rate),
                    # A retimed sound item plays at its own speed: without this the picture
                    # moves and the sound does not, and the two drift apart.
                    "speed": _speed(it),
                    "speed_keys": _speed_keys(it, rate),
                }
            )

    captions = []
    titles = []
    for it in items("text"):
        if isinstance(it.get("title"), dict):
            # A designed title: one PNG of the canvas, overlaid with its motion (titles.py).
            from hermes_studio import titles as _TT

            titles.append({"at": it["at"], "dur": it.get("dur") or 0, "fi": it.get("fade_in") or 0, "fo": it.get("fade_out") or 0,
                           "png": _TT.png(it["title"], folder / "cache"), "in": it["title"].get("in", "fade"),
                           "out": it["title"].get("out", "fade")})
            end_tick = max(end_tick, it["at"] + (it.get("dur") or 0))
            continue
        text = " ".join(str(it.get("text") or "").split())
        if not text:
            continue
        captions.append({"at": it["at"], "dur": it.get("dur") or 0, "text": text, "style": str(it.get("style") or "pop")})
        end_tick = max(end_tick, it["at"] + (it.get("dur") or 0))

    # Transitions: a cross-dissolve is an overlap of exactly 'dur' between two consecutive
    # main-track clips. The render replaces the concat at that seam with an xfade, keyed by
    # the two clip ids and the offset (in output seconds) where the blend begins.
    transitions = []
    for tr in doc["tracks"]:
        if tr.get("role") != "main":
            continue
        by_id = {i["id"]: i for i in tr["items"] if i.get("type") == "clip" and "at" in i}
        for it in tr["items"]:
            if it.get("type") != "transition":
                continue
            a_id, b_id = it.get("between", [None, None])
            a, b = by_id.get(a_id), by_id.get(b_id)
            if not a or not b:
                continue
            dur = it.get("dur", 0)
            if dur <= 0:
                continue
            a_end = a["at"] + (a["src"][1] - a["src"][0])
            transitions.append(
                {
                    "a": a_id,
                    "b": b_id,
                    "dur": dur,
                    "offset": a_end - dur,  # the blend starts where a would have ended, minus the overlap
                    "kind": str(it.get("kind") or "fade"),
                }
            )

    if end_tick <= 0:
        raise RenderError("nothing to render")

    return {
        "width": w,
        "height": h,
        "fps": _fps(doc),
        "rate": rate,
        "inputs": inputs,
        "audio": audio,
        "captions": captions,
        "titles": titles,
        "transitions": transitions,
        "end_tick": end_tick,
        "silent": not any(True for _ in audio),
        # Where a grade with custom curves writes its 1D LUT (grade.ffmpeg_chain).
        "cache": str(folder / "cache"),
    }


def _build_ass(plan: dict, cache: Path) -> Path | None:
    """Captions as an ASS file under the project cache. None when the cut has no text."""
    from hermes_studio.captions import STYLES, build_ass
    from hermes_studio.transcribe import Word

    if not plan["captions"]:
        return None
    rate = plan["rate"]
    words: list[Word] = []
    for cap in plan["captions"]:
        start = _t2s(cap["at"], rate)
        end = max(start + 0.01, _t2s(cap["at"] + cap["dur"], rate))
        for tok in cap["text"].split():
            words.append(Word(text=tok, start=start, end=end))
    if not words:
        return None
    styles = {c["style"] for c in plan["captions"]}
    style = styles.pop() if len(styles) == 1 else "pop"
    st = STYLES.get(style, STYLES["pop"])
    cache.mkdir(parents=True, exist_ok=True)
    ass = cache / "render.ass"
    ass.write_text(
        build_ass(
            words,
            0.0,
            _t2s(plan["end_tick"], plan["rate"]) + 1.0,
            None,
            plan["width"],
            plan["height"],
            style,
            layout="fit",
            place=(2, st.margin_v_fit),
        )
    )
    return ass


# --------------------------------------------------------------------------- graph


def _pan_filter(pan: float) -> str:
    """A track's balance, as ffmpeg pan -- the law every NLE uses for a stereo track (Resolve's
    Pan, FCP's Balance): unity at the centre, so parking the knob in the middle changes nothing,
    then a cos curve to full on one side and silence on the other at the edge. Each output takes
    its own input channel, never a blend, and ``n=0`` stops ffmpeg renormalising (which would
    make the edges quiet rather than silent). The page mirrors these two numbers (mix.js), so a
    clip panned hard left is equally hard left in the preview and in the export."""
    p = max(-1.0, min(1.0, float(pan)))
    gl = 1.0 if p <= 0 else math.cos(p * math.pi / 2)
    gr = 1.0 if p >= 0 else math.cos(-p * math.pi / 2)
    return f"pan=stereo|FL={gl:.6f}*c0|FR={gr:.6f}*c1"


@lru_cache(maxsize=256)
def _audio_channels(path: str) -> int:
    """How many audio channels a file has, probed once. A mono file (a voiceover, a phone
    recording) has no right channel to balance, so it is upmixed to stereo before the pan."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=channels",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=60)
    try:
        return max(1, int((r.stdout.strip().split(",") or ["1"])[0]))
    except ValueError:
        return 1


def _duck_expr(pts: list[tuple[float, float]]) -> str:
    """The ducking envelope as one volume expression over TIMELINE seconds. The stream is
    padded and delayed to the cut's start before this, so its clock is the timeline's; the same
    point list the page reads from the view, so preview and render dip together."""
    return f"volume=eval=frame:volume='{_interp_expr([{'at': a, 'gain': g} for a, g in pts], 'gain', 't')}'"


def _interp_expr(kfs: list[dict], key: str, tvar: str) -> str:
    """A piecewise-linear ffmpeg expression for one value over keyframes (sorted by ``at``).

    Before the first key it holds the first value; between two keys it ramps linearly; after
    the last key it holds the LAST value. Built from the end: start with the last value, then
    for each segment from the last to the first wrap ``if(lt(t, b.at), <segment>, <rest>)``,
    and finally guard the time before the first key.

    The old builder got two things wrong, and transform keyframes rendered wrong because of it:
    after the last key it fell back to the FIRST key's value, and a segment between two equal
    values replaced everything built so far (so keys 1, 2, 2, 1 lost the ramp from 1 to 2).
    """
    def v(x: float) -> str:
        return f"{x:.6f}"

    expr = v(kfs[-1][key])
    for i in range(len(kfs) - 1, 0, -1):
        a, b = kfs[i - 1], kfs[i]
        if abs(b[key] - a[key]) < 1e-12 or b["at"] <= a["at"]:
            seg = v(a[key])
        else:
            seg = f"{v(a[key])}+({v(b[key])}-{v(a[key])})*({tvar}-{v(a['at'])})/({v(b['at'])}-{v(a['at'])})"
        expr = f"if(lt({tvar},{v(b['at'])}),{seg},{expr})"
    return f"if(lt({tvar},{v(kfs[0]['at'])}),{v(kfs[0][key])},{expr})" if len(kfs) > 1 else expr


def _zoompan(kfs: list[dict], w: int, h: int, fps: float, dur: float) -> str:
    """A zoompan filter string that animates scale and pan over the keyframes. zoompan
    re-evaluates its expressions on every output frame, keyed by ``on`` (the output frame
    number), which this build advances reliably -- unlike scale's eval=frame, whose output
    size is fixed at init and so cannot resize per frame. The keyframe times (seconds) are
    converted to frame numbers by ``on``/``fps`` being the rebased clock, so the ramp is over
    frames. Rotation is not animated (zoompan has no rotate); a keyframe track with a non-zero
    rotate still animates position and scale."""
    # The caller feeds an already contain-fitted frame that fills the canvas at zoom 1, so the
    # keyframe scale is zoompan's zoom directly. Keyframe times are frames now (at * fps).
    frame_kfs = [{**k, "at": k["at"] * fps} for k in kfs]
    z = _interp_expr(frame_kfs, "scale", "on")
    xx = _interp_expr(frame_kfs, "x", "on")
    yy = _interp_expr(frame_kfs, "y", "on")
    # zoompan's x/y are the top-left of the crop window in the zoomed image; centre the crop
    # and add the pan offset (a fraction of the input size). iw/ih are the input size.
    xexp = f"iw/2-(iw/zoom/2)+({xx})*iw"
    yexp = f"ih/2-(ih/zoom/2)+({yy})*ih"
    return f"zoompan=z='{z}':x='{xexp}':y='{yexp}':d=1:s={w}x{h}:fps={fps:.3f},"


# --------------------------------------------------------------------------- graph


def _assemble_video(segs: list, seg_ids: list, seg_durs: list, transitions: list, rate: int) -> list:
    """Join the picture segments into ``[outv]`` as filter-graph lines.

    Adjacent clips with a cross-dissolve between them blend with ``xfade``; everything
    else is a plain ``concat``. A gap never carries a transition.

    ``xfade`` overlaps the tail of the running stream with the head of the next segment:
    the output is ``len(acc) + len(next) - duration`` long, and the blend begins at
    ``offset`` seconds into that output. Because each xfade shortens the running stream,
    the offsets must be accumulated as we fold left -- emitting one flat ``concat`` cannot
    express a seam that overlaps. ``seg_durs`` is each segment's own length in seconds, so
    the running length before a seam is the sum of the segments joined so far.
    """
    if not segs:
        raise RenderError("nothing on the main track")
    if len(segs) == 1:
        return [f"{segs[0]}copy[outv]"]

    xf = {(t["a"], t["b"]): _t2s(t["dur"], rate) for t in transitions}
    xfk = {(t["a"], t["b"]): t.get("kind", "fade") for t in transitions}

    fc: list[str] = []
    acc = segs[0]
    running = seg_durs[0]          # length of the joined stream so far, in seconds
    for i in range(1, len(segs)):
        a_id, b_id = seg_ids[i - 1], seg_ids[i]
        dur = xf.get((a_id, b_id))
        last = i == len(segs) - 1
        out = "outv" if last else f"x{i}"
        if dur:
            # The dissolve sits where the first clip would have ended: that is `running`
            # seconds into the output, and it runs for `dur`, so the seam is pulled back
            # by the overlap. ffmpeg needs the offset as a plain number.
            offset = max(0.0, running - dur)
            kind = xfk.get((a_id, b_id), "fade")
            fc.append(f"{acc}{segs[i]}xfade=transition={kind}:duration={dur:.3f}:offset={offset:.3f}[{out}]")
            running = running + seg_durs[i] - dur
        else:
            fc.append(f"{acc}{segs[i]}concat=n=2:v=1:a=0[{out}]")
            running = running + seg_durs[i]
        acc = f"[{out}]"
    return fc


def _build_graph(plan: dict, ass: Path | None) -> tuple[str, str]:
    """The filter graph, and the label to map as the output video."""
    sizes = {inp["idx"]: inp["size"] for inp in plan["inputs"] if inp.get("role") == "clip" and inp.get("size")}
    w, h = plan["width"], plan["height"]
    rate = plan["rate"]
    total = _t2s(plan["end_tick"], rate)
    fps = plan["fps"]
    fc: list[str] = []
    v_in: list[str] = []

    # The same source cut more than once needs a split so each piece keeps its trim.
    v_uses: dict[int, int] = {}
    a_uses: dict[int, int] = {}
    for inp in plan["inputs"]:
        if inp["role"] == "clip":
            v_uses[inp["idx"]] = v_uses.get(inp["idx"], 0) + 1
    for row in plan["audio"]:
        a_uses[row["idx"]] = a_uses.get(row["idx"], 0) + 1
    for idx, count in v_uses.items():
        if count > 1:
            outs = "".join(f"[s{idx}_{k}]" for k in range(count))
            fc.append(f"[{idx}:v]split={count}{outs}")
    for idx, count in a_uses.items():
        if count > 1:
            outs = "".join(f"[sa{idx}_{k}]" for k in range(count))
            fc.append(f"[{idx}:a]asplit={count}{outs}")

    cut_v: dict[int, int] = {}
    cut_a: dict[int, int] = {}
    seg_ids: list = []          # the clip id behind each segment, in order (None for a gap)
    seg_durs: list = []         # each segment's own length in seconds
    for n, inp in enumerate(plan["inputs"]):
        kind = inp["role"]
        if kind == "clip":
            idx = inp["idx"]
            k = cut_v.get(idx, 0)
            cut_v[idx] = k + 1
            src = f"s{idx}_{k}" if v_uses.get(idx, 0) > 1 else f"{idx}:v"
            i0, o1 = inp["src"]
            s_in = _t2s(i0, rate)
            src_dur = _t2s(o1 - i0, rate)
            speed = float(inp.get("speed") or 1.0)
            # The source window is always `src_dur` long; rescaling its timestamps by
            # 1/speed plays it faster (shorter output) or slower (longer). PTS-STARTPTS
            # still re-bases each segment to zero so concat/xfade see clean, aligned
            # streams; fps= then re-timestamps to the canvas rate.
            # The clip's length on the timeline: the one length rule (constant speed, a ramp's
            # integral, or a freeze frame's hold). `src_dur / speed` was wrong for a ramp, and the
            # dissolve offsets and the fade-out start read this.
            dur = _t2s(inp["tl_dur"], rate) if inp.get("tl_dur") else src_dur / speed
            v_in.append(f"[v{n}]")
            seg_ids.append(inp.get("id"))
            seg_durs.append(dur)
            # Every piece of a file has that file's size. Only the first input record carried it,
            # so the second and later pieces of a split (or a freeze) were scaled to the whole
            # canvas -- stretched -- whenever the source's shape differed from the canvas's.
            sw, sh = inp["size"] or sizes.get(idx) or (w, h)
            # A crop keeps a sub-rectangle of the source, which then fills the canvas, so
            # feed _contain the cropped dimensions. Crop happens before scale.
            crop = inp.get("crop")
            if crop:
                cw = max(2, int(round(sw * crop["w"])) // 2 * 2)
                ch = max(2, int(round(sh * crop["h"])) // 2 * 2)
                cx = max(0, int(round(sw * crop["x"])) // 2 * 2)
                cy = max(0, int(round(sh * crop["y"])) // 2 * 2)
                crop_filter = f"crop={cw}:{ch}:{cx}:{cy},"
                sw, sh = cw, ch
            else:
                crop_filter = ""
            dw, dh, x, y = _contain(sw, sh, w, h)
            # The primary grade (grade.py): on the clip's own pixels, right after the scale and
            # before transform/pad, so a lift never lifts the letterbox. Same formula the
            # preview shows.
            gchain = _G.ffmpeg_chain(inp.get("grade"), Path(plan.get("cache") or ".") / "luts")
            grade_filter = f"{gchain}," if gchain else ""
            # Transform acts on the contained frame before it meets the canvas: scale
            # multiplies it, rotate turns it, and x/y pan it by a fraction of the canvas.
            # The frame is padded onto a layer at least canvas-sized (so a zoom-out leaves
            # black), shifted by the transform offset, then a canvas-sized window is cropped
            # from the centre -- which gives zoom-in (crop) and pan for free.
            tf = inp.get("transform")
            kfs = inp.get("keyframes")
            if kfs:
                # Animated transform: zoompan evaluates its zoom/x/y expressions on every
                # output frame, so a piecewise-linear expression over the keyframes animates
                # the move. `on` is the output frame number; the clip's keyframe times are
                # already seconds from the clip start, and the segment is rebased to zero, so
                # `on/fps` is that same clock. Values before the first / after the last
                # keyframe hold the endpoint (clamped), which is how a Ken Burns push reads.
                xf = _zoompan(kfs, w, h, fps, dur)
            elif tf:
                tscale = tf["scale"]
                tw = max(2, int(round(dw * tscale)) // 2 * 2)
                th = max(2, int(round(dh * tscale)) // 2 * 2)
                rot = f":c=black:ow={tw}:oh={th}" if abs(tf["rotate"]) > 1e-9 else ""
                rot_filter = f",rotate={tf['rotate']:.4f}{rot}" if rot else ""
                # The picture is scaled, padded onto a layer three canvases wide/tall, and a
                # canvas-sized window is cropped from it. Panning moves the crop window (so
                # x>0 reveals what was further right -- pan right), and zoom is the scaled
                # size of the picture: bigger than the canvas crops in, smaller letterboxes.
                # The window is clamped to the layer, so a pan past the picture's edge just
                # meets black rather than wrapping.
                pad_w, pad_h = w * 3, h * 3
                px = (pad_w - tw) // 2
                py = (pad_h - th) // 2
                cx = max(0, min(pad_w - w, (pad_w - w) // 2 + int(round(tf["x"] * w))))
                cy = max(0, min(pad_h - h, (pad_h - h) // 2 + int(round(tf["y"] * h))))
                xf = f"scale={tw}:{th}:flags=bicubic{rot_filter},pad={pad_w}:{pad_h}:{px}:{py}:black,crop={w}:{h}:{cx}:{cy},"
            else:
                xf = ""
            # Re-base the trimmed segment to zero, then rescale by 1/speed so it plays
            # faster (shorter output) or slower (longer). fps= re-timestamps to the canvas
            # rate. At speed 1 the expression is a no-op, which keeps the normal path exact.
            if inp.get("speed_keys"):
                # A speed ramp: setpts carries the exact integral of 1/speed, then fps re-timestamps.
                # The expression has commas (nested if), so it is quoted inside the filter option.
                pts = f"'{_ramp_pts(inp['speed_keys'])}'"
            else:
                pts = f"(PTS-STARTPTS)/{speed:.6f}" if abs(speed - 1.0) > 1e-9 else "PTS-STARTPTS"
            # Video fades to/from black sit after setpts so their start times are on the
            # final (speed-adjusted) timeline. fade_in opens from black; fade_out closes to
            # it, starting dur-fo seconds in so it lands exactly on the clip's last frame.
            vfade = ""
            fi_v, fo_v = inp.get("fade_in") or 0, inp.get("fade_out") or 0
            if fi_v:
                vfade += f",fade=t=in:st=0:d={_t2s(fi_v, rate):.3f}"
            if fo_v:
                vfade += f",fade=t=out:st={max(0.0, dur - _t2s(fo_v, rate)):.3f}:d={_t2s(fo_v, rate):.3f}"
            pad = f"pad={w}:{h}:{x}:{y}:black," if not tf else ""
            if inp.get("hold"):
                # A freeze frame: pick exactly the one source frame (a half-frame window either
                # side of its time, so rounding can't take two or none), clone it out to the
                # hold, then cut to the hold's length.
                fr = 1.0 / (fps if fps > 0 else 30.0)
                chain = (f"{crop_filter}scale={dw}:{dh}:flags=bicubic,{grade_filter}{xf}{pad}setpts=PTS-STARTPTS,"
                         f"tpad=stop_mode=clone:stop_duration={dur + fr:.6f},fps={fps:.3f},trim=duration={dur:.6f}"
                         f"{vfade},setsar=1,format=yuv420p")
                fc.append(f"[{src}]trim=start={max(0.0, s_in - fr / 2):.6f}:end={s_in + fr / 2:.6f},{chain}[v{n}]")
            else:
                # setsar=1 on every piece: scaling a 9:16 phone shot to whole pixels leaves it SAR
                # 1215:1216, a 16:9 shot stays 1:1, and concat refuses to join the two -- any cut
                # mixing vertical and horizontal footage failed to render. The canvas is square.
                chain = f"{crop_filter}scale={dw}:{dh}:flags=bicubic,{grade_filter}{xf}{pad}setpts={pts},fps={fps:.3f}{vfade},setsar=1,format=yuv420p"
                fc.append(f"[{src}]trim=start={s_in:.3f}:end={s_in + src_dur:.3f},{chain}[v{n}]")
        elif kind == "gap":
            dur = _t2s(inp["end"] - inp["at"], rate)
            v_in.append(f"[v{n}]")
            seg_ids.append(None)
            seg_durs.append(dur)
            fc.append(f"[{inp['idx']}:v]trim=start=0:end={dur:.3f},setpts=PTS-STARTPTS,fps={fps:.3f},setsar=1,format=yuv420p[v{n}]")

    fc.extend(_assemble_video(v_in, seg_ids, seg_durs, plan["transitions"], rate))

    # Sound: each item is placed at its own time, then padded to the full length so
    # amix sees streams of equal size and a gap stays a gap.
    a_ready: list[tuple[str, str, float]] = []  # (label, role, clip volume)
    for n, row in enumerate(plan["audio"]):
        idx = row["idx"]
        i0, o1 = row["src"]
        s_in = _t2s(i0, rate)
        dur = _t2s(o1 - i0, rate)
        delay_ms = int(round(_t2s(row["at"], rate) * 1000))
        fade = ""
        fi, fo = row["fade_in"], row["fade_out"]
        if fi:
            fade += f",afade=t=in:st=0:d={_t2s(fi, rate):.3f}"
        if fo:
            fade += f",afade=t=out:st={max(0.0, dur - _t2s(fo, rate)):.3f}:d={_t2s(fo, rate):.3f}"
        # The clip's own volume is an absolute gain applied per stream, so it survives the
        # mix's role-weight normalisation (folding it into the weight would cancel out for a
        # single-track mix, and a relative share is the wrong model for a level anyway).
        vol = float(row.get("volume") or 1.0)
        vol_filter = f",volume={vol:.4f}" if abs(vol - 1.0) > 1e-6 else ""
        # The clip's volume envelope (rubber band) rides on top of its volume. After asetpts the
        # stream's t is clip-local seconds, which is what the keys are in. eval=frame re-reads
        # the expression every audio frame (1024 samples, ~21 ms), fine for a level ramp.
        if row.get("gain_keys"):
            vol_filter += f",volume=eval=frame:volume='{_interp_expr(row['gain_keys'], 'gain', 't')}'"
        # Ducking rides under the clip's own level, on the TIMELINE clock: the stream is padded
        # and delayed to the cut's start before this runs, so its t is timeline seconds.
        if row.get("duck"):
            vol_filter += "," + _duck_expr(row["duck"])
        # Balance last, so a dip never also swings the sound sideways. A mono file is upmixed
        # first: it has no right channel to hold back.
        pan = float(row.get("pan") or 0.0)
        if abs(pan) > 1e-6:
            if _audio_channels(str(row.get("path") or "")) < 2:
                vol_filter += ",aformat=channel_layouts=stereo"
            vol_filter += "," + _pan_filter(pan)
        lab = f"au{n}"
        k = cut_a.get(idx, 0)
        cut_a[idx] = k + 1
        asrc = f"sa{idx}_{k}" if a_uses.get(idx, 0) > 1 else f"{idx}:a"
        # Retime: one atrim+atempo per segment on the SOURCE clock, then concat, so a ramp plays
        # with the same time map as its picture (see _audio_segments). A single unretimed segment
        # keeps the old one-filter path, which is exact and cheaper.
        segs = _audio_segments(row, rate)
        if len(segs) == 1:
            _, _, at = segs[0]
            chain = f"[{asrc}]atrim=start={s_in:.3f}:end={s_in + dur:.3f},asetpts=PTS-STARTPTS"
            if at:
                chain += f",{at}"
            fc.append(
                f"{chain}{fade}{vol_filter},aresample=48000,adelay=delays={delay_ms}:all=1,"
                f"apad=whole_dur={total:.3f}[{lab}]"
            )
        else:
            parts = []
            for si, (a_t, b_t, at) in enumerate(segs):
                out = f"{lab}s{si}"
                fc.append(
                    f"[{asrc}]atrim=start={s_in + a_t:.3f}:end={s_in + b_t:.3f},asetpts=PTS-STARTPTS"
                    f"{',' + at if at else ''}[{out}]"
                )
                parts.append(f"[{out}]")
            joined = "".join(parts)
            fc.append(
                f"{joined}concat=n={len(segs)}:v=0:a=1,asetpts=PTS-STARTPTS"
                f"{fade}{vol_filter},aresample=48000,adelay=delays={delay_ms}:all=1,"
                f"apad=whole_dur={total:.3f}[{lab}]"
            )
        a_ready.append((lab, row["role"], 1.0))

    if not a_ready:
        fc.append(f"anullsrc=r=48000:cl=stereo:d={total:.3f}[outa]")
    else:
        # Role weight sets the balance between voice and music; a clip's own volume was
        # already applied as an absolute gain per stream above. The weights are absolute
        # (voice 1.0, music 0.35). They used to be divided by their sum over EVERY stream, and
        # clips on a track rarely overlap, so each split made the whole cut 6 dB quieter
        # once loudnorm stood aside (one clip -23.2 dB, two -29.2, four -35.3). The limiter
        # below catches the rare case where voice and music peaks stack past full scale.
        weights = [MIX.get(role, 1.0) for _lab, role, _vol in a_ready]
        wstr = " ".join(f"{wgt:.4f}" for wgt in weights)
        # loudnorm is a broadcast auto-leveler that pulls the whole mix to -14 LUFS; it would
        # erase any level the user set by hand. So only auto-level when every clip is at its
        # default volume -- otherwise the authored mix is respected, with a limiter to keep
        # peaks safe.
        # An authored mix is anything the mixer decided, not just a clip's volume: a track
        # gain, a balance or a ducking dip all count. loudnorm re-levels the whole cut to
        # -14 LUFS, which would pull a ducked bed straight back up under the voice and undo the
        # mixer's work -- so it stands aside for all of them.
        hand_set = any(abs(float(r.get("volume") or 1.0) - 1.0) > 1e-6 or r.get("gain_keys") or r.get("duck")
                       or abs(float(r.get("pan") or 0.0)) > 1e-6 for r in plan["audio"])
        tail = "alimiter=limit=0.95,aresample=48000" if hand_set else "alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000"
        fc.append(
            "".join(f"[{lab}]" for lab, _role, _vol in a_ready)
            + f"amix=inputs={len(a_ready)}:duration=first:normalize=0:weights='{wstr}',"
            + tail
            + f",atrim=duration={total:.3f},asetpts=PTS-STARTPTS[outa]"
        )

    vout = "outv"
    if ass is not None:
        fc.append(f"[outv]ass='{_ass_escape_path(ass)}'[outv2]")
        vout = "outv2"
    # Titles over everything: each PNG is its own looped input (see _encode), faded in alpha
    # (linear, as the preview) and slid with the overlay position expression (titles.py).
    from hermes_studio import titles as _TT

    base_idx = len(plan["inputs"])
    for k, ti in enumerate(plan.get("titles") or []):
        at, dur = _t2s(ti["at"], rate), _t2s(ti["dur"], rate)
        fi, fo = min(_t2s(ti["fi"], rate), dur), min(_t2s(ti["fo"], rate), dur)
        chain = f"[{base_idx + k}:v]format=rgba"
        if fi > 0 and ti["in"] != "none":
            chain += f",fade=t=in:st=0:d={fi:.6f}:alpha=1"
        if fo > 0 and ti["out"] != "none":
            chain += f",fade=t=out:st={max(0.0, dur - fo):.6f}:d={fo:.6f}:alpha=1"
        chain += f",setpts=PTS-STARTPTS+{at:.6f}/TB[tt{k}]"
        fc.append(chain)
        xe, ye = _TT.motion_expr(ti["in"] if fi > 0 else "none", ti["out"] if fo > 0 else "none", at, dur, fi, fo, w, h)
        fc.append(f"[{vout}][tt{k}]overlay=x='{xe}':y='{ye}':eval=frame:eof_action=pass:format=auto,format=yuv420p[tv{k}]")
        vout = f"tv{k}"

    return ";".join(fc), vout


def _encode(plan: dict, graph: str, vout: str, out_path: Path, *, aout: str = "outa", seconds: float | None = None) -> list[str]:
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-nostdin"]
    for inp in plan["inputs"]:
        kind = inp["role"]
        if kind == "clip":
            cmd += ["-i", str(inp["path"])]
        elif kind == "sound":
            cmd += ["-i", str(inp["path"])]
        elif kind == "gap":
            cmd += ["-f", "lavfi", "-i", f"color=c=black:s={plan['width']}x{plan['height']}:r={plan['fps']:.3f}"]
    for ti in plan.get("titles") or []:
        # One still, looped for the title's length at the cut's frame rate.
        cmd += ["-loop", "1", "-framerate", f"{plan['fps']:.3f}", "-t", f"{_t2s(ti['dur'], plan['rate']):.6f}", "-i", str(ti["png"])]
    cmd += [
        "-filter_complex",
        graph,
        "-map",
        f"[{vout}]",
        "-map",
        f"[{aout}]",
        "-t",
        f"{seconds if seconds is not None else _t2s(plan['end_tick'], plan['rate']):.3f}",
        "-r",
        f"{plan['fps']:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    return cmd


def _range(plan: dict, start: float | None, end: float | None) -> tuple[float, float] | None:
    """An In/Out range in timeline seconds, checked against the cut. None = the whole cut."""
    if start is None and end is None:
        return None
    total = _t2s(plan["end_tick"], plan["rate"])
    s = 0.0 if start is None else float(start)
    e = total if end is None else float(end)
    if not (s == s and e == e) or s < 0 or e > total + 1e-6 or e - s < 1.0 / max(plan["fps"], 1.0):
        raise RenderError(f"the range must sit inside the cut (0 to {total:.3f}s) and last at least a frame")
    return s, min(e, total)


def render_project(pid: str, out_path: Path | None = None, *, start: float | None = None, end: float | None = None) -> dict:
    """Render a project to a file. The file lands in the project folder by default.

    ``start``/``end`` (timeline seconds, the page's In and Out marks) render only that range.
    The trim is the very last step -- after captions, the mix, the limiter and loudnorm -- so a
    range is frame-for-frame and level-for-level the same as that stretch of a full render,
    rather than a section levelled on its own.
    """
    from hermes_studio import editor as E

    folder = E._dir(pid)
    if not (folder / "base.json").exists():
        raise EditorError("no such project")
    plan = _build_plan(E._log(folder).doc, folder)
    rng = _range(plan, start, end)
    if shutil.which("ffmpeg") is None:
        raise RenderError("ffmpeg is not installed")
    ass = _build_ass(plan, folder / "cache")
    graph, vout = _build_graph(plan, ass)
    aout, seconds = "outa", None
    if rng:
        s, e = rng
        graph += (
            f";[{vout}]trim=start={s:.6f}:end={e:.6f},setpts=PTS-STARTPTS[rngv]"
            f";[outa]atrim=start={s:.6f}:end={e:.6f},asetpts=PTS-STARTPTS[rnga]"
        )
        vout, aout, seconds = "rngv", "rnga", e - s
    dest = out_path or (folder / f"{pid}-render.mp4")
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(_encode(plan, graph, vout, dest, aout=aout, seconds=seconds))
    if not dest.is_file() or dest.stat().st_size < 1024:
        raise RenderError("the render produced no file")
    return {
        "ok": True,
        "path": str(dest),
        "name": dest.name,
        "size": [plan["width"], plan["height"]],
        "duration": round(seconds if seconds is not None else _t2s(plan["end_tick"], plan["rate"]), 3),
        "range": [round(rng[0], 3), round(rng[1], 3)] if rng else None,
        "bytes": dest.stat().st_size,
        "captions": bool(ass),
        # What the mix came out at, measured on the exported file (M4's readout).
        "loudness": _loudness(dest),
    }


TARGET_LUFS = -14.0  # the delivery target for web and social (YouTube, Spotify, Reels)
TARGET_TOL = 1.0     # how far either side of it still counts as on target


def _loudness(path: Path) -> dict | None:
    """Measure the export's loudness (EBU R128 / ffmpeg ebur128) and report it back with the
    render, so the level is a fact you can read rather than something to take on trust.

    ``lufs`` is the integrated loudness over the whole file, ``peak`` its true peak in dBTP.
    Both come from ebur128's summary block, which it prints when it has seen the end of the
    stream -- so the file is measured to null output, twice over is not needed.

    Returns None when ffmpeg can't measure it (no sound stream, a truncated file): a render
    must not fail because its loudness couldn't be read.
    """
    try:
        r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-filter_complex", "ebur128=peak=true",
                            "-f", "null", "-"], capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        return None
    tail = r.stderr[-3000:]
    lufs = peak = None
    for line in tail.splitlines():
        if "I:" in line and "LUFS" in line:
            #   Integrated loudness:    I:         -14.2 LUFS
            try:
                lufs = float(line.split("I:")[1].split("LUFS")[0].strip())
            except (IndexError, ValueError):
                pass
        elif "Peak:" in line and "dBFS" in line:
            try:
                peak = float(line.split("Peak:")[1].split("dBFS")[0].strip())
            except (IndexError, ValueError):
                pass
    if lufs is None and peak is None:
        return None
    out = {"lufs": lufs, "peak": peak}
    if lufs is not None:
        out["on_target"] = abs(lufs - TARGET_LUFS) <= TARGET_TOL
        out["target"] = TARGET_LUFS
    return out


__all__ = ["RenderError", "render_project", "MIX", "TARGET_LUFS"]


# ---------------------------------------------------------------------------
# S6 render pipeline: the engine's render jobs (render_jobs.py, behind the MCP
# render_timeline tool and the engine HTTP API) use it. render_project above is the
# renderer the desk's Edit page uses. This one renders a doc with a chosen size,
# transcript words and a caption style, in windows for long cuts. The two share no
# helpers: the S6 ones carry an _s6_ prefix where a name would otherwise collide.

SEGMENT_OVER = 40
CRF = 18  # final renders: visually lossless (C11 SSIM >= 0.98 against the source)
Progress = Callable[[float], None]


def _s(ticks: int | Fraction) -> str:
    return f"{float(Fraction(ticks) / T.TICK_RATE):.6f}"


def _props(it: dict) -> dict:
    return {**T.DEFAULT_PROPS, **(it.get("props") or {})}


def _s6_speed(it: dict) -> Fraction:
    return Fraction(*_props(it)["speed"])


def _ratio(v: Any) -> Fraction:
    return Fraction(*v) if isinstance(v, list) else Fraction(v)


def timeline_end(doc: dict) -> int:
    return max((e for _, e in T.resolve(doc).values()), default=0)


def _s6_has_audio(path: str, cache: dict[str, bool]) -> bool:
    if path not in cache:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        cache[path] = bool(p.stdout.strip())
    return cache[path]


def _has_video(path: str, cache: dict[str, bool]) -> bool:
    key = "v:" + path
    if key not in cache:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        cache[key] = bool(p.stdout.strip())
    return cache[key]


# --------------------------------------------------------------------------- ASS for text + captions


def _ass_time(ticks: int) -> str:
    cs = max(0, int(Fraction(ticks, T.TICK_RATE) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _ass_text(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def build_ass(doc: dict, w: int, h: int, a: int, b: int, words: list[dict] | None) -> str:
    """Text items (lower third, by style) and caption words (bottom) for the window [a, b)."""
    spans = T.resolve(doc)
    big = max(10, h // 14)
    small = max(10, h // 22)
    out = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {w}",
        f"PlayResY: {h}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: text,DejaVu Sans,{big},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,{max(2, big // 12)},0,5,"
        f"{w // 12},{w // 12},0,1",
        f"Style: impact,DejaVu Sans,{int(big * 1.25)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,"
        f"{max(3, big // 8)},0,5,{w // 12},{w // 12},0,1",
        f"Style: cap,DejaVu Sans,{small},&H00FFFFFF,&H0000E5FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,{max(2, small // 10)},0,2,"
        f"{w // 10},{w // 10},{h // 9},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for tr in doc["tracks"]:
        if tr["role"] != "text":
            continue
        for it in tr["items"]:
            s, e = spans[it["id"]]
            if e <= a or s >= b:
                continue
            fi = int(Fraction(it.get("fade_in", 0), T.TICK_RATE) * 1000)
            fo = int(Fraction(it.get("fade_out", 0), T.TICK_RATE) * 1000)
            fad = f"{{\\fad({fi},{fo})\\pos({w // 2},{int(h * 0.72)})}}"
            style = "impact" if it["style"] == "impact" else "text"
            out.append(
                f"Dialogue: 1,{_ass_time(max(s, a) - a)},{_ass_time(min(e, b) - a)},{style},,0,0,0,,{fad}{_ass_text(it['text'])}"
            )
    return "\n".join(out) + "\n"


def caption_ass(words: list[dict], w: int, h: int, a: int, b: int, style: str) -> str | None:
    """The clip pipeline's own word-by-word captions (``captions.build_ass``) for the window
    [a, b): the same look as Hermes clips. None when no word falls in the window."""
    from hermes_studio.captions import build_ass as clip_ass
    from hermes_studio.transcribe import Word

    local = [
        Word(wd["w"], float(Fraction(max(wd["at"], a) - a, T.TICK_RATE)), float(Fraction(min(wd["end"], b) - a, T.TICK_RATE)))
        for wd in words
        if wd["end"] > a and wd["at"] < b and wd["end"] > wd["at"]
    ]
    if not local:
        return None
    return clip_ass(local, 0.0, float(Fraction(b - a, T.TICK_RATE)), play_x=w, play_y=h, style=style, layout="fit")


# --------------------------------------------------------------------------- the graph


def plan(
    doc: dict,
    project_dir: Path,
    a: int,
    b: int,
    size: tuple[int, int],
    words: list[dict] | None,
    work: Path,
    caption_style: str = "pop",
) -> dict:
    """The two FFmpeg passes for the window [a, b) of ``doc``: ``video`` and ``audio``, each
    ``(input args, filter_complex)``, plus ``info``. Audio is its own pass: one graph pulling
    video and audio from the same seeked inputs at different rates can stall FFmpeg."""
    w, h = size
    fps = Fraction(*doc["fps"])
    spans = T.resolve(doc)
    by_id = {it["id"]: it for tr in doc["tracks"] for it in tr["items"]}
    probe: dict[str, bool] = {}
    inputs: list[str] = []
    ainputs: list[str] = []

    def src_of(mid: str) -> str:
        return doc["media"][mid]["path"]

    def inp(into: list[str], path: str, start: int, length: int) -> int:
        """One input per clip, seeked to its source range: decoders never wait on each other."""
        into.extend(["-ss", _s(start), "-t", _s(length), "-i", path])
        return into.count("-i") - 1

    # transitions: incoming clip id -> overlap ticks; outgoing clip id -> overlap ticks
    fade_alpha_in: dict[str, int] = {}
    fade_audio_out: dict[str, int] = {}
    for tr in doc["tracks"]:
        for it in tr["items"]:
            if it["type"] == "transition":
                out_id, in_id = it["between"]
                fade_alpha_in[in_id] = it["dur"]
                fade_audio_out[out_id] = it["dur"]

    dur = b - a
    graph: list[str] = [f"color=c=black:s={w}x{h}:r={fps.numerator}/{fps.denominator}:d={_s(dur)},format=yuv420p[base]"]
    last = "base"
    audio_labels: list[str] = []
    agraph: list[str] = []
    n_video = 0
    for tr in doc["tracks"]:
        for it in tr["items"]:
            if it["type"] != "clip":
                continue
            s, e = spans[it["id"]]
            if e <= a or s >= b:
                continue
            path = src_of(it["media"])
            sp = _s6_speed(it)
            src_in, src_out = it["src"]
            lo, hi = max(s, a) - s, min(e, b) - s  # the window's part, in clip-local timeline ticks
            place = max(s, a) - a
            fi, fo = it.get("fade_in", 0), it.get("fade_out", 0)
            props = _props(it)
            if tr["id"] == T.MAIN_TRACK and _has_video(path, probe):
                n_video += 1
                k = inp(inputs, path, src_in, src_out - src_in)
                f = [f"[{k}:v]trim=duration={_s(src_out - src_in)}", "setpts=PTS-STARTPTS"]
                if sp != 1:
                    f.append(f"setpts=PTS/{float(sp):.6f}")
                f.append(f"fps={fps.numerator}/{fps.denominator}")
                crop = props["crop"]
                if isinstance(crop, dict):
                    x, y, cw, ch = (_ratio(crop[q]) for q in "xywh")
                    f.append(f"crop=iw*{float(cw):.6f}:ih*{float(ch):.6f}:iw*{float(x):.6f}:ih*{float(y):.6f}")
                f += [f"scale={w}:{h}:force_original_aspect_ratio=increase", f"crop={w}:{h}", "setsar=1", "format=yuva420p"]
                clip_len = e - s
                if fi:
                    f.append(f"fade=t=in:st=0:d={_s(fi)}")
                if fo:
                    f.append(f"fade=t=out:st={_s(clip_len - fo)}:d={_s(fo)}")
                if it["id"] in fade_alpha_in:
                    f.append(f"fade=t=in:st=0:d={_s(fade_alpha_in[it['id']])}:alpha=1")
                f += [f"trim=start={_s(lo)}:end={_s(hi)}", f"setpts=PTS-STARTPTS+{_s(place)}/TB"]
                lab = f"v{n_video}"
                graph.append(",".join(f) + f"[{lab}]")
                graph.append(f"[{last}][{lab}]overlay=eof_action=pass:format=auto[o{n_video}]")
                last = f"o{n_video}"
            if _s6_has_audio(path, probe) and _ratio(props["volume"]) > 0:
                k = inp(ainputs, path, src_in, src_out - src_in)
                af = [f"[{k}:a]atrim=duration={_s(src_out - src_in)}", "asetpts=PTS-STARTPTS"]
                rest = sp
                while rest > 2:
                    af.append("atempo=2")
                    rest /= 2
                while rest < Fraction(1, 2):
                    af.append("atempo=0.5")
                    rest *= 2
                if rest != 1:
                    af.append(f"atempo={float(rest):.6f}")
                af += ["aformat=sample_rates=48000:channel_layouts=stereo"]
                vol = _ratio(props["volume"])
                if vol != 1:
                    af.append(f"volume={float(vol):.6f}")
                clip_len = e - s
                if fi:
                    af.append(f"afade=t=in:st=0:d={_s(fi)}")
                if fo:
                    af.append(f"afade=t=out:st={_s(clip_len - fo)}:d={_s(fo)}")
                if it["id"] in fade_alpha_in:
                    af.append(f"afade=t=in:st=0:d={_s(fade_alpha_in[it['id']])}")
                if it["id"] in fade_audio_out:
                    d = fade_audio_out[it["id"]]
                    af.append(f"afade=t=out:st={_s(clip_len - d)}:d={_s(d)}")
                af += [f"atrim=start={_s(lo)}:end={_s(hi)}", "asetpts=PTS-STARTPTS"]
                ms = int(Fraction(place, T.TICK_RATE) * 1000)
                if ms:
                    af.append(f"adelay={ms}:all=1")
                lab = f"a{len(audio_labels) + 1}"
                agraph.append(",".join(af) + f"[{lab}]")
                audio_labels.append(lab)

    def sub(name: str, text: str) -> str:
        f = work / name
        f.write_text(text, encoding="utf-8")
        arg = str(f).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        return f"subtitles=filename='{arg}'"

    subs = [sub("overlay.ass", build_ass(doc, w, h, a, b, None))]
    caps = caption_ass(words, w, h, a, b, caption_style) if words else None
    if caps:
        subs.append(sub("captions.ass", caps))
    graph.append(f"[{last}]{','.join(subs)},trim=duration={_s(dur)},format=yuv420p[outv]")
    if audio_labels:
        mix = "".join(f"[{x}]" for x in audio_labels)
        agraph.append(f"{mix}amix=inputs={len(audio_labels)}:normalize=0:dropout_transition=0,apad,atrim=duration={_s(dur)}[ca]")
    else:
        agraph.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={_s(dur)}[ca]")
    _ = by_id
    return {
        "video": (inputs, ";".join(graph)),
        "audio": (ainputs, ";".join(agraph)),
        "info": {"clips": n_video, "audio_streams": len(audio_labels), "duration": dur},
    }


def _s6_encode(passes: dict, fps: Fraction, out: Path, dur: int, on_progress: Progress | None, cancel: Callable[[], bool]) -> None:
    """Audio pass to a WAV next to ``out`` (about 5% of the bar), then the video pass muxing it."""
    wav = out.with_name(f".{out.stem}.audio.wav")
    ain, agraph = passes["audio"]
    _ffmpeg(
        [*ain, "-filter_complex", agraph, "-map", "[ca]", "-c:a", "pcm_s16le", "-ar", "48000", "-t", _s(dur), str(wav)],
        dur,
        (lambda f: on_progress(0.05 * f)) if on_progress else None,
        cancel,
    )
    vin, vgraph = passes["video"]
    n = vin.count("-i")
    try:
        _ffmpeg(
            [
                *vin,
                "-i",
                str(wav),
                "-filter_complex",
                vgraph,
                "-map",
                "[outv]",
                "-map",
                f"{n}:a",
                "-r",
                f"{fps.numerator}/{fps.denominator}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                str(CRF),
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-ar",
                "48000",
                "-t",
                _s(dur),
                "-movflags",
                "+faststart",
                "-f",
                "mp4",
                str(out),
            ],
            dur,
            (lambda f: on_progress(0.05 + 0.95 * f)) if on_progress else None,
            cancel,
        )
    finally:
        wav.unlink(missing_ok=True)


def _ffmpeg(args: list[str], dur: int, on_progress: Progress | None, cancel: Callable[[], bool]) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-nostats", "-loglevel", "error", "-progress", "pipe:1", "-y", *args]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    total = max(1, dur * 1_000_000 // T.TICK_RATE)
    try:
        assert p.stdout is not None
        for line in p.stdout:
            if cancel():
                p.kill()
                break
            k, _, v = line.strip().partition("=")
            if k == "out_time_us" and v.isdigit() and on_progress:
                on_progress(min(1.0, int(v) / total))
        p.wait()
        err = p.stderr.read() if p.stderr else ""
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
        for s in (p.stdout, p.stderr):
            if s:
                s.close()
    if cancel():
        raise RuntimeError("render cancelled")
    if p.returncode != 0:
        raise RuntimeError(err.strip()[-1500:] or f"ffmpeg exit {p.returncode}")


def windows(doc: dict, every: int = SEGMENT_OVER) -> list[tuple[int, int]]:
    """Cut points for a long timeline: V1 clip starts, every ``every`` clips, never inside a
    transition (or an anchored item's span, which is drawn whole by its window)."""
    end = timeline_end(doc)
    spans = T.resolve(doc)
    main = next((tr for tr in doc["tracks"] if tr["id"] == T.MAIN_TRACK), {"items": []})
    clips = sorted(spans[it["id"]][0] for it in main["items"] if it["type"] == "clip")
    if len(clips) <= every:
        return [(0, end)]
    busy = [spans[it["id"]] for tr in doc["tracks"] for it in tr["items"] if it["type"] == "transition"]
    cuts = [0]
    for i in range(every, len(clips), every):
        t = clips[i]
        if t > cuts[-1] and not any(s < t < e for s, e in busy):
            cuts.append(t)
    cuts.append(end)
    return [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1) if cuts[i + 1] > cuts[i]]


def render(
    doc: dict,
    project_dir: Path,
    out: Path,
    *,
    size: tuple[int, int] | None = None,
    words: list[dict] | None = None,
    caption_style: str = "pop",
    on_progress: Progress | None = None,
    cancel: Callable[[], bool] = lambda: False,
    segment_over: int = SEGMENT_OVER,
) -> dict:
    """Render a valid doc to ``out`` (mp4). Returns ``{path, duration, segments, clips}``."""
    size = size or tuple(doc["size"])
    if size[0] % 2 or size[1] % 2:
        raise ValueError("width and height must be even")
    end = timeline_end(doc)
    if end <= 0:
        raise ValueError("the timeline is empty")
    fps = Fraction(*doc["fps"])
    work = out.parent / f".{out.stem}.work"
    work.mkdir(parents=True, exist_ok=True)
    wins = windows(doc, segment_over)
    done = 0
    parts: list[Path] = []
    clips = 0
    try:
        for i, (a, b) in enumerate(wins):
            seg_dir = work / f"seg{i:04d}"
            seg_dir.mkdir(exist_ok=True)
            target = out if len(wins) == 1 else seg_dir / "part.mp4"
            tmp = target.with_name(f".{target.stem}.tmp.mp4")
            passes = plan(doc, project_dir, a, b, size, words, seg_dir, caption_style)
            clips += passes["info"]["clips"]

            def prog(f: float, a=a, b=b, done=done) -> None:
                if on_progress:
                    on_progress(min(1.0, (done + f * (b - a)) / end))

            _s6_encode(passes, fps, tmp, b - a, prog, cancel)
            os.replace(tmp, target)
            parts.append(target)
            done += b - a
        if len(wins) > 1:
            lst = work / "parts.txt"
            lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
            tmp = out.with_name(f".{out.stem}.tmp.mp4")
            p = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(lst),
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(tmp),
                ],
                capture_output=True,
                text=True,
            )
            if p.returncode != 0:
                raise RuntimeError(p.stderr.strip()[-1500:] or "concat failed")
            os.replace(tmp, out)
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)
    if on_progress:
        on_progress(1.0)
    return {"path": str(out), "duration": end, "segments": len(wins), "clips": clips}
