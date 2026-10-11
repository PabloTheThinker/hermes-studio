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


def layers_for(template: str, w: int, h: int, text: str, sub: str, accent: str) -> list[dict]:
    """The design layers a template makes on a w x h canvas. Type sizes scale by the short side,
    so a lower third on a 9:16 phone cut is as readable as on 16:9."""
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
            {"type": "text", "text": text, "x": m + round(u * 0.03), "y": y, "w": width, "size": size, "weight": 800, "color": INK, "line": 1.1},
        ]
        if sub:
            out.append({"type": "text", "text": sub, "x": m + round(u * 0.03), "y": y + round(size * 1.2), "w": width, "size": ssize,
                        "weight": 500, "color": accent, "font": "mono", "line": 1.2})
        # A soft dark band behind the words so they read on any picture.
        band_h = round(size * 1.15 + (ssize * 1.4 if sub else 0) + u * 0.06)
        out.insert(0, {"type": "rect", "x": 0, "y": y - round(u * 0.03), "w": round(w * 0.72), "h": band_h, "fill": "#000000a0"})
        return out
    if template == "end-card":
        size, ssize = round(u * 0.09), round(u * 0.04)
        out = [
            {"type": "rect", "x": 0, "y": 0, "w": w, "h": h, "fill": "#0b0b0ce6"},
            {"type": "text", "text": text, "x": round(w * 0.1), "y": round(h * 0.42 - size * 0.6), "w": round(w * 0.8), "size": size,
             "weight": 800, "color": INK, "align": "center", "line": 1.05},
            {"type": "rect", "x": round(w / 2 - u * 0.06), "y": round(h * 0.42 + size * 0.75), "w": round(u * 0.12), "h": max(2, round(u * 0.006)), "fill": accent},
        ]
        if sub:
            out.append({"type": "text", "text": sub, "x": round(w * 0.1), "y": round(h * 0.42 + size * 0.95), "w": round(w * 0.8), "size": ssize,
                        "weight": 500, "color": accent, "font": "mono", "align": "center", "line": 1.2})
        return out
    # "title": centred, on the picture.
    size, ssize = round(u * 0.1), round(u * 0.042)
    out = [{"type": "text", "text": text, "x": round(w * 0.08), "y": round(h * 0.5 - size * 0.7), "w": round(w * 0.84), "size": size,
            "weight": 800, "color": INK, "align": "center", "line": 1.05, "effect": {"kind": "shadow"}}]
    if sub:
        out.append({"type": "text", "text": sub, "x": round(w * 0.08), "y": round(h * 0.5 + size * 0.55), "w": round(w * 0.84), "size": ssize,
                    "weight": 600, "color": accent, "align": "center", "line": 1.2, "effect": {"kind": "shadow", "offset": 4, "opacity": 0.8}})
    return out


def make(template: str, w: int, h: int, *, text: str, sub: str = "", accent: str | None = None,
         anim_in: str = "fade", anim_out: str = "fade") -> dict:
    """A complete, clean title object."""
    if template not in TEMPLATES:
        raise ValueError(f"template is one of {', '.join(TEMPLATES)}")
    if anim_in not in ANIMS or anim_out not in ANIMS:
        raise ValueError(f"animation is one of {', '.join(ANIMS)}")
    text = " ".join(str(text or "").split())[:MAX_TEXT]
    sub = " ".join(str(sub or "").split())[:MAX_TEXT]
    accent = _hex(accent, AMBER)
    raw = layers_for(template, w, h, text, sub, accent)
    layers = [x for x in (D.clean_layer(lay, w, h) for lay in raw) if x]
    return {"template": template, "text": text, "sub": sub, "accent": accent, "in": anim_in, "out": anim_out,
            "size": [w, h], "layers": layers}


def problem(t) -> str | None:
    """Why a stored title is not valid, or None. A title must be exactly what ``make`` builds from
    its own fields, so the layers can't drift from the template (or carry unchecked values)."""
    if not isinstance(t, dict):
        return "title must be an object"
    try:
        w, h = t["size"]
        again = make(t["template"], int(w), int(h), text=t["text"], sub=t.get("sub", ""), accent=t.get("accent"),
                     anim_in=t.get("in", "fade"), anim_out=t.get("out", "fade"))
    except (KeyError, TypeError, ValueError) as exc:
        return f"bad title: {exc}"
    return None if again == t else "title layers don't match the template"


def key(t: dict) -> str:
    return hashlib.sha1(json.dumps({"v": VERSION, "size": t["size"], "layers": t["layers"]}, sort_keys=True).encode()).hexdigest()[:16]


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
    tmp = out.with_name(f".{out.stem}.{hashlib.sha1(str(id(base)).encode()).hexdigest()[:6]}.tmp.png")
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


__all__ = ["TEMPLATES", "ANIMS", "make", "problem", "png", "key", "motion_expr", "SLIDE"]
