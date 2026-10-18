"""Feathered rectangle/ellipse masks isolating a clip's grade or blur.

Preview (mask.js) and render (ffmpeg geq + maskedmerge) share :func:`matte_at` and
:func:`interp_keys`. Mask times are seconds from the clip's output start (same clock as
transform keyframes on a rebased segment).
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Any

SHAPES = frozenset({"rect", "ellipse"})
TARGETS = frozenset({"grade", "blur"})
MASK_KEYS = frozenset({"shape", "x", "y", "w", "h", "feather", "invert", "target", "blur", "keys"})
MASK_KEY_KEYS = frozenset({"at", "x", "y", "w", "h"})
# Centre offset from frame centre, as a fraction of the frame width/height.
POS_MIN, POS_MAX = Fraction(-1, 2), Fraction(1, 2)
SIZE_MIN, SIZE_MAX = Fraction(1, 100), Fraction(1)
FEATHER_MIN, FEATHER_MAX = Fraction(0), Fraction(1, 2)
BLUR_MIN, BLUR_MAX = Fraction(0), Fraction(500)

DEFAULT_SHAPE = "rect"
DEFAULT_TARGET = "grade"
DEFAULT_BLUR = 12.0


def frac(v: Any) -> float | None:
    if isinstance(v, (list, tuple)) and len(v) == 2:
        try:
            num, den = float(v[0]), float(v[1])
            return num / den if den else None
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


_frac = frac


def to_pair(v: float) -> list[int]:
    fr = Fraction(v).limit_denominator(1000)
    return [fr.numerator, fr.denominator]


def _pair(v: float) -> list[int]:
    return to_pair(v)


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 <= edge0:
        return 1.0 if x >= edge1 else 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def matte_at(
    shape: str,
    mx: float,
    my: float,
    w: float,
    h: float,
    feather: float,
    invert: bool,
    w_px: int,
    h_px: int,
    lx: float,
    ly: float,
) -> float:
    """Matte 0..1 at normalized pixel centre (lx, ly) in 0..1 frame coordinates."""
    if w <= 0 or h <= 0 or w_px <= 0 or h_px <= 0:
        return 0.0 if not invert else 1.0
    cx = 0.5 + mx
    cy = 0.5 + my
    px = lx * w_px
    py = ly * h_px
    cx_px = cx * w_px
    cy_px = cy * h_px
    hw_px = w * w_px * 0.5
    hh_px = h * h_px * 0.5
    f_px = max(0.0, feather) * min(w_px, h_px)
    if shape == "ellipse":
        if hw_px <= 1e-9 or hh_px <= 1e-9:
            d_px = 1e9
        else:
            rn = math.sqrt(((px - cx_px) / hw_px) ** 2 + ((py - cy_px) / hh_px) ** 2)
            d_px = (rn - 1.0) * min(hw_px, hh_px)
    else:
        d_px = max(abs(px - cx_px) - hw_px, abs(py - cy_px) - hh_px)
    if f_px <= 1e-9:
        m = 1.0 if d_px <= 0.0 else 0.0
    else:
        m = smoothstep(0.0, 1.0, max(0.0, min(1.0, (-d_px) / f_px)))
    if invert:
        m = 1.0 - m
    return m


def _interp_scalar(kfs: list[dict], key: str, t: float, base: float) -> float:
    if not kfs:
        return base
    from hermes_studio import easing as _EZ

    return _EZ.interp_scalar(kfs, key, t)


def resolve_at(mask: dict, t: float) -> tuple[float, float, float, float]:
    """x, y, w, h at output time ``t`` (seconds from clip start)."""
    bx = _frac(mask.get("x")) or 0.0
    by = _frac(mask.get("y")) or 0.0
    bw = _frac(mask.get("w")) or 0.5
    bh = _frac(mask.get("h")) or 0.5
    keys = mask.get("keys")
    if not isinstance(keys, list) or not keys:
        return bx, by, bw, bh
    kfs = []
    for k in keys:
        if not isinstance(k, dict):
            continue
        at = _frac(k.get("at"))
        if at is None:
            continue
        kfs.append({
            "at": at,
            "x": _frac(k.get("x")) if k.get("x") is not None else bx,
            "y": _frac(k.get("y")) if k.get("y") is not None else by,
            "w": _frac(k.get("w")) if k.get("w") is not None else bw,
            "h": _frac(k.get("h")) if k.get("h") is not None else bh,
        })
    kfs.sort(key=lambda k: k["at"])
    if not kfs:
        return bx, by, bw, bh
    return (
        _interp_scalar(kfs, "x", t, bx),
        _interp_scalar(kfs, "y", t, by),
        _interp_scalar(kfs, "w", t, bw),
        _interp_scalar(kfs, "h", t, bh),
    )


def parse(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    shape = str(raw.get("shape") or DEFAULT_SHAPE)
    if shape not in SHAPES:
        return None
    out: dict[str, Any] = {"shape": shape}
    for k in ("x", "y", "w", "h", "feather", "blur"):
        if k in raw and raw[k] is not None:
            v = _frac(raw[k])
            if v is None:
                return None
            out[k] = _pair(v)
    if raw.get("invert") is True:
        out["invert"] = True
    target = str(raw.get("target") or DEFAULT_TARGET)
    if target in TARGETS and target != DEFAULT_TARGET:
        out["target"] = target
    keys = raw.get("keys")
    if isinstance(keys, list) and keys:
        out["keys"] = keys
    return out


def store(
    *,
    shape: str = DEFAULT_SHAPE,
    x: float = 0.0,
    y: float = 0.0,
    w: float = 0.5,
    h: float = 1.0,
    feather: float = 0.0,
    invert: bool = False,
    target: str = DEFAULT_TARGET,
    blur: float = DEFAULT_BLUR,
    keys: list[dict] | None = None,
) -> dict:
    """Build a mask dict with defaults dropped (validator + hash rules)."""
    out: dict[str, Any] = {
        "x": _pair(x),
        "y": _pair(y),
        "w": _pair(w),
        "h": _pair(h),
    }
    if shape != DEFAULT_SHAPE:
        out["shape"] = shape
    if feather > 1e-9:
        out["feather"] = _pair(feather)
    if invert:
        out["invert"] = True
    if target != DEFAULT_TARGET:
        out["target"] = target
    if target == "blur" and blur != DEFAULT_BLUR:
        out["blur"] = _pair(blur)
    if keys:
        out["keys"] = keys
    return out


def view(mask: dict | None) -> dict | None:
    if not isinstance(mask, dict):
        return None
    out: dict[str, Any] = {
        "shape": str(mask.get("shape") or DEFAULT_SHAPE),
        "x": _frac(mask.get("x")) or 0.0,
        "y": _frac(mask.get("y")) or 0.0,
        "w": _frac(mask.get("w")) or 0.5,
        "h": _frac(mask.get("h")) or 1.0,
        "feather": _frac(mask.get("feather")) or 0.0,
        "invert": mask.get("invert") is True,
        "target": str(mask.get("target") or DEFAULT_TARGET),
        "blur": _frac(mask.get("blur")) or DEFAULT_BLUR,
    }
    keys = mask.get("keys")
    if isinstance(keys, list) and keys:
        out["keys"] = keys
    return out


def _ffmpeg_num(x: float) -> str:
    return f"{x:.8f}"


def _interp_expr(kfs: list[dict], key: str, tvar: str) -> str:
    """Piecewise eased ffmpeg expression (easing.py, same as transform keyframes)."""
    from hermes_studio import easing as _EZ

    return _EZ.interp_expr(kfs, key, tvar, eased=True)


def geq_lum_expr(mask: dict, w: int, h: int, rate: int, tvar: str = "T") -> str:
    """Gray matte 0..255 for ffmpeg geq, evaluated per frame (``tvar`` in seconds)."""
    shape = str(mask.get("shape") or DEFAULT_SHAPE)
    invert = mask.get("invert") is True
    feather = _frac(mask.get("feather")) or 0.0
    bx = _frac(mask.get("x")) or 0.0
    by = _frac(mask.get("y")) or 0.0
    bw = _frac(mask.get("w")) or 0.5
    bh = _frac(mask.get("h")) or 1.0
    keys = mask.get("keys")
    if isinstance(keys, list) and keys:
        kfs = []
        for k in keys:
            if not isinstance(k, dict) or not isinstance(k.get("at"), int):
                continue
            kfs.append({
                "at": k["at"] / rate,
                "x": _frac(k.get("x")) if k.get("x") is not None else bx,
                "y": _frac(k.get("y")) if k.get("y") is not None else by,
                "w": _frac(k.get("w")) if k.get("w") is not None else bw,
                "h": _frac(k.get("h")) if k.get("h") is not None else bh,
            })
        kfs.sort(key=lambda k: k["at"])
        if kfs:
            mx = _interp_expr(kfs, "x", tvar)
            my = _interp_expr(kfs, "y", tvar)
            mw = _interp_expr(kfs, "w", tvar)
            mh = _interp_expr(kfs, "h", tvar)
        else:
            mx, my, mw, mh = map(_ffmpeg_num, (bx, by, bw, bh))
    else:
        mx, my, mw, mh = map(_ffmpeg_num, (bx, by, bw, bh))

    wn, hn = _ffmpeg_num(float(w)), _ffmpeg_num(float(h))
    fp = _ffmpeg_num(feather * min(w, h))
    cx = f"(0.5+({mx}))"
    cy = f"(0.5+({my}))"
    lx = f"((X+0.5)/{wn})"
    ly = f"((Y+0.5)/{hn})"
    px = f"({lx}*{wn})"
    py = f"({ly}*{hn})"
    cxp = f"({cx}*{wn})"
    cyp = f"({cy}*{hn})"
    hwp = f"(({mw})*{wn}*0.5)"
    hhp = f"(({mh})*{hn}*0.5)"
    if shape == "ellipse":
        rn = f"sqrt(pow(({px})-({cxp}),2)/pow(({hwp}),2)+pow(({py})-({cyp}),2)/pow(({hhp}),2))"
        dpx = f"(({rn})-1)*min(({hwp}),({hhp}))"
    else:
        dpx = f"max(abs(({px})-({cxp}))-({hwp}),abs(({py})-({cyp}))-({hhp}))"
    if feather <= 1e-9:
        m = f"if(lte(({dpx}),0),255,0)"
    else:
        t = f"max(0,min(1,(-({dpx}))/({fp})))"
        sm = f"({t})*({t})*(3-2*({t}))"
        m = f"({sm})*255"
    if invert:
        m = f"255-({m})"
    return m


def ffmpeg_matte_filter(mask: dict, w: int, h: int, rate: int, tvar: str = "T") -> str:
    lum = geq_lum_expr(mask, w, h, rate, tvar)
    return f"geq=lum_expr='{lum}':cb=128:cr=128,format=gray"


def ffmpeg_masked_merge(plain_label: str, corr_label: str, mask_label: str, out_label: str) -> str:
    return f"[{plain_label}][{corr_label}][{mask_label}]maskedmerge[{out_label}]"

