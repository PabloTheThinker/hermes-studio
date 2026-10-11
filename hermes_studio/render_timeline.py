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

from hermes_studio import grade as _G

import shutil
import subprocess
from pathlib import Path
from typing import Any

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


def _volume(it: dict) -> float:
    """The clip's playback volume (props.volume) as a float."""
    return _level((it.get("props") or {}).get("volume"))


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
        # The source window is read at `speed`; a clip played faster than 1x covers fewer
        # ticks on the timeline than the source range it spans, and slower covers more.
        tl_dur = int(round((o1 - i0) / speed))
        if tl_dur <= 0:
            raise RenderError("a clip has no length")
        rel = str(media.get(it.get("media") or "", {}).get("path") or "")
        if not rel:
            raise RenderError("a clip has no picture")
        path = resolve_media(folder, rel)
        if not path.is_file():
            raise RenderError(f"picture file is missing: {path.name}")
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
        clip_extra = {"crop": crop, "look": look, "grade": grade, "fade_in": fi, "fade_out": fo, "transform": transform, "keyframes": keyframes}
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
            end_tick = max(end_tick, it["at"] + (o1 - i0))
            if not audible:
                continue
            path = resolve_media(folder, rel)
            if not path.is_file():
                raise RenderError(f"sound file is missing: {path.name}")
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
                    "gain_keys": _gain_keys(it, rate),
                }
            )

    captions = []
    for it in items("text"):
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
        "transitions": transitions,
        "end_tick": end_tick,
        "silent": not any(True for _ in audio),
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
            fc.append(f"{acc}{segs[i]}xfade=transition=fade:duration={dur:.3f}:offset={offset:.3f}[{out}]")
            running = running + seg_durs[i] - dur
        else:
            fc.append(f"{acc}{segs[i]}concat=n=2:v=1:a=0[{out}]")
            running = running + seg_durs[i]
        acc = f"[{out}]"
    return fc


def _build_graph(plan: dict, ass: Path | None) -> tuple[str, str]:
    """The filter graph, and the label to map as the output video."""
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
            dur = src_dur / speed
            v_in.append(f"[v{n}]")
            seg_ids.append(inp.get("id"))
            seg_durs.append(dur)
            sw, sh = inp["size"] or (w, h)
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
            gchain = _G.ffmpeg_chain(inp.get("grade"))
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
            chain = f"{crop_filter}scale={dw}:{dh}:flags=bicubic,{grade_filter}{xf}{pad}setpts={pts},fps={fps:.3f}{vfade},format=yuv420p"
            fc.append(f"[{src}]trim=start={s_in:.3f}:end={s_in + src_dur:.3f},{chain}[v{n}]")
        elif kind == "gap":
            dur = _t2s(inp["end"] - inp["at"], rate)
            v_in.append(f"[v{n}]")
            seg_ids.append(None)
            seg_durs.append(dur)
            fc.append(f"[{inp['idx']}:v]trim=start=0:end={dur:.3f},setpts=PTS-STARTPTS,fps={fps:.3f},format=yuv420p[v{n}]")

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
        lab = f"au{n}"
        k = cut_a.get(idx, 0)
        cut_a[idx] = k + 1
        asrc = f"sa{idx}_{k}" if a_uses.get(idx, 0) > 1 else f"{idx}:a"
        fc.append(
            f"[{asrc}]atrim=start={s_in:.3f}:end={s_in + dur:.3f},asetpts=PTS-STARTPTS"
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
        hand_set = any(abs(float(r.get("volume") or 1.0) - 1.0) > 1e-6 or r.get("gain_keys") for r in plan["audio"])
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
    }


__all__ = ["RenderError", "render_project", "MIX"]
