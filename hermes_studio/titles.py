"""Titles: designed text on the timeline (Editor 1.0, M3).

A title is a text item with a ``title`` object: a template, its words, an accent colour, how it
comes in and goes out, and the design layers those make. The layers are drawn by the Design
page's own renderer (design._draw_text / _draw_shape, the house fonts) into ONE transparent PNG
the size of the canvas. The render overlays that PNG; the preview shows the very same PNG. So
the still title is the same pixels in both, by construction, and only the motion is computed --
by one formula, written twice (here as an ffmpeg expression, in the page as JS).

Motion: the item's fade_in / fade_out are the in and out durations. Opacity is linear over each
(ffmpeg's fade); a slide moves by a fraction of the canvas, eased with 1 - (1 - p)^3.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from hermes_studio import design as D

TEMPLATES = ("lower-third", "title", "end-card")
ANIMS = ("none", "fade", "slide-up", "slide-left")
SLIDE = 0.06  # slide distance as a fraction of the canvas (height for up, width for left)
AMBER = "#ffc83d"
INK = "#f2efe8"
MAX_TEXT = 200
VERSION = 1  # bump when the drawing changes, so cached PNGs are redrawn


def _hex(c: str | None, default: str) -> str:
    c = str(c or "").strip()
    return c if D.COLOR_RE.match(c) else default


FONT_IDS = tuple(D.FONTS)
BOX_DEFAULT = {"lower-third": True, "title": False, "end-card": True}
POS_LIM = 0.5  # a title may move half the canvas either way
SCALE_MIN, SCALE_MAX = 0.5, 2.0
# Where each template scales from (fractions of the canvas): its own corner or centre, so a
# bigger lower third grows from where it sits, not from the middle of the frame.
_ANCHOR = {"lower-third": (0.06, 0.70), "title": (0.5, 0.5), "end-card": (0.5, 0.42)}


def layers_for(template: str, w: int, h: int, text: str, sub: str, accent: str, font: str = "archivo",
               box: bool | None = None) -> list[dict]:
    """The design layers a template makes on a w x h canvas. Type sizes scale by the short side,
    so a lower third on a 9:16 phone cut is as readable as on 16:9. ``font`` is the main line's
    face; ``box`` the dark panel behind the words (lower third band, title box, end-card wash)."""
    box = BOX_DEFAULT[template] if box is None else bool(box)
    u = min(w, h)
    text = (text or "").strip() or " "
    sub = (sub or "").strip()
    if template == "lower-third":
        m = round(w * 0.06)
        size, ssize = round(u * 0.058), round(u * 0.034)
        y = round(h * 0.70)
        width = round(w * 0.62)
        out = [
            {"type": "rect", "x": m, "y": y - round(u * 0.012), "w": round(u * 0.012), "h": round(size * 1.15 + (ssize * 1.4 if sub else 0) + u * 0.024), "fill": accent},
            {"type": "text", "text": text, "x": m + round(u * 0.03), "y": y, "w": width, "size": size, "weight": 800, "color": INK, "line": 1.1,
             "font": font, **({} if box else {"effect": {"kind": "shadow", "offset": 4, "opacity": 0.8}})},
        ]
        if sub:
            out.append({"type": "text", "text": sub, "x": m + round(u * 0.03), "y": y + round(size * 1.2), "w": width, "size": ssize,
                        "weight": 500, "color": accent, "font": "mono", "line": 1.2})
        # A soft dark band behind the words so they read on any picture.
        if box:
            band_h = round(size * 1.15 + (ssize * 1.4 if sub else 0) + u * 0.06)
            out.insert(0, {"type": "rect", "x": 0, "y": y - round(u * 0.03), "w": round(w * 0.72), "h": band_h, "fill": "#000000a0"})
        return out
    if template == "end-card":
        size, ssize = round(u * 0.09), round(u * 0.04)
        out = [
            {"type": "rect", "x": 0, "y": 0, "w": w, "h": h, "fill": "#0b0b0ce6"},
            {"type": "text", "text": text, "x": round(w * 0.1), "y": round(h * 0.42 - size * 0.6), "w": round(w * 0.8), "size": size,
             "weight": 800, "color": INK, "align": "center", "line": 1.05, "font": font},
            {"type": "rect", "x": round(w / 2 - u * 0.06), "y": round(h * 0.42 + size * 0.75), "w": round(u * 0.12), "h": max(2, round(u * 0.006)), "fill": accent},
        ]
        if sub:
            out.append({"type": "text", "text": sub, "x": round(w * 0.1), "y": round(h * 0.42 + size * 0.95), "w": round(w * 0.8), "size": ssize,
                        "weight": 500, "color": accent, "font": "mono", "align": "center", "line": 1.2})
        if not box:
            out = out[1:]
            for lay in out:
                if lay["type"] == "text":
                    lay["effect"] = {"kind": "shadow", "offset": 4, "opacity": 0.8}
        return out
    # "title": centred, on the picture.
    size, ssize = round(u * 0.1), round(u * 0.042)
    out = [{"type": "text", "text": text, "x": round(w * 0.08), "y": round(h * 0.5 - size * 0.7), "w": round(w * 0.84), "size": size,
            "weight": 800, "color": INK, "align": "center", "line": 1.05, "effect": {"kind": "shadow"}, "font": font}]
    if sub:
        out.append({"type": "text", "text": sub, "x": round(w * 0.08), "y": round(h * 0.5 + size * 0.55), "w": round(w * 0.84), "size": ssize,
                    "weight": 600, "color": accent, "align": "center", "line": 1.2, "effect": {"kind": "shadow", "offset": 4, "opacity": 0.8}})
    if box:
        # A dark panel across the words' column, tall enough for both lines.
        top = round(h * 0.5 - size * 0.95)
        bot = round(h * 0.5 + (size * 0.55 + ssize * 1.5 if sub else size * 0.6) + u * 0.02)
        out.insert(0, {"type": "rect", "x": round(w * 0.06), "y": top, "w": round(w * 0.88), "h": bot - top, "fill": "#000000a0"})
    return out


def _place(layers: list[dict], template: str, w: int, h: int, x: float, y: float, scale: float) -> list[dict]:
    """Scale the template about its anchor, then move it by (x, y) of the canvas. The whole
    layout scales together -- text box widths too -- so the words wrap exactly as before."""
    if x == 0 and y == 0 and scale == 1:
        return layers
    ax, ay = _ANCHOR[template][0] * w, _ANCHOR[template][1] * h
    for lay in layers:
        if lay["type"] == "rect" and (lay["x"], lay["y"], lay["w"], lay.get("h")) == (0, 0, w, h):
            continue  # the end card's wash stays the whole frame
        lay["x"] = round(ax + (lay["x"] - ax) * scale + x * w)
        lay["y"] = round(ay + (lay["y"] - ay) * scale + y * h)
        lay["w"] = max(1, round(lay["w"] * scale))
        if "h" in lay:
            lay["h"] = max(1, round(lay["h"] * scale))
        if "size" in lay:
            lay["size"] = max(6, round(lay["size"] * scale))
    return layers


def _clamp(v, lo: float, hi: float, nd: int) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError) as exc:
        raise ValueError("position and size are numbers") from exc
    if f != f:
        raise ValueError("position and size are numbers")
    return round(min(hi, max(lo, f)), nd)


def make(template: str, w: int, h: int, *, text: str, sub: str = "", accent: str | None = None,
         anim_in: str = "fade", anim_out: str = "fade", x: float = 0, y: float = 0, scale: float = 1,
         font: str = "archivo", box: bool | None = None) -> dict:
    """A complete, clean title object. x / y move it by a fraction of the canvas, scale sizes it
    about the template's anchor, font is the main line's face, box the panel behind it. Those
    five are stored only when they differ from the template's default, so a title made before
    they existed is still exactly what make() builds (and draws the same PNG)."""
    if template not in TEMPLATES:
        raise ValueError(f"template is one of {', '.join(TEMPLATES)}")
    if anim_in not in ANIMS or anim_out not in ANIMS:
        raise ValueError(f"animation is one of {', '.join(ANIMS)}")
    if font not in FONT_IDS:
        raise ValueError(f"font is one of {', '.join(FONT_IDS)}")
    text = " ".join(str(text or "").split())[:MAX_TEXT]
    sub = " ".join(str(sub or "").split())[:MAX_TEXT]
    accent = _hex(accent, AMBER)
    x, y = _clamp(x, -POS_LIM, POS_LIM, 4), _clamp(y, -POS_LIM, POS_LIM, 4)
    scale = _clamp(scale, SCALE_MIN, SCALE_MAX, 3)
    box = BOX_DEFAULT[template] if box is None else bool(box)
    raw = _place(layers_for(template, w, h, text, sub, accent, font, box), template, w, h, x, y, scale)
    layers = [lay for lay in (D.clean_layer(r, w, h) for r in raw) if lay]
    out = {"template": template, "text": text, "sub": sub, "accent": accent, "in": anim_in, "out": anim_out,
           "size": [w, h], "layers": layers}
    for k, v, dflt in (("x", x, 0), ("y", y, 0), ("scale", scale, 1), ("font", font, "archivo"), ("box", box, BOX_DEFAULT[template])):
        if v != dflt:
            out[k] = v
    return out


def fields(t: dict) -> dict:
    """The editable fields of a stored title, defaults filled in (make()'s keyword arguments)."""
    return {"text": t["text"], "sub": t.get("sub", ""), "accent": t.get("accent"), "anim_in": t.get("in", "fade"),
            "anim_out": t.get("out", "fade"), "x": t.get("x", 0), "y": t.get("y", 0), "scale": t.get("scale", 1),
            "font": t.get("font", "archivo"), "box": t.get("box", BOX_DEFAULT.get(t.get("template"), True))}


def problem(t) -> str | None:
    """Why a stored title is not valid, or None. A title must be exactly what ``make`` builds from
    its own fields, so the layers can't drift from the template (or carry unchecked values)."""
    if not isinstance(t, dict):
        return "title must be an object"
    try:
        w, h = t["size"]
        again = make(t["template"], int(w), int(h), **fields(t))
    except (KeyError, TypeError, ValueError) as exc:
        return f"bad title: {exc}"
    return None if again == t else "title layers don't match the template"


def key(t: dict) -> str:
    return hashlib.sha1(json.dumps({"v": VERSION, "size": t["size"], "layers": t["layers"]}, sort_keys=True).encode(), usedforsecurity=False).hexdigest()[:16]


def png(t: dict, cache: Path) -> Path:
    """The title drawn once into a transparent canvas-size PNG (cached by content)."""
    from PIL import Image

    out = cache / "titles" / f"{key(t)}.png"
    if out.is_file() and out.stat().st_size > 0:
        return out
    w, h = t["size"]
    base = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    for lay in t["layers"]:
        if lay["type"] == "text":
            D._draw_text(base, lay)
        elif lay["type"] in ("rect", "ellipse", "line"):
            D._draw_shape(base, lay)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.stem}.{hashlib.sha1(str(id(base)).encode(), usedforsecurity=False).hexdigest()[:6]}.tmp.png")
    base.save(tmp, "PNG")
    tmp.replace(out)
    return out


def motion_expr(kind_in: str, kind_out: str, at: float, dur: float, fi: float, fo: float, w: int, h: int) -> tuple[str, str]:
    """ffmpeg overlay x/y expressions (eval=frame, t = output seconds) for the slide part of the
    motion; opacity is done with fade. p rises 0 -> 1 over the in, falls 1 -> 0 over the out;
    the offset is SLIDE * (1 - e), e = 1 - (1 - p)^3."""
    def p_of(kind: str, which: str) -> str:
        if which == "in":
            return "1" if fi <= 0 or kind not in ("slide-up", "slide-left") else f"clip((t-{at:.6f})/{fi:.6f},0,1)"
        return "1" if fo <= 0 or kind not in ("slide-up", "slide-left") else f"clip(({at + dur:.6f}-t)/{fo:.6f},0,1)"

    def off(axis: str) -> str:
        parts = []
        for kind, which in ((kind_in, "in"), (kind_out, "out")):
            want = "slide-up" if axis == "y" else "slide-left"
            if kind == want:
                p = p_of(kind, which)
                dist = SLIDE * (h if axis == "y" else w)
                parts.append(f"{dist:.4f}*pow(1-({p}),3)")
        return "+".join(parts) if parts else "0"

    return off("x"), off("y")


__all__ = ["TEMPLATES", "ANIMS", "FONT_IDS", "fields", "make", "problem", "png", "key", "motion_expr", "SLIDE"]
