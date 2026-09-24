"""9:16 framing. BridgeClip Classic (fit) and Full Frame (fill), no OpenRouter."""

from __future__ import annotations

import subprocess
from pathlib import Path


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
) -> str:
    """Filter graph from [vin] to [vout]. layout: fit | fill."""
    scale = "flags=lanczos"
    if layout == "fill":
        return (
            f"[{vin}]scale={out_w}:{out_h}:force_original_aspect_ratio=increase:{scale},"
            f"crop={out_w}:{out_h},setsar=1,subtitles='{ass_f}'[{vout}]"
        )
    scaled_h, _y = letterbox_geometry(src_w, src_h, out_w, out_h)
    bg_w, bg_h = even(out_w // 4), even(out_h // 4)
    return (
        f"[{vin}]split=2[bi][fi];"
        f"[bi]scale={bg_w}:{bg_h}:force_original_aspect_ratio=increase,"
        f"crop={bg_w}:{bg_h},gblur=sigma=10,lutyuv=y=val-20,"
        f"scale={out_w}:{out_h}[bg];"
        f"[fi]scale={out_w}:{scaled_h}:{scale}[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,subtitles='{ass_f}'[{vout}]"
    )
