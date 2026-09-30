"""The look of a clip: framing, face position, colour filter, caption spot, audio, progress bar.

Research basis (2026):
- Opus Clip layouts: Fill (speaker crop), Fit (letterbox), Split, Screenshare (screen top,
  speaker bottom), Gameplay (30% speaker top / 70% gameplay below).
- Streamer tools (Boltis, Clip Farm): facecam on top, gameplay below, both locked; split
  ratio 20-80%, never a drifting per-frame tracker.
- Platform safe zones: keep the bottom ~15% and the right rail clear (TikTok/Reels/Shorts UI).
- Loudness: short-form platforms normalise near -14 LUFS.

All local FFmpeg. Nothing here posts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

LAYOUTS = ("auto", "fit", "fill", "split")
FACE_POS = ("top", "bottom")
CAPTION_POS = ("auto", "top", "middle", "bottom")
AUDIO = ("off", "clean")

# Colour looks. Applied after framing, before captions, so caption colours stay true.
FILTERS: dict[str, str] = {
    "none": "",
    "punch": "eq=contrast=1.10:saturation=1.28:brightness=0.01,unsharp=5:5:0.5",
    "warm": "colorbalance=rs=0.06:gs=0.02:bs=-0.06:rm=0.03:bm=-0.03,eq=saturation=1.08",
    "cool": "colorbalance=rs=-0.05:bs=0.07:rm=-0.02:bm=0.04,eq=saturation=1.04",
    "cinematic": "curves=preset=medium_contrast,colorbalance=rs=-0.03:bs=0.05:rh=0.05:bh=-0.04,eq=saturation=0.92,vignette=PI/5",
    "vintage": "curves=preset=vintage,eq=saturation=0.85",
    "bw": "hue=s=0,eq=contrast=1.15",
    "bright": "eq=brightness=0.04:gamma=1.08:saturation=1.05",
}
FILTER_NAMES = {
    "none": "None", "punch": "Punch", "warm": "Warm", "cool": "Cool",
    "cinematic": "Cinematic", "vintage": "Vintage", "bw": "Black & white", "bright": "Bright",
}

AUDIO_CLEAN = "highpass=f=80,afftdn=nf=-25,loudnorm=I=-14:TP=-1.5:LRA=11"
PROGRESS_COLOR = "0xFFC83D"  # Hermes amber


@dataclass
class Look:
    layout: str = "fit"          # auto | fit | fill | split
    face: str = "top"            # split: face band on top or bottom
    face_ratio: float = 0.35     # split: share of height for the face band (0.2-0.6)
    face_box: tuple | None = None  # optional manual camera box (x, y, w, h) 0-1 of the source
    filter: str = "none"
    caption_pos: str = "auto"    # auto | top | middle | bottom
    audio: str = "off"           # off | clean
    progress: bool = False       # thin amber progress bar at the bottom

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["face_box"] is not None:
            d["face_box"] = list(d["face_box"])
        return d


def make_look(data: dict | None = None, **over) -> Look:
    """Validate loosely: unknown values fall back to defaults instead of failing a render."""
    d = dict(data or {})
    d.update({k: v for k, v in over.items() if v is not None})
    lk = Look()
    if str(d.get("layout", "")).lower() in LAYOUTS:
        lk.layout = str(d["layout"]).lower()
    if str(d.get("face", "")).lower() in FACE_POS:
        lk.face = str(d["face"]).lower()
    try:
        r = float(d.get("face_ratio", lk.face_ratio))
        if r > 1:
            r = r / 100.0
        lk.face_ratio = min(0.6, max(0.2, r))
    except (TypeError, ValueError):
        pass
    fb = d.get("face_box")
    if isinstance(fb, str) and fb.strip():
        try:
            fb = [float(x) for x in fb.replace(";", ",").split(",")]
        except ValueError:
            fb = None
    if isinstance(fb, (list, tuple)) and len(fb) == 4:
        try:
            x, y, w, h = (float(v) for v in fb)
            if max(x, y, w, h) > 1.0:  # percents
                x, y, w, h = x / 100, y / 100, w / 100, h / 100
            if w > 0.02 and h > 0.02:
                lk.face_box = (max(0.0, x), max(0.0, y), min(1.0, w), min(1.0, h))
        except (TypeError, ValueError):
            pass
    f = str(d.get("filter", "")).lower().replace(" ", "").replace("&", "").replace("blackwhite", "bw")
    if f in FILTERS:
        lk.filter = f
    if str(d.get("caption_pos", "")).lower() in CAPTION_POS:
        lk.caption_pos = str(d["caption_pos"]).lower()
    if str(d.get("audio", "")).lower() in AUDIO:
        lk.audio = str(d["audio"]).lower()
    elif d.get("audio") is True:
        lk.audio = "clean"
    if "progress" in d:
        lk.progress = str(d["progress"]).lower() in ("1", "true", "yes", "on")
    return lk


def choose_layout(face, src_w: int, src_h: int, out_w: int, out_h: int) -> tuple[str, str]:
    """Auto layout, Opus-style: pick from what is on screen. Returns (layout, reason).

    face: hermes_studio.face.Face (the clip's median subject) or None.
    - Source already as tall as the canvas: fill.
    - No face: fit (letterbox on blur, nothing is cut off).
    - Small face parked off-centre (streamer facecam over game or screen): split.
    - Otherwise a talking head: fill, framed on the eyes.
    """
    from hermes_studio.framing import is_facecam

    if src_w * out_h <= src_h * out_w * 1.05:
        return "fill", "source is already tall"
    if face is None:
        return "fit", "no face found"
    if is_facecam(face):
        return "split", "facecam in a corner"
    return "fill", "speaker in frame"


def post_chain(look: Look, clip_dur: float, out_h: int, out_w: int = 1080) -> str:
    """Filter + progress bar, applied after framing and before captions.

    Returns a fragment that continues a filter chain and ends mid-chain, so callers can
    append ``,next_filter``. The bar is an amber strip slid in from the left with
    ``overlay`` (its x is re-evaluated per frame). Do not use ``drawbox`` for this:
    in drawbox ``t`` is the box *thickness*, not time, so a ``w='iw*t/dur'`` bar is
    drawn full width from the first frame.
    """
    parts: list[str] = []
    f = FILTERS.get(look.filter, "")
    if f:
        parts.append(f)
    if look.progress and clip_dur > 0:
        bar = max(6, int(out_h * 0.005) // 2 * 2)
        parts.append(
            f"null[hcpm];color=c={PROGRESS_COLOR}:s={out_w}x{bar}:r=30[hcpb];"
            f"[hcpm][hcpb]overlay=x='-w+w*min(t/{clip_dur:.3f}\\,1)':y=H-h:eval=frame:shortest=1"
        )
    return ",".join(parts)


def caption_margin(look: Look, layout: str, out_h: int, font_size: int, seam_y: int | None = None) -> tuple[int, int]:
    """(ASS alignment, MarginV) for captions. Keeps clear of the bottom ~15% platform UI."""
    pos = look.caption_pos
    if pos == "auto":
        if layout == "split" and seam_y:
            # On the seam between face and content: reads with both.
            return 2, max(40, out_h - seam_y - font_size // 2)
        if layout == "fill":
            return 2, int(out_h * 0.2)
        return 2, int(out_h * 0.16)
    if pos == "top":
        return 8, int(out_h * 0.16)
    if pos == "middle":
        return 5, 0
    return 2, int(out_h * 0.16)
