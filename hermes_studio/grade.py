"""Primary colour correction: lift / gamma / gain per channel, then saturation.

One formula, stated once, so the render and the page's preview cannot disagree:

    per channel c, on gamma-encoded values in 0..1 (what ffmpeg and the browser both see):
        y = lift_c + x * (gain_c - lift_c)        # lift sets the black point, gain the white
        y = clamp(y, 0, 1) ** (1 / gamma_c)       # gamma bends the mids, ends stay put
        y = curve_c(curve_master(y))              # optional custom curves (Resolve's Curves)
    then saturation about Rec.709 luma (Y = .2126 R + .7152 G + .0722 B):
        out_c = Y + sat * (c - Y)

A custom curve is a monotone cubic (PCHIP, Fritsch-Carlson) through 2-16 points from x = 0 to
x = 1: smooth, and it never overshoots between points, so it can't reverse or clip a tone.

This is the lift/gamma/gain model Resolve's Primaries wheels use, written plainly. The render
runs the per-channel curve as an ffmpeg ``lutrgb`` expression (exact, per 8-bit code value) --
or, once custom curves are set, as a 1D LUT this module writes (``lut1d``, 4096 points of the
same function) -- and the saturation as a ``colorchannelmixer`` matrix. The preview gets the same two stages as
an SVG ``feComponentTransfer`` table sampled from :func:`curve` and an ``feColorMatrix`` built
by :func:`sat_matrix`, so both read the numbers from here.

Stored on a clip as ``props.grade`` = ``{"lift": [r, g, b], "gamma": [r, g, b],
"gain": [r, g, b], "sat": s, "curves": {"m"|"r"|"g"|"b": [[x, y], ...]}}``, every number a
reduced ``[num, den]`` pair like the other props; ``curves`` and each of its keys are optional.
"""
from __future__ import annotations

import hashlib
from fractions import Fraction
from pathlib import Path
from typing import Any

KEYS = ("lift", "gamma", "gain", "sat")
CHANNELS = "rgb"
IDENTITY = {"lift": (0.0, 0.0, 0.0), "gamma": (1.0, 1.0, 1.0), "gain": (1.0, 1.0, 1.0), "sat": 1.0}
# Ranges (inclusive). Lift is an offset of the black point; gain a multiplier of the white
# point; gamma > 0 bends the mids; saturation 0 = mono, 1 = unchanged.
LIFT = (Fraction(-1, 2), Fraction(1, 2))
GAMMA = (Fraction(1, 5), Fraction(5))
GAIN = (Fraction(0), Fraction(4))
SAT = (Fraction(0), Fraction(4))
RANGES = {"lift": LIFT, "gamma": GAMMA, "gain": GAIN, "sat": SAT}
LUMA = (0.2126, 0.7152, 0.0722)  # Rec.709
# How many points the preview's per-channel table carries. Linear interpolation between 257
# evenly spaced samples is within a code value of the exact curve for any gamma in range.
TABLE_POINTS = 257
# Custom curves: master (all channels) then per channel; 2..CURVE_MAX points each.
CURVE_KEYS = ("m", "r", "g", "b")
CURVE_MAX = 16
# Points in the render's 1D LUT once curves are set: linear interpolation between 4096 samples is
# far finer than a code value.
LUT_SIZE = 4096


def _f(v: Any) -> float:
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return float(Fraction(int(v[0]), int(v[1])))
    return float(v)  # type: ignore[arg-type]


def parse(grade: dict | None) -> dict | None:
    """``props.grade`` -> plain floats ``{lift: (r,g,b), gamma: (...), gain: (...), sat: s}``.
    None for a missing grade or the identity (no grade is the same as the identity)."""
    if not isinstance(grade, dict):
        return None
    out = {
        "lift": tuple(_f(v) for v in grade.get("lift") or IDENTITY["lift"]),
        "gamma": tuple(_f(v) for v in grade.get("gamma") or IDENTITY["gamma"]),
        "gain": tuple(_f(v) for v in grade.get("gain") or IDENTITY["gain"]),
        "sat": _f(grade["sat"]) if grade.get("sat") is not None else 1.0,
        "curves": _parse_curves(grade.get("curves")),
    }
    return None if is_identity(out) else out


def _parse_curves(cv: Any) -> dict | None:
    if not isinstance(cv, dict):
        return None
    out = {}
    for k in CURVE_KEYS:
        pts = cv.get(k)
        if not pts:
            continue
        pts = tuple((_f(p[0]), _f(p[1])) for p in pts)
        if not _is_straight(pts):
            out[k] = pts
    return out or None


def _is_straight(pts) -> bool:
    return len(pts) == 2 and abs(pts[0][1]) < 1e-9 and abs(pts[1][1] - 1) < 1e-9


def is_identity(g: dict) -> bool:
    return (all(abs(a - b) < 1e-9 for k in ("lift", "gamma", "gain") for a, b in zip(g[k], IDENTITY[k]))
            and abs(g["sat"] - 1.0) < 1e-9 and not g.get("curves"))


def pchip(pts, x: float) -> float:
    """Monotone cubic (Fritsch-Carlson PCHIP) through ``pts`` ((x, y) with x increasing from 0
    to 1), at ``x``. Between points it stays between their y values (no overshoot). wheels.js
    carries the same function for the live preview; a test pins them equal."""
    n = len(pts)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    if n == 2:
        (x0, y0), (x1, y1) = pts
        return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    h = [pts[k + 1][0] - pts[k][0] for k in range(n - 1)]
    d = [(pts[k + 1][1] - pts[k][1]) / h[k] for k in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for k in range(1, n - 1):
        if d[k - 1] * d[k] <= 0:
            m[k] = 0.0
        else:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    # the endpoint slopes, limited so the first and last pieces stay monotone too
    for e, dd in ((0, d[0]), (n - 1, d[-1])):
        if m[e] * dd <= 0:
            m[e] = 0.0
        elif abs(m[e]) > 3 * abs(dd):
            m[e] = 3 * dd
    k = 0
    while k < n - 2 and x > pts[k + 1][0]:
        k += 1
    t = (x - pts[k][0]) / h[k]
    t2, t3 = t * t, t * t * t
    return ((2 * t3 - 3 * t2 + 1) * pts[k][1] + (t3 - 2 * t2 + t) * h[k] * m[k]
            + (-2 * t3 + 3 * t2) * pts[k + 1][1] + (t3 - t2) * h[k] * m[k + 1])


def curve(g: dict, ch: int, x: float) -> float:
    """The per-channel curve at ``x`` (0..1) for channel ``ch`` (0 r, 1 g, 2 b)."""
    lo, hi, gm = g["lift"][ch], g["gain"][ch], g["gamma"][ch]
    y = min(1.0, max(0.0, lo + x * (hi - lo)))
    y = y ** (1.0 / gm)
    cv = g.get("curves")
    if cv:
        if "m" in cv:
            y = pchip(cv["m"], y)
        if CHANNELS[ch] in cv:
            y = pchip(cv[CHANNELS[ch]], y)
        y = min(1.0, max(0.0, y))
    return y


def sat_matrix(s: float) -> list[list[float]]:
    """3x3 RGB matrix for saturation ``s`` about Rec.709 luma: row = output channel."""
    wr, wg, wb = LUMA
    k = 1.0 - s
    return [
        [k * wr + s, k * wg, k * wb],
        [k * wr, k * wg + s, k * wb],
        [k * wr, k * wg, k * wb + s],
    ]


def apply_pixel(g: dict | None, rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """The whole grade on one 0..1 pixel: the reference the render and preview are checked by."""
    if not g:
        return rgb
    c = [curve(g, i, rgb[i]) for i in range(3)]
    m = sat_matrix(g["sat"])
    o = [min(1.0, max(0.0, sum(m[r][i] * c[i] for i in range(3)))) for r in range(3)]
    return (o[0], o[1], o[2])


def _cube_text(g: dict) -> str:
    n = LUT_SIZE - 1
    rows = (" ".join(f"{curve(g, ch, i / n):.7f}" for ch in range(3)) for i in range(LUT_SIZE))
    return f'TITLE "hermes-studio grade"\nLUT_1D_SIZE {LUT_SIZE}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n' + "\n".join(rows) + "\n"


def _filter_path(p: Path) -> str:
    """A path as an unquoted value inside an ffmpeg filter graph. Two levels of escaping: the
    option value (\\ ' :) then the graph (\\ ' [ ] , ;). Quoting with '...' can't carry a quote
    (ffmpeg takes no escapes inside quotes), so nothing is quoted. Checked with a folder named
    it's a: [b],c;d, through both -vf and -filter_complex."""
    s = str(p).replace("\\", "/")
    for ch in ("\\", "'", ":"):
        s = s.replace(ch, "\\" + ch)
    for ch in ("\\", "'", "[", "]", ",", ";"):
        s = s.replace(ch, "\\" + ch)
    return s


def ffmpeg_chain(g: dict | None, lut_dir: Path | None = None) -> str:
    """The grade as ffmpeg filters (empty for none). ``lutrgb`` evaluates the curve once per
    8-bit code value; ``colorchannelmixer`` applies the saturation matrix. Both run on RGB,
    so ffmpeg converts in and back out around them. With custom curves the per-channel stage is
    a ``lut1d`` reading a .cube this function writes into ``lut_dir`` (named by its content, so
    an unchanged grade reuses its file)."""
    if not g:
        return ""
    parts = []
    if g.get("curves"):
        if lut_dir is None:
            raise ValueError("a grade with curves needs a folder for its LUT")
        text = _cube_text(g)
        path = Path(lut_dir) / f"grade-{hashlib.sha1(text.encode()).hexdigest()[:16]}.cube"
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(text)
            tmp.replace(path)
        parts.append(f"lut1d=file={_filter_path(path)}:interp=linear")
    # Without curves the per-channel stage is the exact lutrgb expression; with them, the LUT
    # above already carries lift/gamma/gain too, so no lutrgb.
    curves = None if g.get("curves") else []
    for i, c in enumerate(CHANNELS):
        lo, hi, gm = g["lift"][i], g["gain"][i], g["gamma"][i]
        if abs(lo) < 1e-12 and abs(hi - 1) < 1e-12 and abs(gm - 1) < 1e-12:
            continue
        if curves is not None:
            curves.append(f"{c}='maxval*pow(clip({lo:.9g}+val/maxval*({hi - lo:.9g}),0,1),{1 / gm:.9g})'")
    if curves:
        parts.append("lutrgb=" + ":".join(curves))
    if abs(g["sat"] - 1.0) > 1e-12:
        m = sat_matrix(g["sat"])
        names = [f"{o}{i}" for o in CHANNELS for i in CHANNELS]
        vals = [m[r][i] for r in range(3) for i in range(3)]
        parts.append("colorchannelmixer=" + ":".join(f"{n}={v:.9g}" for n, v in zip(names, vals)))
    return ",".join(parts)


def preview(g: dict | None) -> dict | None:
    """What the page needs to show the grade: one table per channel (TABLE_POINTS samples of
    :func:`curve`, 0..1) and the saturation matrix. Rounded to 5 places (finer than a code
    value) so the view stays small."""
    if not g:
        return None
    n = TABLE_POINTS - 1
    return {
        "tables": [[round(curve(g, ch, i / n), 5) for i in range(TABLE_POINTS)] for ch in range(3)],
        "matrix": [[round(v, 6) for v in row] for row in sat_matrix(g["sat"])],
    }


def view(g: dict | None) -> dict | None:
    """The grade's numbers for the inspector, as floats."""
    if not g:
        return None
    cv = g.get("curves") or {}
    return {"lift": list(g["lift"]), "gamma": list(g["gamma"]), "gain": list(g["gain"]), "sat": g["sat"],
            "curves": {k: [list(p) for p in pts] for k, pts in cv.items()} or None}


def pair(v: float) -> list[int]:
    fr = Fraction(v).limit_denominator(10000)
    return [fr.numerator, fr.denominator]


def _store_curves(curves: Any) -> dict | None:
    """Page curves ({"m": [[x, y], ...], ...}) -> checked and sorted floats, straight lines and
    absent keys dropped. Raises ValueError naming what is wrong."""
    if curves is None:
        return None
    if not isinstance(curves, dict):
        raise ValueError("curves must be an object of m / r / g / b point lists")
    out = {}
    for k, pts in curves.items():
        if k not in CURVE_KEYS:
            raise ValueError(f"unknown curve {k!r}; use m, r, g or b")
        if pts is None:
            continue
        try:
            pts = [(float(p[0]), float(p[1])) for p in pts]
        except (TypeError, ValueError, IndexError):
            raise ValueError(f"curve {k} points must be [x, y] pairs") from None
        if not (2 <= len(pts) <= CURVE_MAX):
            raise ValueError(f"curve {k} needs 2 to {CURVE_MAX} points")
        pts.sort()
        if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in pts):
            raise ValueError(f"curve {k} points must be inside 0..1")
        if any(b[0] - a[0] < 1e-3 for a, b in zip(pts, pts[1:])):
            raise ValueError(f"curve {k} has two points at the same input")
        if pts[0][0] != 0 or pts[-1][0] != 1:
            raise ValueError(f"curve {k} must run from input 0 to input 1")
        if not _is_straight(pts):
            out[k] = pts
    return out or None


def store(lift=None, gamma=None, gain=None, sat=None, curves=None) -> dict | None:
    """Floats from the page -> ``props.grade`` (``[num, den]`` pairs), or None for the identity.
    Raises ValueError naming the first number out of range."""
    g = {
        "lift": tuple(float(v) for v in (lift if lift is not None else IDENTITY["lift"])),
        "gamma": tuple(float(v) for v in (gamma if gamma is not None else IDENTITY["gamma"])),
        "gain": tuple(float(v) for v in (gain if gain is not None else IDENTITY["gain"])),
        "sat": float(sat) if sat is not None else 1.0,
        "curves": _store_curves(curves),
    }
    for k in ("lift", "gamma", "gain"):
        if len(g[k]) != 3:
            raise ValueError(f"{k} needs three numbers (r, g, b)")
        lo, hi = RANGES[k]
        for c, v in zip(CHANNELS, g[k]):
            if not (float(lo) <= v <= float(hi)):
                raise ValueError(f"{k} {c} must be between {float(lo):g} and {float(hi):g}")
    if not (float(SAT[0]) <= g["sat"] <= float(SAT[1])):
        raise ValueError(f"saturation must be between {float(SAT[0]):g} and {float(SAT[1]):g}")
    if is_identity(g):
        return None
    out = {"lift": [pair(v) for v in g["lift"]], "gamma": [pair(v) for v in g["gamma"]],
           "gain": [pair(v) for v in g["gain"]], "sat": pair(g["sat"])}
    if g["curves"]:
        out["curves"] = {k: [[pair(x), pair(y)] for x, y in pts] for k, pts in g["curves"].items()}
    return out


# ---- named looks ------------------------------------------------------------------------
# The five looks are grades now, so they show in the preview, the scopes and the wheels like
# any other grade. Each was fitted (Nelder-Mead over the 10 numbers) to what its old ffmpeg
# eq/colorbalance chain did to a 9x9x9 RGB cube; error in 8-bit code values, rms / worst:
#   warm 1.52 / 11.0   cool 1.60 / 12.1   punch 1.03 / 3.9   film 2.95 / 10.7
# mono is set by hand: saturation 0 about Rec.709 luma plus the old contrast lift. The old
# chain's eq=saturation=0 used Rec.601 luma, which no HD grade should, so mono differs on
# saturated colours by design (greys stay within 4 code values of the old look).
# Script: ~/.hermes/cache/scratch/fit_looks.py (kept out of the package; it needs ffmpeg).
LOOKS: dict[str, dict[str, Any]] = {
    "warm": {"lift": (-0.033, -0.033, -0.05), "gamma": (0.99, 0.999, 1.007), "gain": (1.018, 1.035, 1.018), "sat": 1.052},
    "cool": {"lift": (-0.046, -0.027, -0.031), "gamma": (1.007, 0.999, 0.989), "gain": (1.017, 1.029, 1.014), "sat": 0.997},
    "punch": {"lift": (-0.092, -0.104, -0.108), "gamma": (1.001, 0.999, 0.999), "gain": (1.085, 1.085, 1.071), "sat": 1.057},
    "mono": {"lift": (-0.06, -0.06, -0.06), "gamma": (1.0, 1.0, 1.0), "gain": (1.06, 1.06, 1.06), "sat": 0.0},
    "film": {"lift": (-0.035, -0.028, -0.026), "gamma": (0.998, 0.998, 0.995), "gain": (1.014, 1.02, 1.004), "sat": 0.898},
}


def look(name: str | None) -> dict | None:
    """A named look as ``props.grade`` (``[num, den]`` pairs), or None for no look."""
    if not name:
        return None
    return store(**LOOKS[name])


def look_name(stored: dict | None) -> str | None:
    """The look a stored grade is, if it is exactly one of them (the inspector's Look menu
    shows it; a grade that was moved off a look reads as no look)."""
    if not stored:
        return None
    for name in LOOKS:
        if look(name) == stored:
            return name
    return None
