"""Cubic easing for keyframed values. One formula for render (ffmpeg), preview (JS) and tests."""

from __future__ import annotations

EASE_IDS = frozenset({"linear", "ease-in", "ease-out", "ease-in-out"})
DEFAULT_EASE = "linear"


def ease_progress(u: float, kind: str = DEFAULT_EASE) -> float:
    """Map linear segment progress u in [0, 1] to eased progress in [0, 1]."""
    u = max(0.0, min(1.0, float(u)))
    if kind == "ease-in":
        return u * u * u
    if kind == "ease-out":
        v = 1.0 - u
        return 1.0 - v * v * v
    if kind == "ease-in-out":
        if u < 0.5:
            return 4.0 * u * u * u
        v = -2.0 * u + 2.0
        return 1.0 - v * v * v / 2.0
    return u


def ease_ffmpeg(u_expr: str, kind: str) -> str:
    """ffmpeg expression for eased progress from a linear ``u_expr`` (already 0..1)."""
    if kind == "ease-in":
        return f"pow({u_expr},3)"
    if kind == "ease-out":
        return f"1-pow(1-({u_expr}),3)"
    if kind == "ease-in-out":
        return f"if(lt({u_expr},0.5),4*pow({u_expr},3),1-pow(-2*({u_expr})+2,3)/2)"
    return u_expr


def interp_scalar(kfs: list[dict], key: str, t: float, *, ease_key: str = "ease") -> float:
    """Piecewise interpolation over sorted keyframes; segment easing from the start key."""
    if not kfs:
        raise ValueError("empty keyframes")
    if t <= kfs[0]["at"]:
        return float(kfs[0][key])
    if t >= kfs[-1]["at"]:
        return float(kfs[-1][key])
    for i in range(1, len(kfs)):
        a, b = kfs[i - 1], kfs[i]
        if t < b["at"]:
            if b["at"] <= a["at"]:
                return float(a[key])
            u = (t - a["at"]) / (b["at"] - a["at"])
            p = ease_progress(u, str(a.get(ease_key) or DEFAULT_EASE))
            return float(a[key]) + p * (float(b[key]) - float(a[key]))
    return float(kfs[-1][key])


def interp_expr(kfs: list[dict], key: str, tvar: str, *, eased: bool = False) -> str:
    """ffmpeg expression for ``key`` over sorted keyframes (hold before first / after last)."""
    if eased:
        return _interp_expr_eased(kfs, key, tvar)
    return _interp_expr_linear(kfs, key, tvar)


def _interp_expr_linear(kfs: list[dict], key: str, tvar: str) -> str:
    def v(x: float) -> str:
        return f"{x:.6f}"

    expr = v(kfs[-1][key])
    for i in range(len(kfs) - 1, 0, -1):
        a, b = kfs[i - 1], kfs[i]
        if abs(b[key] - a[key]) < 1e-12 or b["at"] <= a["at"]:
            seg = v(a[key])
        else:
            seg = f"{v(a[key])}+({v(b[key])}-{v(a[key])})*({tvar}-{v(a['at'])})/({v(b['at'])}-{v(a['at'])})"
        expr = f"if(lt({tvar},{v(b['at'])}),{seg},{expr})"
    return f"if(lt({tvar},{v(kfs[0]['at'])}),{v(kfs[0][key])},{expr})" if len(kfs) > 1 else expr


def _interp_expr_eased(kfs: list[dict], key: str, tvar: str) -> str:
    def v(x: float) -> str:
        return f"{x:.6f}"

    def seg(a: dict, b: dict) -> str:
        if abs(b[key] - a[key]) < 1e-12 or b["at"] <= a["at"]:
            return v(a[key])
        u = f"clip(({tvar}-{v(a['at'])})/({v(b['at'])}-{v(a['at'])}),0,1)"
        p = ease_ffmpeg(u, str(a.get("ease") or DEFAULT_EASE))
        return f"{v(a[key])}+({v(b[key])}-{v(a[key])})*({p})"

    expr = v(kfs[-1][key])
    for i in range(len(kfs) - 1, 0, -1):
        a, b = kfs[i - 1], kfs[i]
        expr = f"if(lt({tvar},{v(b['at'])}),{seg(a, b)},{expr})"
    return f"if(lt({tvar},{v(kfs[0]['at'])}),{v(kfs[0][key])},{expr})" if len(kfs) > 1 else expr


__all__ = [
    "DEFAULT_EASE",
    "EASE_IDS",
    "ease_ffmpeg",
    "ease_progress",
    "interp_expr",
    "interp_scalar",
]
