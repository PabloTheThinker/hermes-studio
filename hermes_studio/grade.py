"""Primary colour correction: lift / gamma / gain per channel, then saturation.

One formula, stated once, so the render and the page's preview cannot disagree:

    per channel c, on gamma-encoded values in 0..1 (what ffmpeg and the browser both see):
        y = lift_c + x * (gain_c - lift_c)        # lift sets the black point, gain the white
        y = clamp(y, 0, 1) ** (1 / gamma_c)       # gamma bends the mids, ends stay put
    then saturation about Rec.709 luma (Y = .2126 R + .7152 G + .0722 B):
        out_c = Y + sat * (c - Y)

This is the lift/gamma/gain model Resolve's Primaries wheels use, written plainly. The render
runs the per-channel curve as an ffmpeg ``lutrgb`` expression (exact, per 8-bit code value)
and the saturation as a ``colorchannelmixer`` matrix. The preview gets the same two stages as
an SVG ``feComponentTransfer`` table sampled from :func:`curve` and an ``feColorMatrix`` built
by :func:`sat_matrix`, so both read the numbers from here.

Stored on a clip as ``props.grade`` = ``{"lift": [r, g, b], "gamma": [r, g, b],
"gain": [r, g, b], "sat": s}``, every number a reduced ``[num, den]`` pair like the other props.
"""
from __future__ import annotations

from fractions import Fraction
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
    }
    return None if is_identity(out) else out


def is_identity(g: dict) -> bool:
    return all(abs(a - b) < 1e-9 for k in ("lift", "gamma", "gain") for a, b in zip(g[k], IDENTITY[k])) and abs(g["sat"] - 1.0) < 1e-9


def curve(g: dict, ch: int, x: float) -> float:
    """The per-channel curve at ``x`` (0..1) for channel ``ch`` (0 r, 1 g, 2 b)."""
    lo, hi, gm = g["lift"][ch], g["gain"][ch], g["gamma"][ch]
    y = min(1.0, max(0.0, lo + x * (hi - lo)))
    return y ** (1.0 / gm)


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


def ffmpeg_chain(g: dict | None) -> str:
    """The grade as ffmpeg filters (empty for none). ``lutrgb`` evaluates the curve once per
    8-bit code value; ``colorchannelmixer`` applies the saturation matrix. Both run on RGB,
    so ffmpeg converts in and back out around them."""
    if not g:
        return ""
    parts = []
    curves = []
    for i, c in enumerate(CHANNELS):
        lo, hi, gm = g["lift"][i], g["gain"][i], g["gamma"][i]
        if abs(lo) < 1e-12 and abs(hi - 1) < 1e-12 and abs(gm - 1) < 1e-12:
            continue
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
    return {"lift": list(g["lift"]), "gamma": list(g["gamma"]), "gain": list(g["gain"]), "sat": g["sat"]}


def pair(v: float) -> list[int]:
    fr = Fraction(v).limit_denominator(10000)
    return [fr.numerator, fr.denominator]


def store(lift=None, gamma=None, gain=None, sat=None) -> dict | None:
    """Floats from the page -> ``props.grade`` (``[num, den]`` pairs), or None for the identity.
    Raises ValueError naming the first number out of range."""
    g = {
        "lift": tuple(float(v) for v in (lift if lift is not None else IDENTITY["lift"])),
        "gamma": tuple(float(v) for v in (gamma if gamma is not None else IDENTITY["gamma"])),
        "gain": tuple(float(v) for v in (gain if gain is not None else IDENTITY["gain"])),
        "sat": float(sat) if sat is not None else 1.0,
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
    return {"lift": [pair(v) for v in g["lift"]], "gamma": [pair(v) for v in g["gamma"]],
            "gain": [pair(v) for v in g["gain"]], "sat": pair(g["sat"])}


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
