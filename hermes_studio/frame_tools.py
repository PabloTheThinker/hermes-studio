"""S5 frame tools on the engine: ``timeline_frames``, ``timeline_contact_sheet``, ``history_frames``.

They need the ``render`` scope and a running engine (making a frame writes the cache, and a
closed-app read never writes). Results carry refs (``key``, ``at``, ``cached``); the image bytes go
only as MCP image content, and only when ``images`` isn't false (Wire §1: refs by default in
write results, pixels on request)."""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Any

from hermes_studio import frames as F
from hermes_studio import oplog as O
from hermes_studio import timeline as T

IMAGES = "_images"  # result key the /mcp layer turns into image content blocks


def _bad(path: str, rule: str, msg: str) -> O.OplogError:
    return O.OplogError("invalid_op", msg, rule=rule, path=path)


def _no_unknown(args: dict, allowed: set[str]) -> None:
    for k in sorted(set(args) - allowed, key=repr):
        raise _bad(f"/{k}", "unknown_arg", f"unknown argument '{k}'")


def _width(args: dict) -> int:
    w = args.get("width", F.DEFAULT_WIDTH)
    if not O._int_arg(w) or not 32 <= w <= F.MAX_WIDTH:
        raise _bad("/width", "bad_arg", f"'width' must be a whole number of pixels, 32-{F.MAX_WIDTH}")
    return w


def _images_flag(args: dict) -> bool:
    v = args.get("images", True)
    if not isinstance(v, bool):
        raise _bad("/images", "bad_arg", "'images' must be true or false")
    return v


def _seconds(v: Any, path: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v) or v < 0:
        raise _bad(path, "bad_arg", "a time must be a number of seconds, 0 or more")
    return int(Fraction(v) * T.TICK_RATE)


def _cache(proj: Any) -> F.FrameCache:
    c = getattr(proj, "_frame_cache", None)
    if c is None:
        c = proj._frame_cache = F.FrameCache(proj.dir)
    return c


def _doc(proj: Any) -> dict:
    with proj.mutex:
        return proj.oplog().doc


def _ref(t: int, key: str, hit: bool) -> dict:
    return {"at": t, "at_s": t / T.TICK_RATE, "key": key, "cached": hit}


def timeline_frames(proj: Any, args: dict) -> dict:
    """``{at_s: [seconds...]}`` (or ``at: [ticks...]``), up to 12: one frame each."""
    _no_unknown(args, {"at_s", "at", "width", "images"})
    width, want_images = _width(args), _images_flag(args)
    if ("at_s" in args) == ("at" in args):
        raise _bad("/at_s", "missing_arg" if "at" not in args else "bad_arg", "give at_s (seconds) or at (ticks), not both")
    key = "at_s" if "at_s" in args else "at"
    raw = args[key]
    if not isinstance(raw, list) or not 1 <= len(raw) <= 12:
        raise _bad(f"/{key}", "bad_arg", f"'{key}' must be a list of 1-12 times")
    times = []
    for i, v in enumerate(raw):
        if key == "at":
            if not O._int_arg(v) or v < 0:
                raise _bad(f"/at/{i}", "bad_arg", "a time in ticks must be a whole number, 0 or more")
            times.append(v)
        else:
            times.append(_seconds(v, f"/at_s/{i}"))
    doc, cache = _doc(proj), _cache(proj)
    refs, imgs = [], []
    for t in times:
        k, path, hit = cache.get(F.recipe_at(doc, t, width))
        refs.append(_ref(t, k, hit))
        if want_images:
            imgs.append(("image/jpeg", path.read_bytes()))
    out: dict[str, Any] = {"version": doc["version"], "hash": doc["hash"], "frames": refs}
    if imgs:
        out[IMAGES] = imgs
    return out


def timeline_contact_sheet(proj: Any, args: dict) -> dict:
    """``count`` (default 12, 1-48) frames spread evenly over ``from_s``..``to_s`` (default the
    whole timeline), tiled into one JPEG with times."""
    _no_unknown(args, {"count", "width", "from_s", "to_s", "cols", "images"})
    width, want_images = _width(args), _images_flag(args)
    n = args.get("count", 12)
    if not O._int_arg(n) or not 1 <= n <= F.SHEET_MAX:
        raise _bad("/count", "bad_arg", f"'count' must be 1-{F.SHEET_MAX}")
    cols = args.get("cols", 4)
    if not O._int_arg(cols) or not 1 <= cols <= 12:
        raise _bad("/cols", "bad_arg", "'cols' must be 1-12")
    doc = _doc(proj)
    end = F.timeline_end(doc)
    a = _seconds(args["from_s"], "/from_s") if "from_s" in args else 0
    b = _seconds(args["to_s"], "/to_s") if "to_s" in args else end
    if b <= a:
        raise _bad("/to_s", "bad_arg", "the range is empty: to_s must be after from_s (and the timeline must not be empty)")
    times = [a + (b - a) * (2 * i + 1) // (2 * n) for i in range(n)]  # the middle of each slot
    cache = _cache(proj)
    refs, files = [], []
    for t in times:
        k, path, hit = cache.get(F.recipe_at(doc, t, width))
        refs.append(_ref(t, k, hit))
        files.append((t, path))
    out: dict[str, Any] = {"version": doc["version"], "hash": doc["hash"], "from": a, "to": b, "frames": refs}
    if want_images:
        out[IMAGES] = [("image/jpeg", F.contact_sheet(files, cols))]
    return out


def history_frames(proj: Any, args: dict) -> dict:
    """Before/after frames of one entry (``op_id``) at the first time it changed."""
    _no_unknown(args, {"op_id", "width", "images"})
    width, want_images = _width(args), _images_flag(args)
    op_id = args.get("op_id")
    if not isinstance(op_id, str):
        raise _bad("/op_id", "bad_arg" if "op_id" in args else "missing_arg", "'op_id' must be an op id")
    with proj.mutex:
        info = F.entry_frames(proj.oplog(), op_id, width)
    if not info:
        raise O.OplogError("not_found", f"no entry {op_id!r}", rule="not_found", path="/op_id", id=op_id)
    cache = _cache(proj)
    out: dict[str, Any] = {k: info[k] for k in ("op_id", "at", "before_version", "after_version")}
    out["at_s"] = info["at"] / T.TICK_RATE
    imgs = []
    for side in ("before", "after"):
        k, path, hit = cache.get(info[side])
        out[side] = {"key": k, "cached": hit}
        if want_images:
            imgs.append(("image/jpeg", path.read_bytes()))
    if imgs:
        out[IMAGES] = imgs
    return out


TOOLS = {"timeline_frames": timeline_frames, "timeline_contact_sheet": timeline_contact_sheet, "history_frames": history_frames}
