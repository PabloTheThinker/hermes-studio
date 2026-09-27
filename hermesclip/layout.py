"""Framing. Fit and Fill after BridgeClip (MIT, see NOTICE); Split (face band + content band) is Hermes Studio's own."""

from __future__ import annotations

import subprocess
from pathlib import Path

ASPECTS = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
    "4:5": (1080, 1350),
}


def canvas(aspect: str) -> tuple[int, int]:
    return ASPECTS.get(aspect, ASPECTS["9:16"])


def even(value: float) -> int:
    return max(2, int(value) // 2 * 2)


def probe_size(video: Path) -> tuple[int, int]:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(video),
        ],
        text=True,
    ).strip()
    w, h = out.split(",")
    return int(w), int(h)


def letterbox_geometry(src_w: int, src_h: int, out_w: int, out_h: int) -> tuple[int, int]:
    """Scaled height and Y offset for the original plate on a 9:16 canvas."""
    scaled_h = min(out_h, even(out_w * src_h / src_w + 1))
    return scaled_h, (out_h - scaled_h) // 2


def frame_filters(
    src_w: int,
    src_h: int,
    out_w: int,
    out_h: int,
    layout: str,
    ass_f: str,
    vin: str = "vin",
    vout: str = "outv",
    look=None,
    track=None,
    clip_dur: float = 0.0,
    to_out=None,
) -> str:
    """Filter graph from [vin] to [vout].

    layout: fit (whole frame on blur) | fill (crop framed on the eyes, locked or smooth pan)
            | split (face band + content band).
    track: hermesclip.face.FaceTrack for the clip (may be empty).
    to_out: clip seconds -> output seconds, for camera keys after tight cuts.
    Order: frame -> colour filter -> progress bar -> captions, so caption colours stay true.
    """
    from hermesclip.framing import camera, split_geometry
    from hermesclip.look import Look, post_chain

    lk = look or Look(layout=layout)
    post = post_chain(lk, clip_dur, out_h)
    tail = (post + "," if post else "") + f"setsar=1,subtitles='{ass_f}'[{vout}]"
    scale = "flags=lanczos"
    if layout == "split":
        face = track.median() if track else None
        g = split_geometry(src_w, src_h, out_w, out_h, lk, face)
        top, bottom = ("fc", "bc") if lk.face == "top" else ("bc", "fc")
        return (
            f"[{vin}]split=2[fi][bi];"
            f"[fi]{g['face'].ffmpeg()},scale={out_w}:{g['face_h']}:{scale},setsar=1[fc];"
            f"[bi]{g['body'].ffmpeg()},scale={out_w}:{g['body_h']}:{scale},setsar=1[bc];"
            f"[{top}][{bottom}]vstack=inputs=2,{tail}"
        )
    if layout == "fill":
        cam = camera(src_w, src_h, out_w, out_h, track, to_out)
        return f"[{vin}]{cam.ffmpeg()},scale={out_w}:{out_h}:{scale},{tail}"
    scaled_h, _y = letterbox_geometry(src_w, src_h, out_w, out_h)
    bg_w, bg_h = even(out_w // 4), even(out_h // 4)
    return (
        f"[{vin}]split=2[bi][fi];"
        f"[bi]scale={bg_w}:{bg_h}:force_original_aspect_ratio=increase,"
        f"crop={bg_w}:{bg_h},gblur=sigma=10,lutyuv=y=val-20,"
        f"scale={out_w}:{out_h}[bg];"
        f"[fi]scale={out_w}:{scaled_h}:{scale}[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{tail}"
    )
