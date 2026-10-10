"""render_timeline._interp_expr: the ffmpeg expression behind keyframes and volume envelopes.

The expression is evaluated here in Python (it only uses if(), lt() and arithmetic) and
compared with a plain reference interpolation at many points.
"""

from __future__ import annotations

import pytest

from hermes_studio import render_timeline as R


def _eval(expr: str, tvar: str, t: float) -> float:
    py = expr.replace("if(", "_if(").replace("lt(", "_lt(")
    env = {"_if": lambda c, a, b: a if c else b, "_lt": lambda x, y: 1 if x < y else 0, tvar: t}
    return float(eval(py, {"__builtins__": {}}, env))  # noqa: S307 -- our own generated expression


def _ref(kfs: list[dict], key: str, t: float) -> float:
    if t <= kfs[0]["at"]:
        return kfs[0][key]
    for a, b in zip(kfs, kfs[1:]):
        if t < b["at"]:
            return a[key] + (b[key] - a[key]) * (t - a["at"]) / (b["at"] - a["at"])
    return kfs[-1][key]


CASES = {
    "one key": [{"at": 1.0, "v": 0.5}],
    "ramp down and hold the LAST value": [{"at": 0.0, "v": 1.0}, {"at": 1.0, "v": 1.0}, {"at": 1.2, "v": 0.25}],
    "equal neighbours keep the earlier ramp": [{"at": 0.0, "v": 1.0}, {"at": 2.0, "v": 2.0}, {"at": 3.0, "v": 2.0}, {"at": 5.0, "v": 1.0}],
    "starts late": [{"at": 2.0, "v": 3.0}, {"at": 4.0, "v": 1.0}],
    "zoom in and stay": [{"at": 0.0, "v": 1.0}, {"at": 4.0, "v": 1.8}],
}


@pytest.mark.parametrize("name", list(CASES))
def test_interp_expr_matches_linear_interpolation_everywhere(name):
    kfs = CASES[name]
    expr = R._interp_expr(kfs, "v", "t")
    for i in range(-20, 141):
        t = i * 0.05
        assert abs(_eval(expr, "t", t) - _ref(kfs, "v", t)) < 1e-5, (name, t)


def test_the_old_builder_bugs_are_gone():
    # After the last key the value holds there (it used to snap back to the first key)...
    kfs = CASES["zoom in and stay"]
    assert abs(_eval(R._interp_expr(kfs, "v", "on"), "on", 9.0) - 1.8) < 1e-9
    # ...and an equal pair no longer erases the ramp before it (keys 1, 2, 2, 1).
    kfs = CASES["equal neighbours keep the earlier ramp"]
    assert abs(_eval(R._interp_expr(kfs, "v", "t"), "t", 1.0) - 1.5) < 1e-9
