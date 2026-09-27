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
    face: tuple[float, float] | None = None,
    look=None,
    box: tuple | None = None,
    clip_dur: float = 0.0,
) -> str:
    """Filter graph from [vin] to [vout].

    layout: fit (letterbox on blur) | fill (crop, pinned on the face) | split (face band + content band).
    look (hermesclip.look.Look): face top/bottom, band size, colour filter, progress bar.
    Order: frame -> colour filter -> progress bar -> captions, so caption colours stay true.
    """
    from hermesclip.look import Look, post_chain, split_geometry

    lk = look or Look(layout=layout)
    post = post_chain(lk, clip_dur, out_h)
    tail = (post + "," if post else "") + f"setsar=1,subtitles='{ass_f}'[{vout}]"
    scale = "flags=lanczos"
    if layout == "split":
        g = split_geometry(src_w, src_h, out_w, out_h, lk, box)
        fw, fh, fx, fy = g["face"]
        bw, bh, bx, by = g["body"]
        top, bottom = ("fc", "bc") if lk.face == "top" else ("bc", "fc")
        return (
            f"[{vin}]split=2[fi][bi];"
            f"[fi]crop={fw}:{fh}:{fx}:{fy},scale={out_w}:{g['face_h']}:{scale},setsar=1[fc];"
            f"[bi]crop={bw}:{bh}:{bx}:{by},scale={out_w}:{g['body_h']}:{scale},setsar=1[bc];"
            f"[{top}][{bottom}]vstack=inputs=2,{tail}"
        )
    if layout == "fill":
        crop = f"crop={out_w}:{out_h}"
        if face:
            from hermesclip.face import fill_crop_xy

            x, y = fill_crop_xy(src_w, src_h, out_w, out_h, face[0], face[1])
            crop = f"crop={out_w}:{out_h}:{x}:{y}"
        return (
            f"[{vin}]scale={out_w}:{out_h}:force_original_aspect_ratio=increase:{scale},"
            f"{crop},{tail}"
        )
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
