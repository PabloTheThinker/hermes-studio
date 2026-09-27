"""Where the face goes. Pure math: no OpenCV, no ffmpeg, fully unit-testable.

Rules, from vertical-video framing guides, the YouTube Shorts / TikTok safe zones and
Google AutoFlip (research notes in docs/FRAMING.md):

1. Eye line on the upper third of the output, not the face centred at 50%.
2. Headroom: never cut the top of the head; never leave a sky of empty space.
3. Lead room: a head turned to one side gets more space on that side.
4. Safe zone: Shorts put buttons down the right edge (~96 of 1080 px) and the title
   block at the bottom (~300 of 1920 px). The subject sits a touch left of centre and
   well above the bottom block.
5. Size: a talking head reads best when the face is roughly a fifth of the frame
   height. Wide shots get a gentle zoom, capped so we never upscale into mush.
6. Camera: a still subject gets a still camera. Only real movement gets a smooth pan,
   and a jump between two people is a hard cut, never a whip pan across the room.
"""

from __future__ import annotations

from dataclasses import dataclass

# Composition targets, as shares of the OUTPUT frame.
EYE_LINE = 0.36          # eyes 36% from the top: upper third, clear of the top UI strip
SAFE_CX = 0.47           # horizontal home, nudged left of the Shorts button rail
LEAD = 0.07              # extra room toward where the head is turned, at full yaw
FACE_SHARE = 0.20        # face height as a share of output height, for a talking head
MAX_UPSCALE = 2.2        # never enlarge source pixels more than this
HEADROOM = 0.35          # keep at least this many face-heights above the face box

# Camera behaviour.
STILL_SPREAD = 0.06      # face moves less than 6% of frame width -> locked camera
CUT_JUMP = 0.22          # jump bigger than 22% of frame width between samples -> hard cut
MAX_PAN_SPEED = 0.18     # pan at most 18% of source width per second


@dataclass(frozen=True)
class Crop:
    """Crop window in source pixels (ffmpeg order: w, h, x, y)."""

    w: int
    h: int
    x: int
    y: int

    def ffmpeg(self) -> str:
        return f"crop={self.w}:{self.h}:{self.x}:{self.y}"


def _even(v: float) -> int:
    return max(2, int(v) // 2 * 2)


def _off(v: float) -> int:
    return max(0, int(v) // 2 * 2)


def crop_size(src_w: int, src_h: int, out_w: int, out_h: int, face_h: float | None = None) -> tuple[int, int]:
    """Crop size with the output aspect. Zooms in on small faces, within the upscale cap."""
    aspect = out_w / out_h
    ch = float(src_h)
    if face_h and face_h > 0:
        want = face_h * src_h / FACE_SHARE
        floor = max(out_h / MAX_UPSCALE, src_h * 0.5)
        ch = min(float(src_h), max(want, floor))
    cw = ch * aspect
    if cw > src_w:
        cw = float(src_w)
        ch = cw / aspect
    return _even(cw), _even(ch)


def place(
    src_w: int, src_h: int, cw: int, ch: int,
    cx: float, eye_y: float, face_y: float, face_h: float, yaw: float = 0.0,
) -> tuple[int, int]:
    """Top-left (x, y) of a cw x ch crop so the face follows the composition rules.

    cx, eye_y, face_y, face_h are 0-1 of the source frame.
    """
    # Horizontal: face at the safe home. Lead room: a head turned screen-left sits right
    # of home, so the empty space is in front of the face, not behind it.
    home = SAFE_CX - max(-1.0, min(1.0, yaw)) * LEAD
    x = cx * src_w - home * cw
    # Vertical: eye line on the upper third ...
    y = eye_y * src_h - EYE_LINE * ch
    # ... but never cut the top of the head.
    head_top = (face_y - face_h * HEADROOM) * src_h
    y = min(y, head_top) if head_top >= 0 else 0
    x = min(max(x, 0), src_w - cw)
    y = min(max(y, 0), src_h - ch)
    return _off(x), _off(y)


def still_crop(src_w: int, src_h: int, out_w: int, out_h: int, face) -> Crop:
    """One locked crop for the whole clip. face: hermesclip.face.Face (median) or None."""
    if face is None:
        cw, ch = crop_size(src_w, src_h, out_w, out_h)
        return Crop(cw, ch, _off((src_w - cw) / 2), _off((src_h - ch) / 2))
    cw, ch = crop_size(src_w, src_h, out_w, out_h, face.h)
    x, y = place(src_w, src_h, cw, ch, face.cx, face.eye_y, face.y, face.h, face.yaw)
    return Crop(cw, ch, x, y)


@dataclass(frozen=True)
class CropPath:
    """A crop whose x moves over time. keys: [(t_out_seconds, x_px)], sorted."""

    crop: Crop
    keys: tuple[tuple[float, int], ...]

    def x_expr(self) -> str:
        """ffmpeg expression for crop x over output time t (piecewise linear / steps)."""
        if len(self.keys) < 2:
            return str(self.crop.x)
        expr = str(self.keys[-1][1])
        for (t0, x0), (t1, x1) in reversed(list(zip(self.keys, self.keys[1:], strict=False))):
            if t1 - t0 < 1e-3:  # hard cut: step
                seg = str(x1)
            else:
                seg = f"{x0}+({x1 - x0})*(t-{t0:.3f})/{t1 - t0:.3f}"
            expr = f"if(lt(t\\,{t1:.3f})\\,{seg}\\,{expr})"
        return expr

    def ffmpeg(self) -> str:
        c = self.crop
        return f"crop={c.w}:{c.h}:x='{self.x_expr()}':y={c.y}"


def camera(src_w: int, src_h: int, out_w: int, out_h: int, track, to_out=None) -> Crop | CropPath:
    """Pick a locked crop or a smooth path from a FaceTrack.

    to_out: maps seconds-from-clip-start to output seconds (tight cuts shorten the clip).
    """
    face = track.median() if track else None
    base = still_crop(src_w, src_h, out_w, out_h, face)
    if face is None or len(track.faces) < 3 or track.spread_x() < STILL_SPREAD:
        return base
    fmap = to_out or (lambda t: t)
    keys: list[tuple[float, int]] = []
    for f in track.faces:
        x, _y = place(src_w, src_h, base.w, base.h, f.cx, face.eye_y, face.y, face.h, f.yaw)
        t = round(fmap(f.t), 3)
        if keys:
            pt, px = keys[-1]
            if abs(x - px) > CUT_JUMP * src_w:
                # A different person or a big move: cut, halfway between samples.
                mid = round((pt + t) / 2, 3)
                keys += [(mid, px), (mid, x)]
                keys.append((t, x))
                continue
            # Smooth pan with a speed cap.
            dt = max(t - pt, 1e-3)
            cap = MAX_PAN_SPEED * src_w * dt
            x = int(px + max(-cap, min(cap, x - px)))
        keys.append((t, _off(x)))
    # Hold the first and last position to the clip edges.
    keys = [(0.0, keys[0][1])] + keys + [(keys[-1][0] + 3600.0, keys[-1][1])]
    return CropPath(base, tuple(keys))


def band_crop(src_w: int, src_h: int, band_w: int, band_h: int, face, facecam: bool) -> Crop:
    """Face band for the split layout.

    Facecam (small corner cam): show the whole cam tile tightly, eyes ~40% down.
    Speaker in frame: head and shoulders, eyes ~38% down, same headroom rule.
    """
    aspect = band_w / band_h
    if face is None:
        ch = src_h * 0.45
    elif facecam:
        ch = face.h * src_h * 1.6
    else:
        ch = face.h * src_h * 2.4
    ch = min(float(src_h), max(ch, 64.0))
    cw = ch * aspect
    if cw > src_w:
        cw = float(src_w)
        ch = cw / aspect
    cw, ch = _even(cw), _even(ch)
    if face is None:
        return Crop(cw, ch, _off((src_w - cw) / 2), _off(src_h * 0.3 - ch / 2))
    x = face.cx * src_w - cw / 2
    y = face.eye_y * src_h - (0.40 if facecam else 0.38) * ch
    head_top = (face.y - face.h * 0.25) * src_h
    y = min(y, head_top) if head_top >= 0 else 0
    x = min(max(x, 0), src_w - cw)
    y = min(max(y, 0), src_h - ch)
    return Crop(cw, ch, _off(x), _off(y))


def is_facecam(face) -> bool:
    """A small face parked off-centre (usually a corner) over other content."""
    return face.w < 0.16 and (face.cx < 0.34 or face.cx > 0.66 or face.cy > 0.7)


def _fit_in_box(aspect: float, src_w: int, src_h: int, box: tuple) -> Crop:
    """Largest crop of the given aspect inside a manual camera box (0-1 x, y, w, h)."""
    bx, by, bw, bh = (box[0] * src_w, box[1] * src_h, box[2] * src_w, box[3] * src_h)
    ch = min(bh, bw / aspect)
    cw = ch * aspect
    cw, ch = _even(cw), _even(ch)
    x = min(max(bx + (bw - cw) / 2, 0), src_w - cw)
    y = min(max(by + (bh - ch) / 2, 0), src_h - ch)
    return Crop(cw, ch, _off(x), _off(y))


def split_geometry(src_w: int, src_h: int, out_w: int, out_h: int, look, face) -> dict:
    """Split layout: a locked face band and a locked content band, stacked.

    look: hermesclip.look.Look (face top/bottom, band ratio, optional manual box).
    face: median Face or None. Returns face_h, body_h and a Crop for each band.
    """
    face_h = _even(out_h * look.face_ratio)
    body_h = out_h - face_h
    if look.face_box:
        fcrop = _fit_in_box(out_w / face_h, src_w, src_h, look.face_box)
    else:
        fcrop = band_crop(src_w, src_h, out_w, face_h, face, facecam=bool(face and is_facecam(face)))
    # Content band: full height, centred, nudged away from the camera corner.
    aspect = out_w / body_h
    cw = min(float(src_w), src_h * aspect)
    ch = cw / aspect
    cw, ch = _even(cw), _even(ch)
    cx = src_w / 2
    cam_x = None
    if look.face_box:
        cam_x = (look.face_box[0] + look.face_box[2] / 2) * src_w
    elif face is not None and is_facecam(face):
        cam_x = face.cx * src_w
    if cam_x is not None and cw < src_w:
        cx += (-1 if cam_x > src_w / 2 else 1) * min((src_w - cw) / 2, src_w * 0.12)
    x = min(max(cx - cw / 2, 0), src_w - cw)
    y = min(max((src_h - ch) / 2, 0), src_h - ch)
    return {"face_h": face_h, "body_h": body_h, "face": fcrop, "body": Crop(cw, ch, _off(x), _off(y))}
